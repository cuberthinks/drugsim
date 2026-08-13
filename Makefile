# DrugSim development tasks.
.DEFAULT_GOAL := help
.PHONY: help install fmt lint type test test-security test-golden test-constraints test-all cov \
        up down logs psql clean audit docs db-upgrade db-current db-verify-rdkit golden-regenerate \
        quality-report

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies and pre-commit hooks
	poetry install --with dev
	poetry run pre-commit install

fmt:  ## Format code
	poetry run ruff format .
	poetry run ruff check --fix .

lint:  ## Lint without fixing
	poetry run ruff check .
	poetry run ruff format --check .

type:  ## Type-check (strict)
	poetry run mypy

test:  ## Run unit, security and golden tests (no Docker needed)
	DRUGSIM_ENVIRONMENT=test poetry run pytest -m "unit or security or golden" -v

test-security:  ## Run structure-disclosure controls only
	DRUGSIM_ENVIRONMENT=test poetry run pytest tests/security -v -m security

test-golden:  ## Run the golden-set chemistry regression only
	DRUGSIM_ENVIRONMENT=test poetry run pytest tests/golden -v -m golden

test-constraints:  ## Run database constraint tests (requires Docker)
	DRUGSIM_ENVIRONMENT=test poetry run pytest tests/constraints -v -m constraints

test-all:  ## Run the full suite including integration (requires Docker)
	DRUGSIM_ENVIRONMENT=test poetry run pytest -v

golden-regenerate:  ## Regenerate golden fixtures — ONLY after a reviewed, intended chemistry change
	poetry run python scripts/generate_golden_fixtures.py

quality-report:  ## Regenerate the Phase 2 data-quality report
	poetry run python scripts/generate_quality_report.py

cov:  ## Run tests with coverage
	DRUGSIM_ENVIRONMENT=test poetry run pytest --cov --cov-report=term-missing --cov-report=html

audit:  ## Audit dataset licences
	poetry run python scripts/audit_licenses.py

db-upgrade:  ## Apply pending migrations up to head
	poetry run drugsim db upgrade

db-current:  ## Show the current database revision
	poetry run drugsim db current

db-verify-rdkit:  ## Assert the RDKit cartridge is installed
	poetry run drugsim db verify-rdkit

up:  ## Start the local stack
	docker compose -f deployment/compose/docker-compose.yml up -d --build

down:  ## Stop the local stack
	docker compose -f deployment/compose/docker-compose.yml down

logs:  ## Tail stack logs
	docker compose -f deployment/compose/docker-compose.yml logs -f

psql:  ## Open a psql shell
	docker compose -f deployment/compose/docker-compose.yml exec postgres psql -U drugsim -d drugsim

docs:  ## Serve documentation locally
	poetry run mkdocs serve

clean:  ## Remove caches and build artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
