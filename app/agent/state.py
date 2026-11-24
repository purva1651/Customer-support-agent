from typing import Literal, NotRequired, TypedDict


class ToolCall(TypedDict):
    name: str
    summary: str


class PendingAction(TypedDict):
    action_id: str
    description: str


class AgentState(TypedDict, total=False):
    customer_id: str
    session_id: str
    message: str
    language: str
    intent: Literal["question", "action", "complaint", "small_talk"]
    negative_sentiment: bool
    sentiment_confidence: float
    injection_detected: bool
    reply: str
    sources: list[dict[str, str]]
    tool_calls: list[ToolCall]
    pending_action: PendingAction | None
    escalated: bool
    escalation_summary: str | None
    escalation_reason: str
    attempted: str
    steps: int
    history: NotRequired[list[dict[str, str]]]
