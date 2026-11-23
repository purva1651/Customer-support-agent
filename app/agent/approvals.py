import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ApprovalError(ValueError):
    """Base class for approval token validation failures."""


class UnknownApproval(ApprovalError):
    """The supplied action ID does not exist."""


class ExpiredApproval(ApprovalError):
    """The supplied action ID has expired."""


class UsedApproval(ApprovalError):
    """The supplied action ID was already used."""


@dataclass(frozen=True)
class ApprovedAction:
    action_id: str
    customer_id: str
    booking_id: str
    tool_name: str
    arguments: dict[str, Any]


class ApprovalStore:
    def __init__(self, path: Path, ttl_seconds: int = 600) -> None:
        if ttl_seconds <= 0:
            raise ValueError("approval token lifetime must be positive")
        self._path = path
        self._ttl_seconds = ttl_seconds
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS approval_actions (
                    action_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    booking_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    consumed_at REAL
                )"""
            )

    def create_pending(
        self,
        customer_id: str,
        booking_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        now: float | None = None,
    ) -> str:
        if tool_name != "cancel_booking":
            raise ValueError("only configured risky booking actions can require approval")
        if not customer_id or not booking_id or "customer_id" in arguments:
            raise ValueError(
                "approval must bind a customer and booking without model-supplied identity"
            )
        if arguments.get("booking_id") != booking_id:
            raise ValueError("approval booking must match the tool arguments")
        created_at = time.time() if now is None else now
        action_id = secrets.token_urlsafe(32)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO approval_actions
                   (action_id, customer_id, booking_id, tool_name,
                    arguments_json, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    action_id,
                    customer_id,
                    booking_id,
                    tool_name,
                    json.dumps(arguments, separators=(",", ":")),
                    created_at,
                    created_at + self._ttl_seconds,
                ),
            )
        return action_id

    def consume(
        self, action_id: str, approved: bool, now: float | None = None
    ) -> ApprovedAction | None:
        current_time = time.time() if now is None else now
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT customer_id, booking_id, tool_name, arguments_json,
                          expires_at, consumed_at
                   FROM approval_actions WHERE action_id = ?""",
                (action_id,),
            ).fetchone()
            if row is None:
                raise UnknownApproval("approval action not found")
            if row["consumed_at"] is not None:
                raise UsedApproval("approval action already used")
            if row["expires_at"] <= current_time:
                raise ExpiredApproval("approval action expired")
            connection.execute(
                "UPDATE approval_actions SET consumed_at = ? WHERE action_id = ?",
                (current_time, action_id),
            )
            if not approved:
                return None
            return ApprovedAction(
                action_id=action_id,
                customer_id=str(row["customer_id"]),
                booking_id=str(row["booking_id"]),
                tool_name=str(row["tool_name"]),
                arguments=json.loads(row["arguments_json"]),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection
