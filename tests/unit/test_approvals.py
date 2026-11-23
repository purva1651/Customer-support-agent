from pathlib import Path

import pytest

from app.agent.approvals import (
    ApprovalStore,
    ExpiredApproval,
    UnknownApproval,
    UsedApproval,
)


def test_approval_token_is_bound_and_single_use(tmp_path: Path) -> None:
    store = ApprovalStore(tmp_path / "approvals.sqlite3", ttl_seconds=600)
    action_id = store.create_pending(
        "C001", "B001", "cancel_booking", {"booking_id": "B001"}, now=1000
    )

    action = store.consume(action_id, approved=True, now=1599)

    assert action is not None
    assert action.customer_id == "C001"
    assert action.booking_id == "B001"
    assert action.arguments == {"booking_id": "B001"}
    with pytest.raises(UsedApproval):
        store.consume(action_id, approved=True, now=1600)


def test_expired_and_unknown_approval_tokens_are_rejected(tmp_path: Path) -> None:
    store = ApprovalStore(tmp_path / "approvals.sqlite3", ttl_seconds=600)
    action_id = store.create_pending(
        "C001", "B001", "cancel_booking", {"booking_id": "B001"}, now=1000
    )

    with pytest.raises(ExpiredApproval):
        store.consume(action_id, approved=True, now=1600)
    with pytest.raises(UnknownApproval):
        store.consume("unknown", approved=True, now=1000)


def test_declining_approval_consumes_the_token(tmp_path: Path) -> None:
    store = ApprovalStore(tmp_path / "approvals.sqlite3", ttl_seconds=600)
    action_id = store.create_pending(
        "C001", "B001", "cancel_booking", {"booking_id": "B001"}, now=1000
    )

    assert store.consume(action_id, approved=False, now=1001) is None
    with pytest.raises(UsedApproval):
        store.consume(action_id, approved=True, now=1002)


def test_approval_rejects_identity_or_booking_tampering(tmp_path: Path) -> None:
    store = ApprovalStore(tmp_path / "approvals.sqlite3", ttl_seconds=600)
    with pytest.raises(ValueError, match="without model-supplied identity"):
        store.create_pending(
            "C001",
            "B001",
            "cancel_booking",
            {"booking_id": "B001", "customer_id": "C002"},
        )
    with pytest.raises(ValueError, match="must match"):
        store.create_pending("C001", "B001", "cancel_booking", {"booking_id": "B002"})
