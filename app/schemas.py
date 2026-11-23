from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

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
    url: AnyHttpUrl


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


class HealthResponse(APIModel):
    status: Literal["ok"] = "ok"
