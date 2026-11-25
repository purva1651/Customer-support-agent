from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

Intent = Literal["question", "action", "complaint", "small_talk"]
Language = Literal["English", "Hindi", "Gujarati"]


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatRequest(APIModel):
    customer_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    message: str = Field(min_length=1, max_length=2000)
    language: Language = "English"

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


class SourceResponse(APIModel):
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)


class ToolCallResponse(APIModel):
    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class PendingActionResponse(APIModel):
    action_id: str = Field(min_length=1)
    description: str = Field(min_length=1)


class ChatResponse(APIModel):
    reply: str
    intent: Intent
    sources: list[SourceResponse] = Field(default_factory=list)
    tool_calls: list[ToolCallResponse] = Field(default_factory=list)
    pending_action: PendingActionResponse | None = None
    escalated: bool = False
    escalation_summary: str | None = None


class ApprovalRequest(APIModel):
    action_id: str = Field(min_length=1, max_length=128)
    approved: bool


class ApprovalResponse(APIModel):
    reply: str


class DocumentExtractionResponse(APIModel):
    filename: str = Field(min_length=1)
    document_type: str | None = None
    fields: dict[str, object]
    source: str = Field(min_length=1)


class HealthResponse(APIModel):
    status: Literal["ok"] = "ok"


class KnowledgeSourceResponse(APIModel):
    title: str
    url: str
    kind: Literal["file", "url"]
    indexed_chunks: int = Field(ge=0)
    status: Literal["indexed", "empty"]


class KnowledgeListResponse(APIModel):
    sources: list[KnowledgeSourceResponse]


class KnowledgeUrlRequest(APIModel):
    url: HttpUrl


class KnowledgeMutationResponse(APIModel):
    title: str
    url: str
    indexed_chunks: int = Field(ge=0)


class KnowledgeDeleteResponse(APIModel):
    deleted: bool
    title: str


class ReindexResponse(APIModel):
    updated: int = Field(ge=0)
    removed: int = Field(ge=0)
    indexed_sources: int = Field(ge=0)
    indexed_chunks: int = Field(ge=0)


class TopQuestion(APIModel):
    question: str
    count: int = Field(ge=1)


class IntentCount(APIModel):
    intent: Intent
    count: int = Field(ge=1)


class DailyChatCount(APIModel):
    date: str
    chats: int = Field(ge=0)


class UnresolvedQuery(APIModel):
    question: str
    intent: Intent
    session_id: str
    created_at: str


class AnalyticsResponse(APIModel):
    chats: int = Field(ge=0)
    resolved: int = Field(ge=0)
    escalated: int = Field(ge=0)
    top_questions: list[TopQuestion]
    unresolved: list[UnresolvedQuery]
    intent_counts: list[IntentCount] = Field(default_factory=list)
    daily_chats: list[DailyChatCount] = Field(default_factory=list)


class EscalationRecord(APIModel):
    session_id: str
    customer_id: str
    summary: str
    ticket_id: str | None = None
    created_at: str


class EscalationsResponse(APIModel):
    escalations: list[EscalationRecord]
