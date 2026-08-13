#!/bin/bash
# Verify the RDKit cartridge is present in the image.
#
# Runs once on first initialisation of a fresh data directory. This is a smoke test
# of the IMAGE, not a schema step — extensions are created by Alembic migration so
# that extension state lives in migration history (see Dockerfile.postgres-rdkit).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-'EOSQL'
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'rdkit') THEN
            RAISE EXCEPTION
                'RDKit cartridge is not available in this image. The database is '
                'unusable for DrugSim: substructure and similarity search depend on '
                'it (ADR-003).';
        END IF;
        RAISE NOTICE 'RDKit cartridge available.';
    END
    $$;
EOSQL
