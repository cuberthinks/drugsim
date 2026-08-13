"""Identifier generation: ULIDs and prefixed public identifiers.

DrugSim uses surrogate ULID primary keys throughout (ADR-008). Structure-derived
keys such as InChIKey are unique-constrained but never primary keys, because they
change when standardisation logic changes — which would break every foreign key
referencing them.

ULID is preferred over UUIDv4 for two reasons:

* **Lexicographic sortability.** The leading 48 bits are a millisecond timestamp, so
  ULIDs sort by creation time as strings. This keeps B-tree index inserts
  approximately sequential, avoiding the random-write amplification UUIDv4 causes.
* **Crockford base32.** Case-insensitive, excludes ``I``, ``L``, ``O`` and ``U`` to
  avoid transcription errors and accidental profanity — relevant because these
  identifiers appear in support tickets and logs.

Implemented directly rather than taken as a dependency: the specification is short
and stable, the code is fully covered by tests, and this avoids a supply-chain
dependency on a package used in every primary key in the system (TDS §7.10, P10).
"""

from __future__ import annotations

import os
import re
import time
from typing import Final

__all__ = [
    "ENTITY_PREFIXES",
    "PUBLIC_ID_RE",
    "SYSTEM_USER_UID",
    "ULID_RE",
    "generate_ulid",
    "parse_public_id",
    "public_id",
    "ulid_timestamp_ms",
]

#: The bootstrap service account created by migration 0011 (see
#: database/migrations/versions/0011_bootstrap_system_user.py). A fixed,
#: deterministic ULID rather than a generated one: it must be knowable at
#: migration-authoring time (not derivable from a runtime timestamp), and it
#: resolves the chicken-and-egg problem where the audit trigger on system_user
#: requires app.current_user_id to reference an *existing* system_user — there is
#: no existing row before this one. Verified against ULID_RE in
#: tests/unit/test_ids.py, not merely asserted by construction.
SYSTEM_USER_UID = "0000000000SYSTEM0000000000"

#: Crockford base32 alphabet: digits plus uppercase letters, excluding I, L, O, U.
_CROCKFORD: Final[str] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE: Final[dict[str, int]] = {c: i for i, c in enumerate(_CROCKFORD)}

_TIMESTAMP_CHARS: Final[int] = 10
_RANDOM_CHARS: Final[int] = 16
_ULID_CHARS: Final[int] = _TIMESTAMP_CHARS + _RANDOM_CHARS  # 26

ULID_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")

#: Entity prefixes for public identifiers (TDS §4.1.1).
ENTITY_PREFIXES: Final[dict[str, str]] = {
    "compound": "cmp",
    "prediction": "prd",
    "model": "mdl",
    "dataset": "dst",
    "target": "tgt",
    "protein": "prot",
    "user": "usr",
    "tenant": "tnt",
    "experiment": "exp",
    "simulation": "sim",
    "job": "job",
    "measurement": "mea",
    "assessment": "asm",
}

PUBLIC_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<prefix>[a-z]{3,5})_(?P<ulid>[0-9A-HJKMNP-TV-Z]{26})$"
)


def _encode(value: int, length: int) -> str:
    """Encode an integer as fixed-length Crockford base32.

    Args:
        value: Non-negative integer to encode.
        length: Output length in characters.

    Returns:
        The encoded string, left-padded with the zero character.
    """
    chars = [""] * length
    for i in range(length - 1, -1, -1):
        chars[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


def generate_ulid(timestamp_ms: int | None = None) -> str:
    """Generate a ULID.

    Args:
        timestamp_ms: Millisecond Unix timestamp. Defaults to the current time.
            Supplying it explicitly makes generation deterministic in tests.

    Returns:
        A 26-character Crockford base32 ULID.

    Raises:
        ValueError: If ``timestamp_ms`` is negative or exceeds the 48-bit range.

    Example:
        >>> uid = generate_ulid()
        >>> len(uid)
        26
    """
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    if timestamp_ms < 0 or timestamp_ms >= (1 << 48):
        msg = f"timestamp_ms out of 48-bit range: {timestamp_ms}"
        raise ValueError(msg)

    randomness = int.from_bytes(os.urandom(10), "big")  # 80 bits
    return _encode(timestamp_ms, _TIMESTAMP_CHARS) + _encode(randomness, _RANDOM_CHARS)


def ulid_timestamp_ms(ulid: str) -> int:
    """Extract the millisecond timestamp embedded in a ULID.

    Args:
        ulid: A 26-character ULID.

    Returns:
        The millisecond Unix timestamp.

    Raises:
        ValueError: If the ULID is malformed.
    """
    if not ULID_RE.match(ulid):
        msg = f"malformed ULID: {ulid!r}"
        raise ValueError(msg)
    value = 0
    for char in ulid[:_TIMESTAMP_CHARS]:
        value = (value << 5) | _DECODE[char]
    return value


def public_id(entity: str, ulid: str | None = None) -> str:
    """Build a prefixed public identifier for an entity.

    Public identifiers are opaque to clients. The prefix makes them
    self-describing in logs and support tickets; the ULID body carries no
    parseable business meaning (TDS §4.1.1).

    Args:
        entity: Entity name, a key of :data:`ENTITY_PREFIXES`.
        ulid: Existing ULID to wrap. A new one is generated if omitted.

    Returns:
        An identifier such as ``cmp_01J8XK2M4N7P9QRSTVWXYZ0123``.

    Raises:
        KeyError: If the entity has no registered prefix.
        ValueError: If a supplied ULID is malformed.
    """
    if entity not in ENTITY_PREFIXES:
        msg = f"no public-ID prefix registered for entity {entity!r}"
        raise KeyError(msg)
    if ulid is None:
        ulid = generate_ulid()
    elif not ULID_RE.match(ulid):
        msg = f"malformed ULID: {ulid!r}"
        raise ValueError(msg)
    return f"{ENTITY_PREFIXES[entity]}_{ulid}"


def parse_public_id(value: str) -> tuple[str, str]:
    """Split a public identifier into its entity name and ULID.

    Args:
        value: A public identifier such as ``cmp_01J8XK...``.

    Returns:
        A tuple of ``(entity_name, ulid)``.

    Raises:
        ValueError: If the identifier is malformed or the prefix is unknown.
    """
    match = PUBLIC_ID_RE.match(value)
    if match is None:
        msg = f"malformed public ID: {value!r}"
        raise ValueError(msg)
    prefix = match.group("prefix")
    for entity, entity_prefix in ENTITY_PREFIXES.items():
        if entity_prefix == prefix:
            return entity, match.group("ulid")
    msg = f"unknown public-ID prefix {prefix!r} in {value!r}"
    raise ValueError(msg)
