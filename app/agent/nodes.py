import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.approvals import ApprovalStore
from app.agent.escalation import create_escalation_summary
from app.agent.router import ActionSelector, IntentRouter
from app.agent.state import AgentState
from app.config import AppConfig, IntentDescriptions, PromptTemplates, ToolSettings
from app.guardrails.injection_rules import PromptInjectionDetector
from app.guardrails.input_checks import validate_agent_input

_RISKY_ACTIONS = frozenset({"cancel_booking", "refund_booking", "issue_refund"})


@dataclass(frozen=True)
class AgentServices:
    llm: Any
    config: AppConfig
    prompts: PromptTemplates
    intents: IntentDescriptions
    tool_settings: ToolSettings
    tools_for_customer: Callable[[str], Mapping[str, Any]]
    retriever: Any
    approval_store: ApprovalStore


def create_nodes(services: AgentServices) -> dict[str, Callable[..., Any]]:
    router = IntentRouter(services.llm, services.prompts, services.intents)
    action_selector = ActionSelector(services.llm, services.prompts, services.tool_settings)
    injection_detector = PromptInjectionDetector(
        services.config.guardrails.injection_patterns
    )

    async def guardrails_node(state: AgentState) -> dict[str, Any]:
        message = validate_agent_input(
            state["customer_id"],
            state["session_id"],
            state["message"],
            services.config.guardrails.max_message_chars,
        )
        injected = injection_detector.detect(message)
        return {
            "message": message,
            "injection_detected": injected,
            "steps": 0,
            "sources": [],
            "tool_calls": [],
            "pending_action": None,
            "escalated": False,
            "escalation_summary": None,
            "escalation_reason": "Prompt-injection attempt detected" if injected else "",
            "attempted": "Input was checked by the backend guardrails.",
        }

    async def router_node(state: AgentState) -> dict[str, Any]:
        steps = state.get("steps", 0)
        if steps >= services.config.agent.max_steps:
            return {
                "intent": "complaint",
                "negative_sentiment": False,
                "escalation_reason": "Agent step limit reached before routing.",
            }
        if state.get("injection_detected", False):
            return {"intent": "complaint", "negative_sentiment": False, "steps": steps + 1}
        try:
            decision = await asyncio.to_thread(
                router.classify, state["message"], state.get("history", [])
            )
            return {
                "intent": decision.intent,
                "negative_sentiment": (
                    decision.negative_sentiment
                    and decision.sentiment_confidence
                    >= services.config.agent.sentiment_escalation_threshold
                ),
                "sentiment_confidence": decision.sentiment_confidence,
                "steps": steps + 1,
            }
        except Exception:
            return {
                "intent": "complaint",
                "negative_sentiment": False,
                "steps": steps + 1,
                "escalation_reason": "The request could not be routed reliably.",
            }

    async def answer_node(state: AgentState) -> dict[str, Any]:
        steps = state.get("steps", 0)
        if steps >= services.config.agent.max_steps:
            return {
                "escalation_reason": "Agent step limit reached while answering the question.",
                "reply": "I could not verify this information within the support limits.",
            }
        try:
            results = await asyncio.to_thread(services.retriever.search, state["message"])
        except Exception:
            results = []
        if not results or results[0].score < services.config.retrieval.min_score:
            return {
                "steps": steps + 1,
                "reply": (
                    "I'm not sure about that policy, so I'll ask a human support agent to help."
                ),
                "escalation_reason": "No sufficiently relevant policy source was found.",
                "attempted": (
                    "The policy knowledge base was searched, but no reliable source was found."
                ),
            }

        selected = results[: services.config.retrieval.result_count]
        context_parts: list[str] = []
        sources: list[dict[str, str]] = []
        for result in selected:
            metadata = result.document.metadata
            title = str(metadata.get("title", "Policy source"))
            source = str(metadata.get("source_url", metadata.get("source", "")))
            context_parts.append(
                f"Source title: {title}\nSource URL: {source}\n"
                f"Policy text:\n{result.document.page_content}"
            )
            sources.append({"title": title, "url": source})
        answer_language = (
            "English"
            if services.config.translation.enabled
            else state.get("language", "English")
        )
        messages = [
            SystemMessage(
                content=f"{services.prompts.answer_system}\n\nRetrieved context:\n"
                + "\n\n---\n\n".join(context_parts)
            ),
            HumanMessage(
                content=f"Answer in {answer_language} to this question: {state['message']}"
            ),
        ]
        try:
            response = await asyncio.to_thread(services.llm.invoke, messages)
            reply = _message_text(response)
        except Exception:
            return {
                "steps": steps + 1,
                "reply": "I could not verify an answer from the policy sources.",
                "escalation_reason": "Policy answer generation failed.",
                "attempted": (
                    "Relevant policy sources were found, but an answer could not be generated."
                ),
            }
        return {
            "steps": steps + 1,
            "reply": reply,
            "sources": sources,
            "attempted": f"Retrieved and used {len(sources)} policy source(s).",
        }

    async def act_node(state: AgentState) -> dict[str, Any]:
        steps = state.get("steps", 0)
        if steps >= services.config.agent.max_steps:
            return {
                "escalation_reason": "Agent step limit reached before the requested action.",
                "reply": "I could not safely complete that action within the support limits.",
            }
        tools = services.tools_for_customer(state["customer_id"])
        try:
            selection = await asyncio.to_thread(
                action_selector.select, state["message"], tools
            )
        except Exception:
            return {
                "steps": steps + 1,
                "escalation_reason": "The requested action could not be selected safely.",
                "reply": "I couldn't safely determine which support action to take.",
            }

        name = selection.tool_name
        setting = services.tool_settings.tools.get(name)
        if name not in tools or setting is None or not setting.enabled:
            return {
                "steps": steps + 1,
                "escalation_reason": "The requested action is not enabled.",
                "reply": "That action needs review by a human support agent.",
            }
        arguments = selection.arguments
        if "customer_id" in arguments:
            return {
                "steps": steps + 1,
                "escalation_reason": "The action attempted to supply customer identity.",
                "reply": "I couldn't verify that action safely and will ask a human to review it.",
            }
        requires_approval = setting.requires_approval or name in _RISKY_ACTIONS
        if requires_approval:
            booking_id = arguments.get("booking_id")
            if not isinstance(booking_id, str) or not booking_id:
                return {
                    "steps": steps + 1,
                    "escalation_reason": "The risky action did not identify a booking.",
                    "reply": "I need a booking identifier before I can request approval.",
                }
            action_id = services.approval_store.create_pending(
                state["customer_id"], booking_id, name, arguments
            )
            description = f"Cancel booking {booking_id}. The CRM will apply its configured fee."
            return {
                "steps": steps + 1,
                "pending_action": {"action_id": action_id, "description": description},
                "reply": f"Please approve or decline this request: {description}",
                "attempted": "Cancellation was prepared and is waiting for customer approval.",
            }

        remaining_steps = services.config.agent.max_steps - steps - 1
        if remaining_steps <= 0:
            return {
                "steps": steps + 1,
                "escalation_reason": "Agent step limit reached before the requested tool call.",
                "reply": "I couldn't complete that action within the support limits.",
            }
        try:
            result, attempts = await _invoke_tool(
                tools[name],
                arguments,
                setting.timeout_seconds,
                min(setting.retries, remaining_steps - 1),
            )
        except Exception:
            return {
                "steps": steps + 1,
                "escalation_reason": f"The {name} tool failed after its configured retries.",
                "reply": (
                    "I couldn't complete that action, so I'll ask a human support agent to help."
                ),
                "attempted": f"Tried the {name} support tool.",
            }
        summary = _format_tool_result(result)
        return {
            "steps": steps + attempts,
            "reply": summary,
            "tool_calls": [{"name": name, "summary": summary}],
            "attempted": f"Ran the {name} support tool successfully.",
        }

    async def complaint_node(state: AgentState) -> dict[str, Any]:
        reason = state.get("escalation_reason")
        if not reason:
            reason = (
                "Negative sentiment was detected."
                if state.get("negative_sentiment", False)
                else "The customer requested human support."
            )
        return {
            "escalation_reason": reason,
            "reply": "I'll hand this conversation to a human support agent.",
            "attempted": state.get("attempted", "No support action was taken before handoff."),
        }

    async def small_talk_node(state: AgentState) -> dict[str, Any]:
        steps = state.get("steps", 0)
        if steps >= services.config.agent.max_steps:
            return {
                "reply": "I couldn't finish this response within the support limits.",
                "steps": steps,
                "escalation_reason": "Agent step limit reached while responding to small talk.",
            }
        answer_language = (
            "English"
            if services.config.translation.enabled
            else state.get("language", "English")
        )
        messages = [
            SystemMessage(content=services.prompts.small_talk_system),
            HumanMessage(
                content=f"Reply in {answer_language} to: {state['message']}"
            ),
        ]
        try:
            result = await asyncio.to_thread(services.llm.invoke, messages)
            reply = _message_text(result)
        except Exception:
            reply = "Hello! I can help with a booking or ticket question."
        return {"steps": steps + 1, "reply": reply}

    async def escalation_node(state: AgentState) -> dict[str, Any]:
        steps = state.get("steps", 0)
        summary = await asyncio.to_thread(
            create_escalation_summary,
            services.llm,
            services.prompts,
            state["message"],
            state.get("attempted", "No support action was taken."),
            state.get("escalation_reason", "Human review is required."),
            steps < services.config.agent.max_steps,
        )
        tool_calls = list(state.get("tool_calls", []))
        ticket_setting = services.tool_settings.tools.get("create_ticket")
        ticket_status = ""
        if ticket_setting is not None and ticket_setting.enabled:
            try:
                ticket = services.tools_for_customer(state["customer_id"])["create_ticket"]
                result, attempts = await _invoke_tool(
                    ticket,
                    {"subject": "Human support request", "details": summary},
                    ticket_setting.timeout_seconds,
                    ticket_setting.retries,
                )
                ticket_status = " A support ticket was created."
                tool_calls.append(
                    {"name": "create_ticket", "summary": _format_tool_result(result)}
                )
                steps += attempts
            except Exception:
                ticket_status = " The support ticket could not be created automatically."
        return {
            "steps": steps + 1,
            "escalated": True,
            "escalation_summary": summary,
            "reply": f"I've handed this over to human support.{ticket_status}",
            "tool_calls": tool_calls,
        }

    async def respond_node(state: AgentState) -> dict[str, Any]:
        history = list(state.get("history", []))
        history.extend(
            [
                {"role": "customer", "content": state["message"]},
                {"role": "assistant", "content": state.get("reply", "")},
            ]
        )
        return {"history": history[-40:]}

    return {
        "guardrails": guardrails_node,
        "router": router_node,
        "answer": answer_node,
        "act": act_node,
        "complaint": complaint_node,
        "small_talk": small_talk_node,
        "escalate": escalation_node,
        "respond": respond_node,
    }


async def _invoke_tool(
    tool: Any, arguments: dict[str, Any], timeout_seconds: float, retries: int
) -> tuple[Any, int]:
    attempts = 0
    while True:
        attempts += 1
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(tool.invoke, arguments), timeout=timeout_seconds
            )
            return result, attempts
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500 or attempts > retries:
                raise
        except TimeoutError:
            if attempts > retries:
                raise
        except Exception:
            if attempts > retries:
                raise


def _message_text(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content.strip()
    return json.dumps(content, ensure_ascii=False, default=str)


def _format_tool_result(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)
