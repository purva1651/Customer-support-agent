from pathlib import Path

import pytest

from app.agent.memory import SessionOwnershipError, SessionOwnerStore


def test_session_memory_is_bound_to_one_customer(tmp_path: Path) -> None:
    owners = SessionOwnerStore(tmp_path / "checkpoints.sqlite")
    owners.bind("session-1", "C001")
    owners.bind("session-1", "C001")

    with pytest.raises(SessionOwnershipError):
        owners.bind("session-1", "C002")
