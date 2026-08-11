"""Migration runner.

Migrations are plain SQL files applied in filename order and recorded in the
`schema_migrations` table, so a fresh database reaches the same schema as a
long-running one. Each file is a self-contained snapshot: it never references
Python constants, only literal table and column names.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("soulseek_charts.storage.migrations")

MIGRATIONS_DIRECTORY = Path(__file__).parent / "migrations"

SCHEMA_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations
(
    identifier String,
    name String,
    applied_at DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY identifier
"""


@dataclass(frozen=True)
class Migration:
    identifier: str
    name: str
    statements: tuple[str, ...]


def split_statements(sql_text: str) -> tuple[str, ...]:
    """Split a migration file into individual statements.

    ClickHouse accepts one statement per request, so files are separated on
    semicolons. Comment-only fragments are dropped.
    """
    statements: list[str] = []
    for raw_statement in sql_text.split(";"):
        meaningful_lines = [
            line
            for line in raw_statement.strip().splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        if meaningful_lines:
            statements.append(raw_statement.strip())
    return tuple(statements)


def discover_migrations(directory: Path = MIGRATIONS_DIRECTORY) -> tuple[Migration, ...]:
    """Read migration files in filename order, e.g. `0001_search_query_events.sql`."""
    migrations: list[Migration] = []
    for migration_path in sorted(directory.glob("*.sql")):
        identifier, _, name = migration_path.stem.partition("_")
        migrations.append(
            Migration(
                identifier=identifier,
                name=name,
                statements=split_statements(migration_path.read_text(encoding="utf-8")),
            )
        )
    return tuple(migrations)


def read_applied_identifiers(client: Any) -> set[str]:
    result = client.query("SELECT identifier FROM schema_migrations")
    return {str(row[0]) for row in result.result_rows}


def apply_migrations(
    client: Any,
    database: str,
    migrations: tuple[Migration, ...] | None = None,
) -> tuple[str, ...]:
    """Apply every migration not yet recorded. Returns the identifiers applied."""
    if migrations is None:
        migrations = discover_migrations()

    client.command(f"CREATE DATABASE IF NOT EXISTS {database}")
    client.command(f"USE {database}")
    client.command(SCHEMA_MIGRATIONS_TABLE)

    already_applied = read_applied_identifiers(client)
    newly_applied: list[str] = []

    for migration in migrations:
        if migration.identifier in already_applied:
            logger.debug("Migration %s already applied", migration.identifier)
            continue

        logger.info("Applying migration %s %s", migration.identifier, migration.name)
        for statement in migration.statements:
            client.command(statement)

        client.insert(
            "schema_migrations",
            [[migration.identifier, migration.name]],
            column_names=["identifier", "name"],
        )
        newly_applied.append(migration.identifier)

    return tuple(newly_applied)
