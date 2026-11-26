import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.config import load_runtime_files
from app.mcp_server.server import (
    APIKeyMiddleware,
    MCPIdentity,
    answer_question,
    create_mcp_server,
    create_ticket,
    get_order_status,
    request_identity,
)


def test_mcp_server_exposes_only_expected_tools_and_hides_identity() -> None:
    async def inspect_tools() -> dict[str, Any]:
        server = create_mcp_server(api_key="test-key")
        return {item.name: item for item in await server.list_tools()}

    tools = asyncio.run(inspect_tools())

    assert set(tools) == {
        "answer_question",
        "create_ticket",
        "get_order_status",
        "extract_fields",
    }
    for tool_name in {"answer_question", "create_ticket", "get_order_status"}:
        tool = tools[tool_name]
        assert "X-API-Key" in tool.description
        assert "X-Customer-ID" in tool.description
        assert "X-Session-ID" in tool.description
        assert "customer_id" not in tool.inputSchema["properties"]
        assert "session_id" not in tool.inputSchema["properties"]

    assert "X-API-Key" in tools["extract_fields"].description
    assert set(tools["extract_fields"].inputSchema["properties"]) == {
        "file_base64",
        "filename",
        "document_type",
    }


def test_request_identity_authenticates_and_reads_headers_only() -> None:
    class RequestContext:
        request = type(
            "Request",
            (),
            {"headers": {"X-API-Key": "secret", "X-Customer-ID": "C001", "X-Session-ID": "s1"}},
        )()

    identity = request_identity(RequestContext(), load_runtime_files().config, "secret")
    assert (identity.customer_id, identity.session_id) == ("C001", "s1")

    with pytest.raises(PermissionError):
        request_identity(RequestContext(), load_runtime_files().config, "wrong")


def test_mcp_tool_handlers_use_shared_agent_and_customer_scoped_crm() -> None:
    class Runtime:
        async def chat(self, request: Any) -> Any:
            return SimpleNamespace(
                model_dump=lambda **_: {
                    "reply": request.message,
                    "customer_id": request.customer_id,
                    "session_id": request.session_id,
                    "language": request.language,
                }
            )

    requests: list[httpx.Request] = []

    def crm_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/tickets":
            return httpx.Response(201, json={"ticket_id": "T-1"})
        return httpx.Response(200, json={"booking_id": "B-1", "status": "confirmed"})

    async def invoke_tools() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        crm_client = httpx.Client(
            base_url="http://crm", transport=httpx.MockTransport(crm_handler)
        )
        services = SimpleNamespace(runtime=Runtime(), crm_client=crm_client)
        identity = MCPIdentity(customer_id="C001", session_id="session-9")
        try:
            return (
                await answer_question(services, identity, "Where is my ticket?", "Hindi"),
                await create_ticket(services, identity, "Missing ticket", "Please check"),
                await get_order_status(services, identity, "B-1"),
            )
        finally:
            crm_client.close()

    answer, ticket, booking = asyncio.run(invoke_tools())
    assert answer == {
        "reply": "Where is my ticket?",
        "customer_id": "C001",
        "session_id": "session-9",
        "language": "Hindi",
    }
    assert ticket == {"ticket_id": "T-1"}
    assert booking == {"booking_id": "B-1", "status": "confirmed"}
    assert [request.url.path for request in requests] == ["/tickets", "/bookings/B-1"]
    assert requests[0].read().decode() == (
        '{"customer_id":"C001","subject":"Missing ticket","details":"Please check"}'
    )
    assert requests[1].url.params["customer_id"] == "C001"


def test_api_key_middleware_rejects_missing_or_invalid_key() -> None:
    called = False

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        nonlocal called
        called = True

    middleware = APIKeyMiddleware(app, "secret", "/mcp")
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    scope = {"type": "http", "path": "/mcp", "headers": [(b"x-api-key", b"wrong")]}
    asyncio.run(middleware(scope, receive, send))

    assert not called
    assert messages[0]["status"] == 401
