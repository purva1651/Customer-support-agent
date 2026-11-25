import mimetypes
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.agent.approvals import ExpiredApproval, UnknownApproval, UsedApproval
from app.agent.memory import SessionOwnershipError
from app.api.dependencies import AppServices, get_services
from app.ingestion.source_links import local_source_id
from app.integrations.document_intelligence import (
    DocumentIntelligenceDisabled,
    DocumentIntelligenceError,
)
from app.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    ChatRequest,
    ChatResponse,
    DocumentExtractionResponse,
    HealthResponse,
)

router = APIRouter()
Services = Annotated[AppServices, Depends(get_services)]
_DOCUMENT_EXTENSIONS = {".docx", ".jpeg", ".jpg", ".pdf", ".png"}
_CUSTOMER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
@router.get("/knowledge/source/{source_id}", include_in_schema=True)
def get_knowledge_source(source_id: str, services: Services) -> FileResponse:
    root = services.knowledge_dir.resolve()
    for entry in services.indexer.status():
        source_path = Path(str(entry["source"])).resolve()
        if local_source_id(source_path) != source_id:
            continue
        if root not in source_path.parents or not source_path.is_file():
            break
        media_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
        return FileResponse(
            source_path,
            media_type=media_type,
            filename=source_path.name,
            content_disposition_type="inline",
        )
    raise HTTPException(status_code=404, detail="Knowledge source not found")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    services: Services,
) -> ChatResponse:
    normalized_message = request.message.strip().casefold()
    if normalized_message == "close":
        try:
            services.runtime.validate_session(request)
        except SessionOwnershipError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc
        if services.analytics.has_open_escalation(request.customer_id, request.session_id):
            closed = services.analytics.close_open_escalation(
                request.customer_id, request.session_id
            )
            reply = (
                "Your support case is closed. Send a new message if you need help again."
                if closed
                else "Your support case is already closed. Send a new message "
                "if you need help again."
            )
        else:
            reply = "There is no open human support case in this chat to close."
        response = await services.runtime.notice(request, reply)
        try:
            services.analytics.log_chat(
                customer_id=request.customer_id,
                session_id=request.session_id,
                question=request.message,
                intent=response.intent,
                resolved=True,
                escalated=False,
                escalation_summary=None,
                tool_calls=[],
            )
        except Exception:
            pass
        return response

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


@router.post("/documents/extract", response_model=DocumentExtractionResponse)
async def extract_document(
    services: Services,
    file: Annotated[UploadFile, File()],
    customer_id: Annotated[str, Form(min_length=1, max_length=64)],
    document_type: Annotated[str | None, Form(max_length=100)] = None,
) -> DocumentExtractionResponse:
    client = services.document_client
    if client is None or not client.enabled:
        raise HTTPException(
            status_code=503,
            detail="Document Intelligence extraction is not configured",
        )
    if not _CUSTOMER_ID_PATTERN.fullmatch(customer_id):
        raise HTTPException(status_code=422, detail="Invalid customer_id")
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in _DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail="Supported document types are PDF, DOCX, JPG, JPEG, and PNG",
        )
    content = await file.read(services.config.admin.max_upload_bytes + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded document is empty")
    if len(content) > services.config.admin.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Uploaded document exceeds the size limit")
    if document_type is not None and not document_type.strip():
        raise HTTPException(status_code=422, detail="document_type cannot be blank")
    normalized_document_type = document_type.strip() if document_type else None
    try:
        fields = await client.extract_fields(filename, content, normalized_document_type)
    except DocumentIntelligenceDisabled as exc:
        raise HTTPException(
            status_code=503,
            detail="Document Intelligence extraction is not configured",
        ) from exc
    except DocumentIntelligenceError as exc:
        raise HTTPException(
            status_code=502,
            detail="The Document Intelligence service could not extract this document",
        ) from exc
    return DocumentExtractionResponse(
        filename=filename,
        document_type=normalized_document_type,
        fields=fields,
        source=services.config.integrations.document_intelligence.source,
    )
