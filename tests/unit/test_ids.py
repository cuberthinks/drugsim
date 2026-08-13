"""Tests for ULID generation and public identifiers."""

from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from drugsim_core.ids import (
    ENTITY_PREFIXES,
    PUBLIC_ID_RE,
    SYSTEM_USER_UID,
    ULID_RE,
    generate_ulid,
    parse_public_id,
    public_id,
    ulid_timestamp_ms,
)

pytestmark = pytest.mark.unit

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class TestUlidFormat:
    """Structural properties of generated ULIDs."""

    def test_length_is_26(self) -> None:
        assert len(generate_ulid()) == 26

    def test_matches_pattern(self) -> None:
        assert ULID_RE.match(generate_ulid())

    def test_uses_only_crockford_alphabet(self) -> None:
        for _ in range(200):
            assert set(generate_ulid()) <= set(CROCKFORD)

    def test_excludes_ambiguous_characters(self) -> None:
        """I, L, O and U are excluded to prevent transcription errors."""
        assert not (set("ILOU") & set(CROCKFORD))
        joined = "".join(generate_ulid() for _ in range(200))
        assert not (set("ILOU") & set(joined))

    def test_uniqueness(self) -> None:
        assert len({generate_ulid() for _ in range(10_000)}) == 10_000


class TestUlidTimestamp:
    """Timestamp encoding and sortability."""

    @given(st.integers(min_value=0, max_value=(1 << 48) - 1))
    def test_timestamp_roundtrips(self, timestamp_ms: int) -> None:
        assert ulid_timestamp_ms(generate_ulid(timestamp_ms=timestamp_ms)) == timestamp_ms

    def test_lexicographic_order_follows_time(self) -> None:
        """String sort order matches creation order.

        This is why ULID is preferred over UUIDv4: sequential index inserts rather
        than random ones.
        """
        ulids = [generate_ulid(timestamp_ms=t) for t in range(1_700_000_000_000, 1_700_000_000_050)]
        assert ulids == sorted(ulids)

    def test_rejects_negative_timestamp(self) -> None:
        with pytest.raises(ValueError, match="out of 48-bit range"):
            generate_ulid(timestamp_ms=-1)

    def test_rejects_overflow_timestamp(self) -> None:
        with pytest.raises(ValueError, match="out of 48-bit range"):
            generate_ulid(timestamp_ms=1 << 48)

    def test_rejects_malformed_ulid(self) -> None:
        with pytest.raises(ValueError, match="malformed ULID"):
            ulid_timestamp_ms("not-a-ulid")

    def test_rejects_ambiguous_characters_in_parse(self) -> None:
        """A ULID containing an excluded character is malformed."""
        with pytest.raises(ValueError, match="malformed ULID"):
            ulid_timestamp_ms("I" * 26)


class TestPublicId:
    """Prefixed public identifiers (TDS §4.1.1)."""

    @pytest.mark.parametrize("entity", sorted(ENTITY_PREFIXES))
    def test_every_entity_produces_a_valid_id(self, entity: str) -> None:
        value = public_id(entity)
        assert PUBLIC_ID_RE.match(value), value
        assert value.startswith(f"{ENTITY_PREFIXES[entity]}_")

    @pytest.mark.parametrize("entity", sorted(ENTITY_PREFIXES))
    def test_roundtrip(self, entity: str) -> None:
        value = public_id(entity)
        parsed_entity, parsed_ulid = parse_public_id(value)
        assert parsed_entity == entity
        assert ULID_RE.match(parsed_ulid)

    def test_wraps_existing_ulid(self) -> None:
        ulid = generate_ulid()
        assert public_id("compound", ulid=ulid) == f"cmp_{ulid}"

    def test_unknown_entity_raises(self) -> None:
        with pytest.raises(KeyError, match="no public-ID prefix"):
            public_id("wormhole")

    def test_malformed_ulid_raises(self) -> None:
        with pytest.raises(ValueError, match="malformed ULID"):
            public_id("compound", ulid="too-short")

    @pytest.mark.parametrize(
        "bad",
        ["", "cmp", "cmp_", "_01J8XK2M4N7P9QRSTVWXYZ0123", "cmp-01J8XK2M4N7P9QRSTVWXYZ0123"],
    )
    def test_malformed_public_id_raises(self, bad: str) -> None:
        with pytest.raises(ValueError, match="malformed public ID"):
            parse_public_id(bad)

    def test_unknown_prefix_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown public-ID prefix"):
            parse_public_id(f"zzz_{generate_ulid()}")

    def test_prefixes_are_unique(self) -> None:
        """Two entities sharing a prefix would make parsing ambiguous."""
        prefixes = list(ENTITY_PREFIXES.values())
        assert len(prefixes) == len(set(prefixes))

    def test_prefixes_are_lowercase_alpha(self) -> None:
        for prefix in ENTITY_PREFIXES.values():
            assert re.fullmatch(r"[a-z]{3,5}", prefix), prefix


class TestSystemUserUid:
    """The fixed bootstrap identifier used by migration 0011.

    It must be knowable at migration-authoring time (not derived from a runtime
    timestamp), because it resolves a chicken-and-egg problem: the audit trigger
    on system_user requires app.current_user_id to reference an EXISTING
    system_user row, and there is no existing row before the bootstrap account
    is created. This test is what backs the claim, made in the constant's
    docstring, that the value is verified rather than merely asserted.
    """

    def test_is_a_valid_ulid(self) -> None:
        assert ULID_RE.match(SYSTEM_USER_UID), SYSTEM_USER_UID

    def test_is_exactly_26_characters(self) -> None:
        assert len(SYSTEM_USER_UID) == 26

    def test_produces_a_valid_public_id(self) -> None:
        value = public_id("user", ulid=SYSTEM_USER_UID)
        entity, ulid = parse_public_id(value)
        assert entity == "user"
        assert ulid == SYSTEM_USER_UID

    def test_matches_the_literal_in_the_bootstrap_migration(self, project_root: object) -> None:
        """The migration duplicates this value as a literal (by design — migrations
        must remain runnable independent of the application package). This test is
        what keeps the duplication from silently drifting.
        """
        from pathlib import Path

        migration = (
            Path(str(project_root))
            / "database"
            / "migrations"
            / "versions"
            / "0011_bootstrap_system_user.py"
        )
        content = migration.read_text(encoding="utf-8")
        assert f'SYSTEM_USER_UID = "{SYSTEM_USER_UID}"' in content
