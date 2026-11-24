import asyncio
from typing import Any

from app.agent.approvals import ApprovalStore
from app.agent.escalation import create_escalation_summary
from app.agent.graph import build_agent_graph
from app.agent.memory import SessionOwnerStore
from app.agent.nodes import AgentServices, _format_tool_result, _invoke_tool
from app.config import AppConfig
from app.observability.tracing import create_run_config, flush_traces
from app.schemas import ApprovalResponse, ChatRequest, ChatResponse


class AgentRuntime:
    def __init__(
        self,
        graph: Any,
        services: AgentServices,
        approvals: ApprovalStore,
        sessions: SessionOwnerStore,
        checkpoint_connection: Any,
    ) -> None:
        self._graph = graph
        self._services = services
        self._approvals = approvals
        self._sessions = sessions
        self._checkpoint_connection = checkpoint_connection

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self._sessions.bind(request.session_id, request.customer_id)
        initial_state = request.model_dump()
        try:
            result = await asyncio.wait_for(
                self._graph.ainvoke(
                    initial_state,
                    create_run_config(
                        self._services.config,
                        request.customer_id,
                        request.session_id,
                    ),
                ),
                timeout=self._services.config.agent.request_timeout_seconds,
            )
        except TimeoutError:
            result = await self._timeout_handoff(request)
        return ChatResponse.model_validate(
            {
                "reply": result.get("reply", "I couldn't complete this request safely."),
                "intent": result.get("intent", "question"),
                "sources": result.get("sources", []),
                "tool_calls": result.get("tool_calls", []),
                "pending_action": result.get("pending_action"),
                "escalated": result.get("escalated", False),
                "escalation_summary": result.get("escalation_summary"),
            }
        )

    async def approve(self, action_id: str, approved: bool) -> ApprovalResponse:
        action = self._approvals.consume(action_id, approved)
        if action is None:
            return ApprovalResponse(reply="The cancellation request was declined.")
        setting = self._services.tool_settings.tools.get(action.tool_name)
        risky = action.tool_name in {"cancel_booking", "refund_booking", "issue_refund"}
        if setting is None or not setting.enabled or not (setting.requires_approval or risky):
            raise ValueError("the approved action is no longer configured")
        tools = self._services.tools_for_customer(action.customer_id)
        tool = tools.get(action.tool_name)
        if tool is None or action.arguments.get("booking_id") != action.booking_id:
            raise ValueError("the approved booking action is invalid")
        result, _ = await _invoke_tool(
            tool,
            action.arguments,
            setting.timeout_seconds,
            setting.retries,
        )
        return ApprovalResponse(reply=f"Cancellation result: {_format_tool_result(result)}")

    async def _timeout_handoff(self, request: ChatRequest) -> dict[str, Any]:
        summary = await asyncio.to_thread(
            create_escalation_summary,
            self._services.llm,
            self._services.prompts,
            request.message,
            "The support request exceeded its configured time limit.",
            "The agent could not finish within the per-request timeout.",
            False,
        )
        ticket_calls: list[dict[str, str]] = []
        try:
            ticket = self._services.tools_for_customer(request.customer_id)["create_ticket"]
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    ticket.invoke,
                    {"subject": "Human support request", "details": summary},
                ),
                timeout=self._services.config.agent.request_timeout_seconds,
            )
            ticket_calls.append(
                {"name": "create_ticket", "summary": _format_tool_result(result)}
            )
        except Exception:
            pass
        return {
            "intent": "question",
            "reply": "This request took too long to process and has been handed to human support.",
            "tool_calls": ticket_calls,
            "escalated": True,
            "escalation_summary": summary,
        }

    async def close(self) -> None:
        await self._checkpoint_connection.close()
        await asyncio.to_thread(flush_traces, self._services.config)


async def create_runtime(
    services: AgentServices,
    config: AppConfig,
) -> AgentRuntime:
    checkpoint_path = config.agent.memory_path
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    import aiosqlite
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    connection = await aiosqlite.connect(checkpoint_path)
    checkpointer = AsyncSqliteSaver(
        connection,
        serde=JsonPlusSerializer(allowed_msgpack_modules=[]),
    )
    await checkpointer.setup()
    sessions = SessionOwnerStore(checkpoint_path)
    graph = build_agent_graph(services, checkpointer)
    return AgentRuntime(graph, services, services.approval_store, sessions, connection)
