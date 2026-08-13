"""Constraint tests: evidence domain (endpoint, assay, measurement).

TestMeasurementNeverHoldsAPrediction is the database-level enforcement of P4 —
measurements and predictions must never co-mingle. It is arguably the single
most important test in this file: P4 is stated as a principle throughout Phase 1
and the TDS, and this is what makes it impossible to violate rather than merely
discouraged.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .factories import (
    insert_compound,
    insert_data_source,
    insert_endpoint,
    insert_ingestion_snapshot,
    insert_toolchain,
)

pytestmark = [pytest.mark.integration, pytest.mark.constraints]


@pytest.fixture
def measurement_fixtures(session: Session, curator_user_id: str) -> dict[str, str]:
    """FK targets for a minimal measurement row."""
    source_id = insert_data_source(session)
    snapshot_id = insert_ingestion_snapshot(session, source_id)
    toolchain_id = insert_toolchain(session)
    compound_uid = insert_compound(
        session,
        source_id=source_id,
        snapshot_id=snapshot_id,
        toolchain_id=toolchain_id,
        created_by=curator_user_id,
    )
    endpoint_id = insert_endpoint(session)
    session.flush()
    return {
        "compound_uid": compound_uid,
        "endpoint_id": endpoint_id,
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        "created_by": curator_user_id,
    }


def _insert_measurement(session: Session, fx: dict[str, str], **overrides: object) -> None:
    """Insert a measurement row, allowing individual fields to be overridden."""
    params = {
        "measurement_uid": overrides.get("measurement_uid", "M" + "0" * 25),
        "license_tier": overrides.get("license_tier", "amber"),
        "compound_uid": fx["compound_uid"],
        "endpoint_id": fx["endpoint_id"],
        "canonical_value": overrides.get("canonical_value", 1.0),
        "canonical_unit": "unitless",
        "unit_verified_method": "documented",
        "value_relation": overrides.get("value_relation", "="),
        "measurement_status": overrides.get("measurement_status", "measured"),
        "evidence_type": overrides.get("evidence_type", "experimental"),
        "source_id": fx["source_id"],
        "snapshot_id": fx["snapshot_id"],
        "source_license": "CC-BY-4.0",
        "is_commercial_ok": True,
        "pipeline_version": "e" * 40,
        "drugsim_release": "0.1.0",
        "created_by": fx["created_by"],
    }
    session.execute(
        text(
            "INSERT INTO measurement (measurement_uid, license_tier, compound_uid, "
            "endpoint_id, canonical_value, canonical_unit, unit_verified_method, "
            "value_relation, measurement_status, evidence_type, source_id, "
            "snapshot_id, source_license, is_commercial_ok, pipeline_version, "
            "drugsim_release, created_by) "
            "VALUES (:measurement_uid, :license_tier, :compound_uid, :endpoint_id, "
            ":canonical_value, :canonical_unit, :unit_verified_method, "
            ":value_relation, :measurement_status, :evidence_type, :source_id, "
            ":snapshot_id, :source_license, :is_commercial_ok, :pipeline_version, "
            ":drugsim_release, :created_by)"
        ),
        params,
    )


class TestMeasurementNeverHoldsAPrediction:
    """ck_not_predicted: P4 as a database constraint, not a convention."""

    def test_predicted_evidence_type_rejected(
        self, session: Session, measurement_fixtures: dict[str, str]
    ) -> None:
        with pytest.raises(IntegrityError, match="ck_not_predicted"):
            _insert_measurement(session, measurement_fixtures, evidence_type="predicted")
            session.flush()

    @pytest.mark.parametrize(
        "evidence_type",
        ["experimental", "derived", "expert_curated", "text_mined", "inferred_by_homology"],
    )
    def test_every_non_predicted_type_succeeds(
        self, session: Session, measurement_fixtures: dict[str, str], evidence_type: str
    ) -> None:
        _insert_measurement(
            session,
            measurement_fixtures,
            measurement_uid=f"M{evidence_type[:24]:0>25}",
            evidence_type=evidence_type,
        )
        session.flush()  # must not raise


class TestMeasurementNullSemantics:
    """ck_status_value: the three null states never collapse (Step 2 §8.4)."""

    def test_measured_requires_canonical_value(
        self, session: Session, measurement_fixtures: dict[str, str]
    ) -> None:
        with pytest.raises(IntegrityError, match="ck_status_value"):
            _insert_measurement(
                session, measurement_fixtures, measurement_status="measured", canonical_value=None
            )
            session.flush()

    def test_not_measured_permits_null_value(
        self, session: Session, measurement_fixtures: dict[str, str]
    ) -> None:
        _insert_measurement(
            session, measurement_fixtures, measurement_status="not_measured", canonical_value=None
        )
        session.flush()  # must not raise

    def test_below_loq_requires_loq_value(
        self, session: Session, measurement_fixtures: dict[str, str]
    ) -> None:
        with pytest.raises(IntegrityError, match="ck_status_value"):
            session.execute(
                text(
                    "INSERT INTO measurement (measurement_uid, license_tier, "
                    "compound_uid, endpoint_id, canonical_unit, unit_verified_method, "
                    "measurement_status, evidence_type, source_id, snapshot_id, "
                    "source_license, is_commercial_ok, pipeline_version, "
                    "drugsim_release, created_by) "
                    "VALUES ('M' || repeat('1', 25), 'amber', :compound_uid, "
                    ":endpoint_id, 'unitless', 'documented', 'below_loq', "
                    "'experimental', :source_id, :snapshot_id, 'CC-BY-4.0', true, "
                    ":pv, '0.1.0', :created_by)"
                ),
                {**measurement_fixtures, "pv": "f" * 40},
            )
            session.flush()


class TestCensoringPreserved:
    """value_relation defaults to '=' but censored records must be representable."""

    @pytest.mark.parametrize("relation", ["=", "<", "<=", ">", ">=", "~"])
    def test_every_relation_is_valid(
        self, session: Session, measurement_fixtures: dict[str, str], relation: str
    ) -> None:
        _insert_measurement(
            session,
            measurement_fixtures,
            measurement_uid=f"M{relation.replace('=', 'EQ').replace('<', 'LT').replace('>', 'GT').replace('~', 'TL'):0>25}",
            value_relation=relation,
        )
        session.flush()  # must not raise


class TestMeasurementPartitioning:
    """Rows route to the correct license_tier partition and the licence audit
    (LC-03) can therefore be a partition scan."""

    @pytest.mark.parametrize("tier", ["green", "amber", "red", "black"])
    def test_row_lands_in_matching_partition(
        self, session: Session, measurement_fixtures: dict[str, str], tier: str
    ) -> None:
        _insert_measurement(
            session,
            measurement_fixtures,
            measurement_uid=f"M{tier.upper():0>25}",
            license_tier=tier,
            evidence_type="experimental" if tier != "black" else "expert_curated",
            is_commercial_ok=(tier != "black"),
        )
        session.flush()

        partition = session.execute(
            text(
                "SELECT tableoid::regclass::text FROM measurement "
                "WHERE measurement_uid = :uid"
            ),
            {"uid": f"M{tier.upper():0>25}"},
        ).scalar_one()
        assert partition == f"measurement_{tier}"


class TestEndpointDirectionRequirement:
    """ck_direction: continuous non-physicochemical endpoints must state a
    direction — this is what forces the LD50 sign-convention decision to be
    made explicitly rather than assumed (Phase 1 Step 2 §G.1)."""

    def test_continuous_toxicity_endpoint_requires_direction(self, session: Session) -> None:
        with pytest.raises(IntegrityError, match="ck_direction"):
            insert_endpoint(
                session,
                "ld50_bad",
                endpoint_class="toxicity",
                is_categorical=False,
                higher_is_worse=None,
                expected_min=0,
                expected_max=10000,
            )
            session.flush()

    def test_physicochemical_endpoint_may_omit_direction(self, session: Session) -> None:
        """The Step 4 §1 relaxation: logD/logS have no universal direction."""
        insert_endpoint(
            session,
            "logd_test",
            endpoint_class="physicochemical",
            is_categorical=False,
            higher_is_worse=None,
            expected_min=-10,
            expected_max=15,
        )
        session.flush()  # must not raise

    def test_categorical_endpoint_may_omit_bounds_and_direction(self, session: Session) -> None:
        insert_endpoint(
            session,
            "binary_test",
            is_categorical=True,
            higher_is_worse=None,
            expected_min=None,
            expected_max=None,
        )
        session.flush()  # must not raise
