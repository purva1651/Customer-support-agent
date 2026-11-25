import asyncio
import hashlib
import hmac
import ipaddress
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile

from app.api.dependencies import AppServices, get_services
from app.ingestion.loaders import load_document
from app.schemas import (
    AdminReplyRequest,
    AnalyticsResponse,
    ConversationMessage,
    ConversationMessagesResponse,
    EscalationDecisionRequest,
    EscalationDecisionResponse,
    EscalationsResponse,
    KnowledgeDeleteResponse,
    KnowledgeListResponse,
    KnowledgeMutationResponse,
    KnowledgeSourceResponse,
    KnowledgeTextRequest,
    KnowledgeUrlRequest,
    ReindexResponse,
)

Services = Annotated[AppServices, Depends(get_services)]

def require_admin_key(
    services: Services,
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    expected = services.config.secrets.admin_api_key
    if not expected or not x_admin_key or not hmac.compare_digest(expected, x_admin_key):
        raise HTTPException(status_code=403, detail="Admin access denied")


router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin_key)])


@router.get("/knowledge", response_model=KnowledgeListResponse)
def list_knowledge(services: Services) -> KnowledgeListResponse:
    entries = services.indexer.status()
    return KnowledgeListResponse(
        sources=[
            KnowledgeSourceResponse(
                title=str(entry["title"]),
                url=str(entry["url"]),
                kind=str(entry["kind"]),
                indexed_chunks=int(entry["indexed_chunks"]),
                status=str(entry["status"]),
            )
            for entry in entries
        ]
    )


@router.post("/knowledge/text", response_model=KnowledgeMutationResponse)
async def add_knowledge_text(
    request: KnowledgeTextRequest,
    services: Services,
) -> KnowledgeMutationResponse:
    root = services.knowledge_dir.resolve()
    slug = hashlib.sha256(request.title.casefold().encode("utf-8")).hexdigest()[:16]
    path = root / "manual" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {request.title}\n\n{request.content}\n", encoding="utf-8")
    await asyncio.to_thread(services.indexer.sync)
    return _mutation_for_path(services, path.resolve())


@router.post("/knowledge/upload", response_model=KnowledgeMutationResponse)
async def upload_knowledge(
    file: Annotated[UploadFile, File()],
    services: Services,
) -> KnowledgeMutationResponse:
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    if extension not in {".md", ".pdf", ".docx", ".txt"}:
        raise HTTPException(status_code=422, detail="Unsupported knowledge file type")
    content = await file.read(services.config.admin.max_upload_bytes + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Knowledge file is empty")
    if len(content) > services.config.admin.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Knowledge file exceeds the configured limit")
    root = services.knowledge_dir.resolve()
    target = (root / filename).resolve()
    if root not in target.parents:
        raise HTTPException(status_code=422, detail="Invalid knowledge file name")
    root.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    await asyncio.to_thread(services.indexer.sync)
    return _mutation_for_path(services, target)


@router.post("/knowledge/url", response_model=KnowledgeMutationResponse)
async def add_knowledge_url(
    request: KnowledgeUrlRequest,
    services: Services,
) -> KnowledgeMutationResponse:
    url = str(request.url)
    _validate_external_url(url)
    try:
        document = (
            await asyncio.to_thread(
                load_document,
                url,
                services.config.agent.request_timeout_seconds,
                _validate_external_url,
            )
        )[0]
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not load the knowledge URL") from exc
    title = " ".join(str(document.metadata.get("title", "Web policy")).split()) or "Web policy"
    safe_title = title.replace("\n", " ").replace("\r", " ")
    slug = hashlib.sha256(url.encode()).hexdigest()[:16]
    path = services.knowledge_dir / "web" / f"url-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"<!-- source_url: {url} -->\n# {safe_title}\n\n{document.page_content}"
    path.write_text(content, encoding="utf-8")
    await asyncio.to_thread(services.indexer.sync)
    return _mutation_for_path(services, path.resolve())


@router.post("/knowledge/reindex", response_model=ReindexResponse)
async def reindex_knowledge(
    services: Services,
) -> ReindexResponse:
    before_sources = {entry["source"] for entry in services.indexer.status()}
    updated = await asyncio.to_thread(services.indexer.sync, True)
    entries = services.indexer.status()
    after_sources = {entry["source"] for entry in entries}
    return ReindexResponse(
        updated=len(updated),
        removed=len(before_sources - after_sources),
        indexed_sources=len(entries),
        indexed_chunks=sum(int(entry["indexed_chunks"]) for entry in entries),
    )


@router.delete("/knowledge", response_model=KnowledgeDeleteResponse)
async def delete_knowledge(
    title: Annotated[str, Query(min_length=1, max_length=200)],
    services: Services,
) -> KnowledgeDeleteResponse:
    matches = [entry for entry in services.indexer.status() if entry["title"] == title]
    if not matches:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="Knowledge title is ambiguous")
    if not await asyncio.to_thread(services.indexer.remove_file, str(matches[0]["source"])):
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    return KnowledgeDeleteResponse(deleted=True, title=title)


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(services: Services) -> AnalyticsResponse:
    chats, resolved, escalated, top_questions, unresolved = services.analytics.summary(
        top_limit=services.config.admin.analytics_top_questions_limit,
        unresolved_limit=services.config.admin.analytics_unresolved_limit,
    )
    return AnalyticsResponse(
        chats=chats,
        resolved=resolved,
        escalated=escalated,
        top_questions=top_questions,
        unresolved=unresolved,
        intent_counts=services.analytics.intent_counts(),
        daily_chats=services.analytics.daily_chats(),
    )


@router.get("/escalations", response_model=EscalationsResponse)
def escalations(services: Services) -> EscalationsResponse:
    return EscalationsResponse(
        escalations=services.analytics.escalations(services.config.admin.escalation_list_limit)
    )


@router.post(
    "/escalations/{escalation_id}/decision",
    response_model=EscalationDecisionResponse,
)
def decide_escalation(
    escalation_id: int,
    request: EscalationDecisionRequest,
    services: Services,
) -> EscalationDecisionResponse:
    try:
        status = services.analytics.decide_escalation(escalation_id, request.decision)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return EscalationDecisionResponse(id=escalation_id, status=status)


@router.get(
    "/escalations/{escalation_id}/messages",
    response_model=ConversationMessagesResponse,
)
def escalation_messages(
    escalation_id: int,
    services: Services,
) -> ConversationMessagesResponse:
    try:
        status, messages = services.analytics.admin_escalation_messages(escalation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ConversationMessagesResponse(
        escalation_id=escalation_id,
        status=status,
        messages=messages,
    )


@router.post(
    "/escalations/{escalation_id}/messages",
    response_model=ConversationMessage,
)
def reply_to_escalation(
    escalation_id: int,
    request: AdminReplyRequest,
    services: Services,
) -> ConversationMessage:
    try:
        return services.analytics.add_admin_reply(escalation_id, request.content.strip())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _mutation_for_path(services: AppServices, path: Path) -> KnowledgeMutationResponse:
    match = next(
        (entry for entry in services.indexer.status() if Path(str(entry["source"])) == path),
        None,
    )
    if match is None:
        raise HTTPException(status_code=500, detail="Knowledge source was not indexed")
    return KnowledgeMutationResponse(
        title=str(match["title"]),
        url=str(match["url"]),
        indexed_chunks=int(match["indexed_chunks"]),
    )


def _validate_external_url(url: str) -> None:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
    ):
        raise HTTPException(status_code=422, detail="Knowledge URL must use a public HTTP(S) host")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise HTTPException(status_code=422, detail="Knowledge URL must use a public HTTP(S) host")
