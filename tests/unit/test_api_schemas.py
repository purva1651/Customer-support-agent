import pytest
from pydantic import ValidationError

from app.schemas import ApprovalRequest, ChatRequest, ChatResponse


def test_chat_request_accepts_supported_contract() -> None:
    request = ChatRequest(
        customer_id="C001",
        session_id="session-1",
        message="  Where is my booking?  ",
        language="Hindi",
    )
    assert request.message == "Where is my booking?"
    assert request.language == "Hindi"


@pytest.mark.parametrize(
    "payload",
    [
        {"customer_id": "C001", "session_id": "s1", "message": "   "},
        {"customer_id": "C001", "session_id": "s1", "message": "x" * 2001},
        {"customer_id": "C001", "session_id": "s1", "message": "Hello", "language": "French"},
        {"customer_id": "../C002", "session_id": "s1", "message": "Hello"},
    ],
)
def test_chat_request_rejects_invalid_input(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(payload)


def test_approval_and_chat_response_are_typed() -> None:
    approval = ApprovalRequest(action_id="act-1", approved=True)
    response = ChatResponse.model_validate(
        {"reply": "Here is the policy.", "intent": "question", "sources": [], "tool_calls": []}
    )
    assert approval.approved is True
    assert response.pending_action is None


def test_chat_response_rejects_invalid_source_url() -> None:
    with pytest.raises(ValidationError):
        ChatResponse.model_validate(
            {
                "reply": "See source.",
                "intent": "question",
                "sources": [{"title": "Policy", "url": "not-a-url"}],
            }
        )
