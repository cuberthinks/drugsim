# DrugSim application image: API, workers, ETL, CLI.
#
# Multi-stage so the runtime image carries no build toolchain. Runs non-root with a
# read-only root filesystem in deployment (TDS §10.3).

# --------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.5 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends build-essential curl; \
    rm -rf /var/lib/apt/lists/*; \
    pip install "poetry==${POETRY_VERSION}"

# WORKDIR matches the runtime stage's (/app), not an arbitrary /build --
# poetry's default root-package install can be editable (a path reference
# back to this exact source location, not a physical copy into
# site-packages), so the source tree must live at the SAME absolute path
# in both stages, or an editable install silently breaks at runtime with
# nothing at the referenced path (found and fixed in Phase 8 while
# building Dockerfile.predict-api against the same pattern).
WORKDIR /app

# Dependency layer, cached independently of source changes.
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY src/ ./src/
RUN poetry install --only main

# --------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# libgomp is required by RDKit's compiled extensions.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends libgomp1; \
    rm -rf /var/lib/apt/lists/*; \
    groupadd --gid 1000 drugsim; \
    useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin drugsim

WORKDIR /app

COPY --from=builder --chown=drugsim:drugsim /app/.venv /app/.venv
COPY --from=builder --chown=drugsim:drugsim /app/src /app/src
COPY --from=builder --chown=drugsim:drugsim /app/pyproject.toml /app/poetry.lock /app/
COPY --chown=drugsim:drugsim config/ /app/config/
COPY --chown=drugsim:drugsim datasets/registry.yaml /app/datasets/registry.yaml
COPY --chown=drugsim:drugsim database/ /app/database/

USER drugsim

# Fails the build if the package tree is not importable.
RUN python -c "import drugsim_core; print(drugsim_core.__version__)"

ENTRYPOINT ["drugsim"]
CMD ["--help"]
