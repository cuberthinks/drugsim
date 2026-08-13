-- DrugSim — Extensions
-- Phase 1 ADR-003: the RDKit cartridge is the reason Postgres is self-managed
-- (unavailable on RDS/Cloud SQL/Aurora). It is what makes substructure (@>) and
-- Tanimoto (%) search possible in SQL with GiST indexes, over ~3M compounds,
-- instead of an application-layer scan.

CREATE EXTENSION IF NOT EXISTS rdkit;

-- Required for gen_random_uuid(), used by audit_log.audit_uid.
-- See database/ddl/README.md "Implementation notes" for why audit rows use UUID
-- rather than the application-generated ulid domain.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'rdkit') THEN
        RAISE EXCEPTION
            'RDKit cartridge failed to install. DrugSim cannot function without it '
            '(ADR-003) — check that the postgres-rdkit image is in use, not stock '
            'postgres:16.';
    END IF;
END $$;
