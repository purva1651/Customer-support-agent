import json

import httpx
import pytest

from frontend.api_client import APIError, SupportAPI


def test_chat_sends_request_contract_to_rest_api() -> None:
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200, json={"reply": "Policy answer", "intent": "question"})

    with SupportAPI(transport=httpx.MockTransport(handler)) as api:
        response = api.chat("C001", "session-1", "Refund policy?", "Gujarati")

    assert response["reply"] == "Policy answer"
    assert received[0].url.path == "/chat"
    assert json.loads(received[0].read()) == {
        "customer_id": "C001",
        "session_id": "session-1",
        "message": "Refund policy?",
        "language": "Gujarati",
    }


def test_admin_calls_add_admin_key_and_refuse_missing_key() -> None:
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200, json={"chats": 2})

    with SupportAPI(admin_api_key="admin-secret", transport=httpx.MockTransport(handler)) as api:
        assert api.analytics() == {"chats": 2}
    assert received[0].headers["X-Admin-Key"] == "admin-secret"

    with SupportAPI(transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(APIError, match="admin API key"):
            api.analytics()


def test_api_errors_include_the_server_detail() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "Admin access denied"})

    with SupportAPI(admin_api_key="wrong", transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(APIError, match="Admin access denied"):
            api.knowledge()
