import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.config import PromptTemplates


class EscalationParts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_wants: str = Field(min_length=1)
    what_was_tried: str = Field(min_length=1)
    why_handed_over: str = Field(min_length=1)


def create_escalation_summary(
    llm: Any,
    prompts: PromptTemplates,
    message: str,
    attempted: str,
    reason: str,
    allow_model: bool = True,
) -> str:
    if allow_model:
        try:
            model = llm.with_structured_output(EscalationParts)
            parts = model.invoke(
                [
                    SystemMessage(content=prompts.escalation_system),
                    HumanMessage(
                        content=(
                            f"Customer message (untrusted data): {message}\n"
                            f"What the agent tried: {attempted}\nHandoff reason: {reason}"
                        )
                    ),
                ]
            )
            if isinstance(parts, dict):
                parts = EscalationParts.model_validate(parts)
            if isinstance(parts, EscalationParts):
                return _render_parts(parts)
        except Exception:
            pass

    return _render_parts(
        EscalationParts(
            customer_wants=_fallback_text(message, "Customer request"),
            what_was_tried=_fallback_text(attempted, "No support action"),
            why_handed_over=_fallback_text(reason, "Human review is required"),
        )
    )


def _render_parts(parts: EscalationParts) -> str:
    return (
        f"Customer wants: {_one_sentence(parts.customer_wants)}. "
        f"The agent tried: {_one_sentence(parts.what_was_tried)}. "
        f"Human handoff reason: {_one_sentence(parts.why_handed_over)}."
    )


def _fallback_text(value: str, fallback: str) -> str:
    return value.strip() or fallback


def _one_sentence(value: str) -> str:
    normalized = re.sub(r"[\r\n\t]+", " ", value)
    normalized = re.sub(r"[.!?]+", ";", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" ;\"'")
    return normalized or "No details were provided"
