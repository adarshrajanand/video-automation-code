"""Ordered, checksummed SQL migrations for the local SQLite repository.

Migrations are plain ``NNNN_name.sql`` files shipped with the package. The
runner records each version, name, checksum, and application timestamp in
``schema_migrations``. An already-applied migration whose bytes changed is
refused rather than silently reinterpreted.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pipeline.fingerprints import sha256_bytes, unix_microseconds
from pipeline.storage.backfill import canonicalize_persisted_timestamps
from pipeline.storage.database import Database
from pipeline.storage.errors import MigrationChecksumError, MigrationError
from pipeline.storage.timestamp_migration import (
    _parse_iso_microseconds,
    convert_timestamp_columns_to_microseconds,
    require_reset_only_database,
)

MIGRATION_FILE_PATTERN = re.compile(
    r"^(?P<version>[0-9]{4})_(?P<name>[a-z0-9_]+)\.sql$"
)
DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_timestamp_micro INTEGER NOT NULL
)
"""

# Data-only migrations keep their SQL file as the version/checksum anchor while
# structured JSON and timezone-aware repairs run here inside the same transaction.
#
# 0002 is intentionally a comment-only SQL anchor. SQLite cannot parse and
# validate JSON through Pydantic, nor can it convert timezone offsets while
# preserving six fractional digits. The Python hook below performs that work.
# Do not add logic to an applied migration file; add a new migration instead.
_DATA_MIGRATION_HOOKS: dict[tuple[int, str], Callable[[sqlite3.Connection], None]] = {
    (2, "canonical_timestamps"): canonicalize_persisted_timestamps,
    # #92 changes the persisted representation, not just names. The SQL file is
    # a comment-only anchor because exact ISO-8601 -> integer conversion needs
    # Python; the hook refuses databases with durable rows and points at the
    # documented reset procedure. See timestamp_migration.py.
    (3, "timestamp_micros"): convert_timestamp_columns_to_microseconds,
}

# Migrations in this set destroy and rebuild the schema, so they can only run
# against an empty database. The check runs as a ``migrate()`` preflight because
# an earlier pending migration's hook could otherwise mutate durable rows before
# the guard rejects the run. ``status()`` stays read-only by design.
_RESET_ONLY_MIGRATIONS: frozenset[tuple[int, str]] = frozenset(
    {(3, "timestamp_micros")}
)


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
    applied_timestamp_micro: int


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
            try:
                rows = connection.execute(
                    "SELECT version, name, checksum, applied_timestamp_micro "
                    "FROM schema_migrations ORDER BY version"
                ).fetchall()
            except sqlite3.OperationalError:
                # Legacy schema has `applied_at` as TEXT.
                rows = connection.execute(
                    "SELECT version, name, checksum, applied_at "
                    "FROM schema_migrations ORDER BY version"
                ).fetchall()
                # Convert ISO-8601 string to integer microseconds.
                rows = [
                    (
                        int(row[0]),
                        str(row[1]),
                        str(row[2]),
                        _parse_iso_microseconds(row[3], table="schema_migrations"),
                    )
                    for row in rows
                ]
            return tuple(
                AppliedMigration(
                    version=int(row[0]),
                    name=str(row[1]),
                    checksum=str(row[2]),
                    applied_timestamp_micro=int(row[3]),
                )
                for row in rows
            )

    def _validate_applied(self, applied: tuple[AppliedMigration, ...]) -> None:
        """Fail closed when applied history diverges from local migration files.

        An applied migration is immutable: the stored checksum is its contract.
        To undo an edit, restore the exact applied bytes. If the modified file
        was already applied to a development database, recreate that database;
        never rewrite ``schema_migrations`` by hand.
        """

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
        if any(
            (migration.version, migration.name) in _RESET_ONLY_MIGRATIONS
            for migration in status.pending
        ):
            # Refuse before applying any pending migration so a populated
            # database is not partially rewritten on the way to a migration that
            # can only run empty. See timestamp_migration.py for the reset policy.
            with self.database.connection() as connection:
                require_reset_only_database(connection)
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
                    hook = _DATA_MIGRATION_HOOKS.get(
                        (migration.version, migration.name)
                    )
                    if hook is not None:
                        try:
                            hook(connection)
                        except Exception as error:
                            raise MigrationError(
                                f"migration {migration.version:04d}_"
                                f"{migration.name} failed: {error}"
                            ) from error
                    connection.execute(
                        "INSERT INTO schema_migrations "
                        "(version, name, checksum, applied_timestamp_micro) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            migration.version,
                            migration.name,
                            migration.checksum,
                            unix_microseconds(datetime.now(UTC)),
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
