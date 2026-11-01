"""SQLite connection, pragma, and explicit transaction helpers.

Each :meth:`Database.connection` call opens a fresh connection. Repositories take
a connection explicitly so a caller can compose several writes inside one
:meth:`Database.transaction` block. Transactions use ``BEGIN IMMEDIATE`` by
default to acquire the write lock before reading state that a decision depends
on; callers may request a deferred transaction where immediate locking is not
wanted.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

DEFAULT_BUSY_TIMEOUT_MS = 5_000
MIN_BUSY_TIMEOUT_MS = 1
MAX_BUSY_TIMEOUT_MS = 60_000


class Database:
    """One local SQLite database file with fail-closed connection settings."""

    def __init__(
        self,
        path: Path | str,
        *,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        immediate_transactions: bool = True,
    ) -> None:
        if not MIN_BUSY_TIMEOUT_MS <= busy_timeout_ms <= MAX_BUSY_TIMEOUT_MS:
            raise ValueError(
                "busy_timeout_ms must be between "
                f"{MIN_BUSY_TIMEOUT_MS} and {MAX_BUSY_TIMEOUT_MS}"
            )
        self.path = Path(path).expanduser()
        self.busy_timeout_ms = busy_timeout_ms
        self.immediate_transactions = immediate_transactions

    def __repr__(self) -> str:
        return f"Database(path={str(self.path)!r})"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1_000,
            isolation_level=None,
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute(f"PRAGMA busy_timeout = {int(self.busy_timeout_ms)}")
            connection.execute("PRAGMA foreign_keys = ON")
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
            if foreign_keys is None or int(foreign_keys[0]) != 1:
                raise sqlite3.DatabaseError(
                    "SQLite did not enable foreign-key enforcement"
                )
            # WAL is the local baseline. In-memory or unusual builds may reject
            # it; the connection remains usable with the journal mode they pick.
            with suppress(sqlite3.DatabaseError):
                connection.execute("PRAGMA journal_mode = WAL")
            with suppress(sqlite3.DatabaseError):
                connection.execute("PRAGMA synchronous = NORMAL")
        except BaseException:
            connection.close()
            raise
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection and always close it afterwards."""

        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(
        self, *, immediate: bool | None = None
    ) -> Iterator[sqlite3.Connection]:
        """Yield one connection inside an explicit commit/rollback boundary.

        ``immediate=None`` uses the database-level default. Any exception rolls
        the whole transaction back before propagating. The connection is closed
        after the commit or rollback so a transaction can never leak across
        operations.
        """

        use_immediate = self.immediate_transactions if immediate is None else immediate
        begin_statement = "BEGIN IMMEDIATE" if use_immediate else "BEGIN"
        with self.connection() as connection:
            connection.execute(begin_statement)
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def journal_mode(self) -> str:
        """Return the active journal mode of a fresh connection."""

        with self.connection() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
        return str(row[0]).lower() if row is not None else "unknown"


__all__ = [
    "DEFAULT_BUSY_TIMEOUT_MS",
    "MAX_BUSY_TIMEOUT_MS",
    "MIN_BUSY_TIMEOUT_MS",
    "Database",
]
