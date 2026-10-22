"""Ordered, checksummed SQL migrations for the local SQLite repository.

Migrations are plain ``NNNN_name.sql`` files shipped with the package. The
runner records each version, name, checksum, and application timestamp in
``schema_migrations``. An already-applied migration whose bytes changed is
refused rather than silently reinterpreted.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pipeline.fingerprints import canonical_datetime, sha256_bytes
from pipeline.storage.database import Database
from pipeline.storage.errors import MigrationChecksumError, MigrationError

MIGRATION_FILE_PATTERN = re.compile(
    r"^(?P<version>[0-9]{4})_(?P<name>[a-z0-9_]+)\.sql$"
)
DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


@dataclass(frozen=True, slots=True)
class Migration:
    """One discoverable SQL migration file."""

    version: int
    name: str
    path: Path
    checksum: str


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    """One row recorded in ``schema_migrations``."""

    version: int
    name: str
    checksum: str
    applied_at: str


@dataclass(frozen=True, slots=True)
class MigrationStatus:
    """Current migration state without changing the schema."""

    database_path: Path
    applied: tuple[AppliedMigration, ...]
    pending: tuple[Migration, ...]

    @property
    def current_version(self) -> int:
        return max((migration.version for migration in self.applied), default=0)

    @property
    def is_up_to_date(self) -> bool:
        return not self.pending


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Outcome of one migration run."""

    applied: tuple[Migration, ...]
    current_version: int

    @property
    def changed(self) -> bool:
        return bool(self.applied)


def discover_migrations(
    directory: Path = DEFAULT_MIGRATIONS_DIR,
) -> tuple[Migration, ...]:
    """Return migration files in strict ascending version order."""

    if not directory.is_dir():
        raise MigrationError(f"migration directory does not exist: {directory}")
    discovered: list[Migration] = []
    versions: set[int] = set()
    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_FILE_PATTERN.match(path.name)
        if match is None:
            raise MigrationError(
                "migration file names must match NNNN_name.sql: " + path.name
            )
        version = int(match.group("version"))
        if version < 1:
            raise MigrationError(f"migration versions start at 1: {path.name}")
        if version in versions:
            raise MigrationError(f"duplicate migration version {version}")
        versions.add(version)
        data = path.read_bytes()
        discovered.append(
            Migration(
                version=version,
                name=match.group("name"),
                path=path,
                checksum=sha256_bytes(data),
            )
        )
    discovered.sort(key=lambda migration: migration.version)
    for expected, migration in enumerate(discovered, start=1):
        if migration.version != expected:
            raise MigrationError(
                "migration versions must be contiguous from 0001; "
                f"expected {expected:04d}, found {migration.version:04d}"
            )
    return tuple(discovered)


class MigrationRunner:
    """Apply and inspect the ordered migration set for one database."""

    def __init__(
        self,
        database: Database,
        *,
        migrations_dir: Path = DEFAULT_MIGRATIONS_DIR,
    ) -> None:
        self.database = database
        self.migrations_dir = Path(migrations_dir)
        self._migrations = discover_migrations(self.migrations_dir)

    @property
    def migrations(self) -> tuple[Migration, ...]:
        return self._migrations

    def _ensure_migration_table(self) -> None:
        with self.database.transaction() as connection:
            connection.execute(_SCHEMA_MIGRATIONS_SQL)

    def _read_applied(self) -> tuple[AppliedMigration, ...]:
        self._ensure_migration_table()
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT version, name, checksum, applied_at "
                "FROM schema_migrations ORDER BY version"
            ).fetchall()
        return tuple(
            AppliedMigration(
                version=int(row[0]),
                name=str(row[1]),
                checksum=str(row[2]),
                applied_at=str(row[3]),
            )
            for row in rows
        )

    def _validate_applied(self, applied: tuple[AppliedMigration, ...]) -> None:
        by_version = {migration.version: migration for migration in self._migrations}
        for index, record in enumerate(applied):
            migration = by_version.get(record.version)
            if migration is None:
                raise MigrationError(
                    f"applied migration {record.version} has no local file"
                )
            if migration.version != index + 1:
                raise MigrationError(
                    "applied migration history is not a prefix of the local "
                    f"migration set at version {record.version}"
                )
            if migration.name != record.name:
                raise MigrationChecksumError(
                    f"migration {record.version:04d} was recorded as "
                    f"{record.name!r} but the local file is {migration.name!r}"
                )
            if migration.checksum != record.checksum:
                raise MigrationChecksumError(
                    f"migration {record.version:04d}_{record.name}.sql changed "
                    "after it was applied; add a new migration instead"
                )

    def status(self) -> MigrationStatus:
        """Report applied and pending migrations without applying any."""

        applied = self._read_applied()
        self._validate_applied(applied)
        pending = tuple(
            migration
            for migration in self._migrations
            if migration.version > (applied[-1].version if applied else 0)
        )
        return MigrationStatus(
            database_path=self.database.path,
            applied=applied,
            pending=pending,
        )

    def migrate(self) -> MigrationResult:
        """Apply every pending migration once and return what changed."""

        status = self.status()
        applied_now: list[Migration] = []
        for migration in status.pending:
            try:
                with self.database.transaction() as connection:
                    existing = connection.execute(
                        "SELECT name, checksum FROM schema_migrations "
                        "WHERE version = ?",
                        (migration.version,),
                    ).fetchone()
                    if existing is not None:
                        if (
                            str(existing[0]) != migration.name
                            or str(existing[1]) != migration.checksum
                        ):
                            raise MigrationChecksumError(
                                f"migration {migration.version:04d} changed "
                                "while applying"
                            )
                        continue
                    _execute_sql_script(
                        connection, migration.path.read_text(encoding="utf-8")
                    )
                    connection.execute(
                        "INSERT INTO schema_migrations "
                        "(version, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
                        (
                            migration.version,
                            migration.name,
                            migration.checksum,
                            canonical_datetime(datetime.now(UTC)),
                        ),
                    )
            except sqlite3.Error as error:
                raise MigrationError(
                    f"migration {migration.version:04d}_{migration.name} failed: "
                    f"{error}"
                ) from error
            applied_now.append(migration)
        current = self.status().current_version
        return MigrationResult(applied=tuple(applied_now), current_version=current)


def _execute_sql_script(connection: sqlite3.Connection, script: str) -> None:
    """Execute a SQL script without ``executescript``'s implicit commit."""

    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                connection.execute(statement)
            buffer = ""
    remainder = buffer.strip()
    if remainder:
        connection.execute(remainder)


__all__ = [
    "DEFAULT_MIGRATIONS_DIR",
    "MIGRATION_FILE_PATTERN",
    "AppliedMigration",
    "Migration",
    "MigrationResult",
    "MigrationRunner",
    "MigrationStatus",
    "discover_migrations",
]
