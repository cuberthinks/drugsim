"""Protection of customer molecular structures from disclosure via logs.

A molecular structure uploaded by a customer is pre-patent trade secret. A SMILES
string appearing in an exception message or a debug log is an IP disclosure into a
system with different access controls, different retention, and typically wider
fan-out than the database (TDS §7.1, §7.2.3).

This module provides the first two of the five defence layers named in TDS §7.2.3:

1. :class:`SensitiveStructure` — a wrapper whose string representations are redacted
   by construction. Accidental interpolation into a log message is safe.
2. :func:`redact_event` — a structlog processor that scrubs sensitive keys and
   applies pattern matching as a backstop.

The remaining layers (exception-handler scrubbing, a lint rule, and the CI test in
``tests/security/test_no_structure_in_logs.py``) live elsewhere. The CI test is the
layer that actually holds the line; these are defence in depth.

Design note — why a wrapper rather than pattern matching alone:
    Reliably recognising an arbitrary SMILES string by regex is not possible. The
    grammar overlaps heavily with ordinary text and with file paths. Pattern matching
    is therefore a *backstop* here, deliberately tuned to avoid false positives, and
    the primary control is the type wrapper plus key-name scrubbing, both of which are
    exact rather than heuristic.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "SENSITIVE_KEYS",
    "SensitiveStructure",
    "looks_like_structure",
    "redact_event",
    "structure_digest",
]

#: Keys whose values are always redacted, regardless of content.
#:
#: ``inchikey`` is included deliberately. An InChIKey does not reveal a structure,
#: but it uniquely identifies one — enough to confirm whether a specific novel
#: compound has been submitted. ``compound_uid`` is the safe reference for logs.
SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "smiles",
        "canonical_smiles",
        "isomeric_smiles",
        "standardized_smiles",
        "parent_smiles",
        "source_smiles",
        "structure",
        "structure_value",
        "molblock",
        "molfile",
        "sdf",
        "mol",
        "inchi",
        "inchikey",
        "inchikey_full",
        "parent_inchikey",
        "scaffold",
        "bemis_murcko_scaffold",
        "query_structure",
    }
)

_REDACTED: Final[str] = "[REDACTED:structure]"

# Exact patterns. These are reliable and carry no false-positive risk.
_INCHI_RE: Final[re.Pattern[str]] = re.compile(r"InChI=1S?/[^\s\"']+")
_INCHIKEY_RE: Final[re.Pattern[str]] = re.compile(r"\b[A-Z]{14}-[A-Z]{10}-[A-Z]\b")

# Heuristic SMILES detection — backstop only.
#
# Tuning bias: this is a security control, so it errs toward over-redaction. A false
# positive costs a redacted diagnostic string; a false negative is an IP disclosure.
# The guards below suppress the false-positive shapes that actually occur in DrugSim
# logs (digests, paths, identifiers, key=value pairs), and the corpus in
# tests/unit/test_redaction.py pins the behaviour in both directions.
_SMILES_CHARSET_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9@+\-\[\]()=#$:/\\.%]+$")

#: Aromatic atom symbols in SMILES. Restricting the ring-closure patterns to these
#: (rather than any lowercase letter) is what keeps ordinary words out.
_AROMATIC = "bcnops"

_SMILES_EVIDENCE_RE: Final[re.Pattern[str]] = re.compile(
    rf"""
      \[[A-Za-z][A-Za-z0-9@+\-]{{0,8}}\]   # bracket atom: [nH] [C@@H] [Na+]
    | [{_AROMATIC}]{{2,}}\d                # aromatic run then ring closure: cc1
    | \d[{_AROMATIC}]{{2,}}                # ring closure then aromatic run: 1cc
    | [A-Z][=\#][A-Za-z(\[]                # explicit bond from an atom: C=O, C#N
    | \)[=\#]?[A-Z]                        # branch close then atom: )C  )=O
    | \([=\#][A-Z]                         # branch open then bond: (=O
    """,
    re.VERBOSE,
)

# Shapes that are charset-legal but are overwhelmingly not structures.
_HEXISH_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{12,}$")
_ULIDISH_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"\S+")
_TRAILING_PUNCT: Final[str] = ".,;:!?\"'"


def structure_digest(value: str) -> str:
    """Return a short, stable, non-reversible digest of a structure.

    Included in redacted output so that log lines referring to the same structure can
    be correlated without disclosing it.

    Args:
        value: The raw structure string.

    Returns:
        The first 12 hex characters of the SHA-256 digest.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class SensitiveStructure:
    """A molecular structure that is redacted in every string representation.

    Deliberately *not* a ``str`` subclass. A ``str`` subclass would be silently
    accepted by any API expecting a string, and would leak through code paths that
    bypass ``__str__`` (slicing, concatenation, ``%`` formatting of the underlying
    buffer). Requiring an explicit :meth:`reveal` call makes disclosure a visible,
    greppable, reviewable act.

    Attributes:
        kind: Structure format — ``smiles``, ``molblock``, or ``inchi``.

    Example:
        >>> s = SensitiveStructure("CC(=O)Oc1ccccc1C(=O)O", kind="smiles")
        >>> f"parsing {s}"
        'parsing [REDACTED:structure smiles sha256:a3f9c21b8e40]'
        >>> s.reveal()
        'CC(=O)Oc1ccccc1C(=O)O'
    """

    _value: str
    kind: str = "smiles"

    def reveal(self) -> str:
        """Return the underlying structure.

        The only route to the raw value. Call sites are greppable and are expected to
        be justified in review.

        Returns:
            The raw structure string.
        """
        return self._value

    @property
    def digest(self) -> str:
        """Short non-reversible digest, safe to log."""
        return structure_digest(self._value)

    def __str__(self) -> str:
        """Return the redacted representation."""
        return f"[REDACTED:structure {self.kind} sha256:{self.digest}]"

    def __repr__(self) -> str:
        """Return the redacted representation."""
        return self.__str__()

    def __format__(self, format_spec: str) -> str:
        """Return the redacted representation, ignoring the format spec.

        Ignoring ``format_spec`` is intentional: a spec such as ``:.20`` must not be
        able to slice the raw value back out.
        """
        return self.__str__()


def looks_like_structure(value: str) -> bool:
    """Heuristically decide whether a string appears to be a chemical structure.

    Backstop for the key-based scrubbing in :func:`redact_event`. Tuned conservatively
    to avoid false positives on ordinary strings — file paths, version numbers,
    identifiers — at the cost of missing some genuine structures. The type wrapper and
    key scrubbing are the reliable controls; this catches raw strings that escape both.

    Args:
        value: Candidate string.

    Returns:
        True if the string resembles an InChI, InChIKey, or SMILES.
    """
    if not value or len(value) < 6 or len(value) > 5000:
        return False
    if _INCHI_RE.search(value) or _INCHIKEY_RE.search(value):
        return True
    return _token_is_structure(value)


def _token_is_structure(token: str) -> bool:
    """Decide whether a single whitespace-free token resembles a SMILES.

    Args:
        token: Candidate token, already stripped of surrounding whitespace.

    Returns:
        True if the token resembles a SMILES string.
    """
    if len(token) < 6 or len(token) > 5000:
        return False
    if not _SMILES_CHARSET_RE.match(token):
        return False

    # Guards against charset-legal shapes that are common in logs and are not
    # structures. Ordered cheapest-first.
    if ":" in token:
        return False  # sha256:..., host:port, timestamps
    if _HEXISH_RE.match(token):
        return False  # content digests
    if _ULIDISH_RE.match(token):
        return False  # ULIDs and public-ID bodies
    if token.count("/") > 1 or token.count("\\") > 1:
        return False  # filesystem paths and URLs
    if sum(1 for c in token if c.isalpha()) < 3:
        return False  # version strings, numeric identifiers

    return bool(_SMILES_EVIDENCE_RE.search(token))


def _redact_embedded_structures(text: str) -> str:
    """Redact structure-like tokens appearing inside a longer string.

    Necessary because structures reach logs embedded in text far more often than as
    standalone values — through ``%``-style stdlib formatting and through exception
    messages, which are formatted and logged by handlers far from the raise site.
    Both were live leak paths caught by ``tests/security/test_no_structure_in_logs``.

    Args:
        text: Free text that may contain structures.

    Returns:
        The text with any structure-like token replaced.
    """

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if _token_is_structure(token):
            return f"[REDACTED:structure sha256:{structure_digest(token)}]"
        stripped = token.rstrip(_TRAILING_PUNCT)
        if stripped != token and _token_is_structure(stripped):
            suffix = token[len(stripped) :]
            return f"[REDACTED:structure sha256:{structure_digest(stripped)}]{suffix}"
        return token

    return _TOKEN_RE.sub(replace, text)


def _redact_value(value: Any, key: str | None = None) -> Any:  # noqa: ANN401
    """Recursively redact a value, considering its key.

    Args:
        value: Value to inspect.
        key: The mapping key this value was found under, if any.

    Returns:
        The value with any structure content replaced.
    """
    if isinstance(value, SensitiveStructure):
        return str(value)

    if key is not None and key.lower() in SENSITIVE_KEYS:
        if isinstance(value, str):
            return f"[REDACTED:structure sha256:{structure_digest(value)}]"
        return _REDACTED

    if isinstance(value, str):
        if _token_is_structure(value):
            return f"[REDACTED:structure sha256:{structure_digest(value)}]"
        if _INCHI_RE.search(value):
            value = _INCHI_RE.sub(_REDACTED, value)
        if _INCHIKEY_RE.search(value):
            value = _INCHIKEY_RE.sub(_REDACTED, value)
        return _redact_embedded_structures(value)

    if isinstance(value, dict):
        return {k: _redact_value(v, key=str(k)) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        redacted = [_redact_value(v, key=key) for v in value]
        return type(value)(redacted) if isinstance(value, tuple) else redacted

    return value


def redact_event(
    _logger: Any,  # noqa: ANN401
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that removes molecular structures from a log event.

    Applied to every log record. Scrubs by key name (exact), by
    :class:`SensitiveStructure` type (exact), and by pattern (heuristic backstop),
    recursing into nested mappings and sequences.

    Args:
        _logger: Unused; required by the structlog processor signature.
        _method_name: Unused; required by the structlog processor signature.
        event_dict: The event dictionary to scrub, mutated and returned.

    Returns:
        The scrubbed event dictionary.
    """
    return {key: _redact_value(value, key=str(key)) for key, value in event_dict.items()}
