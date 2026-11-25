import sqlite3
from pathlib import Path


class SessionOwnershipError(ValueError):
    """Raised when one demo customer attempts to reuse another customer's session."""


class SessionOwnerStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS session_owners (
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )"""
            )

    def bind(self, session_id: str, customer_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO session_owners (session_id, customer_id) VALUES (?, ?)",
                (session_id, customer_id),
            )
            row = connection.execute(
                "SELECT customer_id FROM session_owners WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None or row["customer_id"] != customer_id:
            raise SessionOwnershipError("session does not belong to this customer")

    def verify(self, session_id: str, customer_id: str) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT customer_id FROM session_owners WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None or row["customer_id"] != customer_id:
            raise SessionOwnershipError("session does not belong to this customer")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection
