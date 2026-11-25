import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.schemas import DailyChatCount, EscalationRecord, IntentCount, TopQuestion, UnresolvedQuery


class AnalyticsStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    resolved INTEGER NOT NULL,
                    escalated INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS escalation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    ticket_id TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            escalation_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(escalation_events)")
            }
            if "status" not in escalation_columns:
                connection.execute(
                    "ALTER TABLE escalation_events "
                    "ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'"
                )

    def log_chat(
        self,
        customer_id: str,
        session_id: str,
        question: str,
        intent: str,
        resolved: bool,
        escalated: bool,
        escalation_summary: str | None,
        tool_calls: list[dict[str, str]],
    ) -> None:
        created_at = datetime.now(UTC).isoformat()
        ticket_id = _ticket_id(tool_calls)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO chat_events
                   (customer_id, session_id, question, intent, resolved, escalated, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    customer_id,
                    session_id,
                    question,
                    intent,
                    int(resolved),
                    int(escalated),
                    created_at,
                ),
            )
            if escalated and escalation_summary:
                connection.execute(
                    """INSERT INTO escalation_events
                       (customer_id, session_id, summary, ticket_id, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (customer_id, session_id, escalation_summary, ticket_id, created_at),
                )

    def summary(
        self, top_limit: int = 10, unresolved_limit: int = 50
    ) -> tuple[int, int, int, list[TopQuestion], list[UnresolvedQuery]]:
        with self._connect() as connection:
            totals = connection.execute(
                """SELECT COUNT(*) AS chats,
                          COALESCE(SUM(resolved), 0) AS resolved,
                          COALESCE(SUM(escalated), 0) AS escalated
                   FROM chat_events"""
            ).fetchone()
            top_rows = connection.execute(
                """SELECT MIN(question) AS question, COUNT(*) AS count
                   FROM chat_events GROUP BY lower(trim(question))
                   ORDER BY count DESC, question ASC LIMIT ?""",
                (top_limit,),
            ).fetchall()
            unresolved_rows = connection.execute(
                """SELECT question, intent, session_id, created_at FROM chat_events
                   WHERE resolved = 0 ORDER BY id DESC LIMIT ?""",
                (unresolved_limit,),
            ).fetchall()
        top_questions = [TopQuestion.model_validate(dict(row)) for row in top_rows]
        unresolved = [UnresolvedQuery.model_validate(dict(row)) for row in unresolved_rows]
        return (
            int(totals["chats"]),
            int(totals["resolved"]),
            int(totals["escalated"]),
            top_questions,
            unresolved,
        )

    def escalations(self, limit: int = 100) -> list[EscalationRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id, session_id, customer_id, summary, ticket_id, created_at, status
                   FROM escalation_events ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [EscalationRecord.model_validate(dict(row)) for row in rows]

    def decide_escalation(self, escalation_id: int, decision: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM escalation_events WHERE id = ?", (escalation_id,)
            ).fetchone()
            if row is None:
                raise LookupError("Escalation not found")
            current_status = str(row["status"])
            if current_status == decision:
                return current_status
            if current_status != "pending":
                raise ValueError(f"Escalation was already {current_status}")
            connection.execute(
                "UPDATE escalation_events SET status = ? WHERE id = ? AND status = 'pending'",
                (decision, escalation_id),
            )
        return decision

    def has_open_escalation(self, customer_id: str, session_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT 1 FROM escalation_events
                   WHERE customer_id = ? AND session_id = ?
                     AND status IN ('pending', 'accepted')
                   ORDER BY id DESC LIMIT 1""",
                (customer_id, session_id),
            ).fetchone()
        return row is not None

    def close_open_escalation(self, customer_id: str, session_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE escalation_events SET status = 'closed'
                   WHERE id = (
                       SELECT id FROM escalation_events
                       WHERE customer_id = ? AND session_id = ?
                         AND status IN ('pending', 'accepted')
                       ORDER BY id DESC LIMIT 1
                   )""",
                (customer_id, session_id),
            )
        return cursor.rowcount > 0

    def intent_counts(self) -> list[IntentCount]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT intent, COUNT(*) AS count FROM chat_events GROUP BY intent "
                "ORDER BY count DESC, intent ASC"
            ).fetchall()
        return [IntentCount.model_validate(dict(row)) for row in rows]

    def daily_chats(self, days: int = 14) -> list[DailyChatCount]:
        if days < 1:
            raise ValueError("days must be positive")
        today = datetime.now(UTC).date()
        start_day = today - timedelta(days=days - 1)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT date(created_at) AS date, COUNT(*) AS chats FROM chat_events "
                "WHERE date(created_at) >= ? GROUP BY date(created_at)",
                (start_day.isoformat(),),
            ).fetchall()
        counts = {str(row["date"]): int(row["chats"]) for row in rows}
        return [
            DailyChatCount(
                date=(start_day + timedelta(days=offset)).isoformat(),
                chats=counts.get((start_day + timedelta(days=offset)).isoformat(), 0),
            )
            for offset in range(days)
        ]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection


def _ticket_id(tool_calls: list[dict[str, str]]) -> str | None:
    for call in tool_calls:
        if call.get("name") != "create_ticket":
            continue
        summary = call.get("summary", "")
        try:
            result = json.loads(summary)
        except (json.JSONDecodeError, TypeError):
            continue
        ticket_id = result.get("ticket_id") if isinstance(result, dict) else None
        if isinstance(ticket_id, str):
            return ticket_id
    return None
