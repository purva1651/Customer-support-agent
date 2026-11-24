from pathlib import Path
from typing import Any

import pytest
import yaml
from langchain_core.tools import tool

from app.agent.router import ActionSelector, IntentRouter
from app.config import load_runtime_files
from app.llm.factory import create_chat_model

ROOT = Path(__file__).resolve().parents[2]


@tool("get_booking_status")
def get_booking_status(booking_id: str) -> dict[str, str]:
    """Get the status and details of a customer's booking."""
    return {"booking_id": booking_id, "status": "confirmed"}


@tool("create_ticket")
def create_ticket(subject: str, details: str) -> dict[str, str]:
    """Create a customer support ticket."""
    return {"ticket_id": "T-1001"}


@tool("update_contact")
def update_contact(email: str | None = None, phone: str | None = None) -> dict[str, str]:
    """Update a customer's contact email or phone number."""
    return {"email": email or "", "phone": phone or ""}


@tool("cancel_booking")
def cancel_booking(booking_id: str) -> dict[str, str]:
    """Cancel a booking after the customer approves the action."""
    return {"booking_id": booking_id, "status": "cancelled"}


@pytest.mark.eval
def test_live_router_and_tool_eval_cases() -> None:
    files = load_runtime_files()
    model = create_chat_model(files.config)
    router = IntentRouter(model, files.prompts, files.intents)
    selector = ActionSelector(
        model,
        files.prompts,
        files.tool_settings,
    )
    tools: dict[str, Any] = {
        "get_booking_status": get_booking_status,
        "create_ticket": create_ticket,
        "update_contact": update_contact,
        "cancel_booking": cancel_booking,
    }
    cases = yaml.safe_load((ROOT / "tests/evals/cases.yaml").read_text(encoding="utf-8"))
    failures: list[str] = []

    for case in cases:
        decision = router.classify(case["input"], [])
        if decision.intent != case["expected_intent"]:
            failures.append(
                f"intent for {case['input']!r}: expected {case['expected_intent']}, "
                f"got {decision.intent}"
            )
        expected_tool = case["expected_tool"]
        if decision.intent == "action" and expected_tool:
            selection = selector.select(case["input"], tools)
            if selection.tool_name != expected_tool:
                failures.append(
                    f"tool for {case['input']!r}: expected {expected_tool}, "
                    f"got {selection.tool_name}"
                )

    assert not failures, "\n".join(failures)
