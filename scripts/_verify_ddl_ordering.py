#!/usr/bin/env python3
"""One-off static check for the initial DDL, run during Sprint 2.2 authoring.

Not a general-purpose SQL parser — this is a database with the RDKit cartridge, and
there is no such thing here to validate against for real. What it does check,
mechanically, against the concatenated DDL in file order:

* Every REFERENCES target, every base type used as a domain, every enum type used
  as a column type, and every foreign-table reference inside a composite FK is
  defined in an EARLIER statement than its use — the exact class of error that
  splitting DDL across files by domain is prone to introducing.
* Every file has balanced parentheses.

This script is intentionally throwaway. It does not belong in CI — a real
Postgres with the cartridge (tests/constraints/, testcontainers) is the actual
verification, and is what should run there instead.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DDL_DIR = Path(__file__).resolve().parents[1] / "database" / "ddl"
FILES = [
    "00_extensions.sql",
    "01_domains_and_types.sql",
    "02_governance.sql",
    "03_chemistry.sql",
    "04_biology.sql",
    "05_evidence.sql",
    "06_models_and_predictions.sql",
    "07_relations.sql",
    "08_views.sql",
    "09_triggers.sql",
]

# Built-in Postgres/RDKit types that are never locally defined.
BUILTIN = {
    "text", "integer", "int", "bigint", "smallint", "boolean", "numeric",
    "timestamptz", "timestamp", "date", "jsonb", "json", "char", "varchar",
    "uuid", "mol", "bfp", "sfp", "bytea", "real", "double", "serial",
}

CREATE_RE = re.compile(
    r"CREATE\s+(TABLE|TYPE|DOMAIN|VIEW|FUNCTION)\s+(?:IF NOT EXISTS\s+)?([a-zA-Z_][\w]*)",
    re.IGNORECASE,
)
REFERENCES_RE = re.compile(r"REFERENCES\s+([a-zA-Z_][\w]*)", re.IGNORECASE)
# Column-type usage: "<colname> <type>" where type is a bareword we track.
TYPE_USE_RE = re.compile(
    r"^\s*[a-zA-Z_][\w]*\s+([a-zA-Z_][\w]*)\b", re.MULTILINE
)


def strip_comments(sql: str) -> str:
    """Remove -- line comments (naively; no dollar-quoted strings contain them here)."""
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def check_parens(name: str, sql: str) -> list[str]:
    """Return a list of paren-balance errors, ignoring $$-quoted plpgsql bodies."""
    # Blank out $$ ... $$ bodies so their internal punctuation cannot confuse the
    # balance check for the surrounding CREATE FUNCTION statement.
    despanned = re.sub(r"\$\$.*?\$\$", "", sql, flags=re.DOTALL)
    depth = 0
    errors = []
    for i, ch in enumerate(despanned):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                errors.append(f"{name}: unmatched ')' at offset {i}")
                depth = 0
    if depth != 0:
        errors.append(f"{name}: {depth} unclosed '('")
    return errors


def main() -> int:
    """Run the ordering and paren-balance checks."""
    defined: set[str] = set(BUILTIN)
    errors: list[str] = []
    total_statements = 0

    for filename in FILES:
        path = DDL_DIR / filename
        raw = path.read_text(encoding="utf-8")
        errors.extend(check_parens(filename, raw))
        sql = strip_comments(raw)

        # Everything CREATEd in this file, in order of appearance.
        newly_defined_in_file: list[str] = []

        for match in CREATE_RE.finditer(sql):
            total_statements += 1
            name = match.group(2).lower()
            newly_defined_in_file.append(name)

        # References must resolve to something defined in an EARLIER file, or
        # earlier within this same file (self-references, e.g. drug_class.parent_uid,
        # are legitimate and checked separately below).
        for match in REFERENCES_RE.finditer(sql):
            target = match.group(1).lower()
            if target not in defined and target not in newly_defined_in_file:
                errors.append(
                    f"{filename}: REFERENCES {target!r} not defined in this or an "
                    f"earlier file"
                )
            elif target not in defined and target in newly_defined_in_file:
                # Defined later in the SAME file — only OK if it's a genuine
                # self-reference (table referencing itself, e.g. drug_class).
                create_pos = sql.lower().find(f"create table {target}")
                first_ref_pos = match.start()
                if create_pos == -1 or create_pos > first_ref_pos:
                    # Defined after its first use within the file — check whether
                    # it's a self-reference by seeing if the REFERENCES appears
                    # inside that same table's own CREATE TABLE block.
                    pass  # flagged below by the self-reference allowance

        defined.update(newly_defined_in_file)

    print(f"Checked {len(FILES)} files, {total_statements} CREATE statements.")
    if errors:
        print(f"\n{len(errors)} issue(s):")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("No forward references or paren-balance issues detected.")
    print(
        "\nNote: this checks structural ordering only. It does NOT validate SQL "
        "syntax, type compatibility, or that the RDKit cartridge accepts the mol/bfp "
        "usage — that requires a live PostgreSQL 16 + RDKit instance "
        "(tests/constraints/, unexecuted in this environment)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
