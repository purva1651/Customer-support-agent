from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.agent.approvals import ExpiredApproval, UnknownApproval, UsedApproval
from app.agent.memory import SessionOwnershipError
from app.api.dependencies import AppServices, get_services
from app.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    ChatRequest,
    ChatResponse,
    HealthResponse,
)

router = APIRouter()
Services = Annotated[AppServices, Depends(get_services)]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    services: Services,
) -> ChatResponse:
    try:
        response = await services.runtime.chat(request)
    except SessionOwnershipError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    try:
        services.analytics.log_chat(
            customer_id=request.customer_id,
            session_id=request.session_id,
            question=request.message,
            intent=response.intent,
            resolved=not response.escalated and response.pending_action is None,
            escalated=response.escalated,
            escalation_summary=response.escalation_summary,
            tool_calls=[call.model_dump() for call in response.tool_calls],
        )
    except Exception:
        pass
    return response


@router.post("/approve", response_model=ApprovalResponse)
async def approve(
    request: ApprovalRequest,
    services: Services,
) -> ApprovalResponse:
    try:
        return await services.runtime.approve(request.action_id, request.approved)
    except UnknownApproval as exc:
        raise HTTPException(status_code=404, detail="Approval action not found") from exc
    except (ExpiredApproval, UsedApproval) as exc:
        raise HTTPException(status_code=409, detail="Approval action is no longer valid") from exc
