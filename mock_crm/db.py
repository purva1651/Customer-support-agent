import os
import sqlite3
from pathlib import Path
from typing import Any

from mock_crm.seed import BOOKINGS, CUSTOMERS

DEFAULT_DB_PATH = Path("data/mock_crm.sqlite3")


def database_path() -> Path:
    return Path(os.environ.get("CRM_DB_PATH", str(DEFAULT_DB_PATH)))


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(path: Path | None = None) -> None:
    with connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT
            );
            CREATE TABLE IF NOT EXISTS bookings (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL REFERENCES customers(id),
                route TEXT NOT NULL,
                departs_at TEXT NOT NULL,
                seat TEXT NOT NULL,
                amount REAL NOT NULL CHECK (amount >= 0),
                status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL REFERENCES customers(id),
                subject TEXT NOT NULL,
                details TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            """
        )
        connection.executemany(
            """INSERT OR IGNORE INTO customers (id, name, email, phone)
               VALUES (:id, :name, :email, :phone)""",
            CUSTOMERS,
        )
        connection.executemany(
            """INSERT OR IGNORE INTO bookings
               (id, customer_id, route, departs_at, seat, amount, status)
               VALUES (:id, :customer_id, :route, :departs_at, :seat, :amount, :status)""",
            BOOKINGS,
        )


def fetch_booking(booking_id: str, customer_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM bookings WHERE id = ? AND customer_id = ?",
            (booking_id, customer_id),
        ).fetchone()
    return dict(row) if row else None


def cancel_booking(booking_id: str, customer_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM bookings WHERE id = ? AND customer_id = ?",
            (booking_id, customer_id),
        ).fetchone()
        if row is None:
            return None
        if row["status"] == "cancelled":
            raise ValueError("booking is already cancelled")
        fee = round(float(row["amount"]) * 0.10, 2)
        refund_amount = round(float(row["amount"]) - fee, 2)
        connection.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
        booking = dict(row)
        booking["status"] = "cancelled"
    return {"booking": booking, "fee": fee, "refund_amount": refund_amount}


def customer_exists(customer_id: str) -> bool:
    with connect() as connection:
        row = connection.execute("SELECT 1 FROM customers WHERE id = ?", (customer_id,)).fetchone()
    return row is not None


def create_ticket(customer_id: str, subject: str, details: str) -> dict[str, Any]:
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO tickets (customer_id, subject, details, status) VALUES (?, ?, ?, 'open')",
            (customer_id, subject, details),
        )
        row = connection.execute(
            "SELECT * FROM tickets WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    result = dict(row)
    result["ticket_id"] = f"T-{1000 + int(result.pop('id'))}"
    return result


def update_contact(customer_id: str, updates: dict[str, str | None]) -> dict[str, Any] | None:
    allowed_fields = {"email", "phone"}
    if not updates or not set(updates).issubset(allowed_fields):
        raise ValueError("contact updates may include email and/or phone")
    fields = {field: value for field, value in updates.items() if value is not None}
    if not fields:
        raise ValueError("at least one contact value is required")
    assignments = ", ".join(f"{field} = ?" for field in fields)
    with connect() as connection:
        cursor = connection.execute(
            f"UPDATE customers SET {assignments} WHERE id = ?",
            (*fields.values(), customer_id),
        )
        if cursor.rowcount == 0:
            return None
        row = connection.execute(
            "SELECT id, name, email, phone FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
    return dict(row)
