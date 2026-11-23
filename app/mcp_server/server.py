import hmac
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from starlette.responses import JSONResponse

from app.api.dependencies import AppServices, create_services
from app.config import AppConfig, load_runtime_files
from app.schemas import ChatRequest
from app.tools.bookings import booking_status_tool
from app.tools.tickets import create_ticket_tool


@dataclass(frozen=True)
class MCPIdentity:
    customer_id: str
    session_id: str


async def answer_question(
    services: AppServices,
    identity: MCPIdentity,
    message: str,
    language: str = "English",
) -> dict[str, Any]:
    response = await services.runtime.chat(
        ChatRequest(
            customer_id=identity.customer_id,
            session_id=identity.session_id,
            message=message,
            language=language,
        )
    )
    return response.model_dump(mode="json")


async def create_ticket(
    services: AppServices,
    identity: MCPIdentity,
    subject: str,
    details: str,
) -> dict[str, Any]:
    result = await create_ticket_tool(identity.customer_id, services.crm_client).ainvoke(
        {"subject": subject, "details": details}
    )
    return _as_object(result)


async def get_order_status(
    services: AppServices,
    identity: MCPIdentity,
    booking_id: str,
) -> dict[str, Any]:
    result = await booking_status_tool(identity.customer_id, services.crm_client).ainvoke(
        {"booking_id": booking_id}
    )
    return _as_object(result)


def request_identity(
    request: Any,
    config: AppConfig,
    expected_api_key: str | None = None,
) -> MCPIdentity:
    request_object = getattr(request, "request", None)
    headers = getattr(request_object, "headers", None)
    if headers is None:
        raise PermissionError("MCP calls must include the configured authentication headers")
    api_key = headers.get(config.mcp.api_key_header)
    required_key = expected_api_key or config.secrets.mcp_api_key
    if not required_key or not api_key or not hmac.compare_digest(required_key, api_key):
        raise PermissionError("MCP API key is invalid")
    customer_id = headers.get(config.mcp.customer_id_header)
    session_id = headers.get(config.mcp.session_id_header)
    if not customer_id or not session_id:
        raise PermissionError("MCP customer and session headers are required")
    return MCPIdentity(customer_id=customer_id, session_id=session_id)


def create_mcp_server(
    services: AppServices | None = None,
    api_key: str | None = None,
    config_directory: Any = None,
) -> FastMCP:
    files = (
        load_runtime_files(config_directory)
        if config_directory is not None
        else load_runtime_files()
    )
    config = files.config

    @asynccontextmanager
    async def lifespan(_: FastMCP) -> AsyncIterator[dict[str, AppServices]]:
        owned_services = services is None
        if services is not None:
            active_services = services
        elif config_directory is None:
            active_services = await create_services()
        else:
            active_services = await create_services(config_directory)
        try:
            yield {"services": active_services}
        finally:
            if owned_services:
                await active_services.close()

    server = FastMCP(
        name="Ticket Support Agent",
        instructions=(
            "Customer identity and session are taken from authenticated HTTP headers. "
            "Never request customer IDs as tool arguments."
        ),
        host=config.mcp.host,
        port=config.mcp.port,
        streamable_http_path=config.mcp.path,
        lifespan=lifespan,
    )

    def active_services(context: Context) -> AppServices:
        if services is not None:
            return services
        lifespan_context = context.request_context.lifespan_context
        if not isinstance(lifespan_context, Mapping):
            raise RuntimeError("MCP service container is unavailable")
        active = lifespan_context.get("services")
        if active is None:
            raise RuntimeError("MCP service container is unavailable")
        return active  # type: ignore[return-value]

    @server.tool(
        name="answer_question",
        description=(
            "Answer a customer support question through the same shared agent used by POST /chat. "
            "Input: message and optional language (English, Hindi, or Gujarati). Output: the "
            "chat response object with reply, intent, sources, tool calls, approval state, and "
            "escalation details. Requires X-API-Key, X-Customer-ID, and X-Session-ID headers."
        )
    )
    async def answer_question_tool(
        message: str,
        ctx: Context,
        language: str = "English",
    ) -> dict[str, Any]:
        """Answer a support question using the shared agent and its cited policy sources."""
        service = active_services(ctx)
        identity = request_identity(ctx.request_context, service.config, api_key)
        return await answer_question(service, identity, message, language)

    @server.tool(
        name="create_ticket",
        description=(
            "Create a support ticket for the customer identified by the authenticated request. "
            "Inputs: subject (1-120 characters) and details (maximum 2000 characters). Output: "
            "ticket_id, customer_id, subject, details, status, and created_at. Requires X-API-Key, "
            "X-Customer-ID, and X-Session-ID headers."
        )
    )
    async def create_ticket_tool(
        subject: str,
        details: str,
        ctx: Context,
    ) -> dict[str, Any]:
        """Create a mock CRM support ticket for the authenticated customer."""
        service = active_services(ctx)
        identity = request_identity(ctx.request_context, service.config, api_key)
        return await create_ticket(service, identity, subject, details)

    @server.tool(
        name="get_order_status",
        description=(
            "Get a booking's route, departure time, seat, amount, and status. Input: booking_id. "
            "Output: booking fields from the CRM. A booking owned by another customer returns the "
            "same not-found error as a missing booking. Requires X-API-Key, X-Customer-ID, and "
            "X-Session-ID headers."
        )
    )
    async def get_order_status_tool(booking_id: str, ctx: Context) -> dict[str, Any]:
        """Look up an order owned by the authenticated customer."""
        service = active_services(ctx)
        identity = request_identity(ctx.request_context, service.config, api_key)
        return await get_order_status(service, identity, booking_id)

    return server


class APIKeyMiddleware:
    def __init__(
        self, app: Any, api_key: str | None, path: str, api_key_header: str = "X-API-Key"
    ) -> None:
        self._app = app
        self._api_key = api_key
        self._path = path
        self._api_key_header = api_key_header.casefold()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("path") == self._path:
            headers = {
                key.decode("latin-1").casefold(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            supplied_key = headers.get(self._api_key_header)
            if (
                not self._api_key
                or not supplied_key
                or not hmac.compare_digest(self._api_key, supplied_key)
            ):
                response = JSONResponse({"detail": "MCP API key is invalid"}, status_code=401)
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


def create_mcp_http_app(
    services: AppServices | None = None,
    api_key: str | None = None,
    config_directory: Any = None,
) -> Any:
    files = (
        load_runtime_files(config_directory)
        if config_directory is not None
        else load_runtime_files()
    )
    config = files.config
    expected_key = api_key or config.secrets.mcp_api_key
    server = create_mcp_server(services, expected_key, config_directory)
    return APIKeyMiddleware(
        server.streamable_http_app(),
        expected_key,
        config.mcp.path,
        config.mcp.api_key_header,
    )


def _as_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {"result": value}
        if isinstance(decoded, dict):
            return decoded
    return {"result": value}


app = create_mcp_http_app()


def main() -> None:
    import uvicorn

    config = load_runtime_files().config
    uvicorn.run(app, host=config.mcp.host, port=config.mcp.port)


if __name__ == "__main__":
    main()
