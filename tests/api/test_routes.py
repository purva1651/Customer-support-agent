from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.api.analytics import AnalyticsStore
from app.api.dependencies import AppServices
from app.api.main import create_app
from app.config import load_runtime_files
from app.ingestion.chunker import KnowledgeChunker
from app.ingestion.indexer import KnowledgeIndexer
from app.retrieval.keyword_search import KeywordSearch
from app.schemas import ApprovalResponse, ChatResponse


class _IdentitySplitter:
    def split_documents(self, documents: list[Document]) -> list[Document]:
        return documents


class _MemoryVectorStore:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}

    def add_documents(self, documents: list[Document], ids: list[str] | None = None) -> None:
        for document, doc_id in zip(documents, ids or [], strict=True):
            self.documents[doc_id] = document

    def delete(self, ids: list[str] | None = None, **kwargs: Any) -> None:
        for doc_id in ids or []:
            self.documents.pop(doc_id, None)


class _FakeRuntime:
    async def chat(self, request: Any) -> ChatResponse:
        if "escalate" in request.message.casefold():
            return ChatResponse(
                reply="I've handed this over.",
                intent="complaint",
                escalated=True,
                escalation_summary=(
                    "Customer wants a review. The agent checked the request. "
                    "Human review is needed."
                ),
                tool_calls=[
                    {"name": "create_ticket", "summary": '{"ticket_id":"T-1009"}'}
                ],
            )
        return ChatResponse(reply="I checked the policy.", intent="question")

    async def approve(self, action_id: str, approved: bool) -> ApprovalResponse:
        return ApprovalResponse(reply=f"{action_id}:{approved}")

    async def close(self) -> None:
        return None


@pytest.fixture
def services(tmp_path: Path) -> AppServices:
    files = load_runtime_files()
    config = files.config.model_copy(
        update={
            "secrets": files.config.secrets.model_copy(
                update={"admin_api_key": "test-admin-key"}
            )
        }
    )
    knowledge_dir = tmp_path / "knowledge_base"
    vector_store = _MemoryVectorStore()
    indexer = KnowledgeIndexer(
        knowledge_dir,
        vector_store,
        KeywordSearch(),
        KnowledgeChunker(splitter=_IdentitySplitter()),
        tmp_path / "data" / "manifest.json",
    )
    return AppServices(
        config=config,
        runtime=_FakeRuntime(),  # type: ignore[arg-type]
        indexer=indexer,
        analytics=AnalyticsStore(tmp_path / "data" / "analytics.sqlite3"),
        knowledge_dir=knowledge_dir,
        crm_client=httpx.Client(),
    )


def test_health_chat_validation_approval_and_analytics(services: AppServices) -> None:
    with TestClient(create_app(services)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        invalid = client.post(
            "/chat",
            json={"customer_id": "C001", "session_id": "s1", "message": " "},
        )
        assert invalid.status_code == 422

        answer = client.post(
            "/chat",
            json={"customer_id": "C001", "session_id": "s1", "message": "GST policy?"},
        )
        escalated = client.post(
            "/chat",
            json={"customer_id": "C001", "session_id": "s2", "message": "Please escalate this"},
        )
        assert answer.status_code == escalated.status_code == 200
        assert escalated.json()["escalated"] is True

        approved = client.post("/approve", json={"action_id": "a1", "approved": True})
        assert approved.json() == {"reply": "a1:True"}
        analytics = client.get("/admin/analytics", headers={"X-Admin-Key": "test-admin-key"})
        assert analytics.status_code == 200
        assert analytics.json()["chats"] == 2
        assert analytics.json()["resolved"] == 1
        assert analytics.json()["escalated"] == 1
        assert analytics.json()["unresolved"][0]["session_id"] == "s2"
        escalations = client.get(
            "/admin/escalations", headers={"X-Admin-Key": "test-admin-key"}
        )
        assert escalations.json()["escalations"][0]["ticket_id"] == "T-1009"


def test_admin_key_is_required(services: AppServices) -> None:
    with TestClient(create_app(services)) as client:
        assert client.get("/admin/knowledge").status_code == 403
        assert client.get(
            "/admin/knowledge", headers={"X-Admin-Key": "wrong"}
        ).status_code == 403
        assert client.get(
            "/admin/knowledge", headers={"X-Admin-Key": "test-admin-key"}
        ).status_code == 200


def test_admin_knowledge_upload_reindex_and_delete(services: AppServices) -> None:
    headers = {"X-Admin-Key": "test-admin-key"}
    with TestClient(create_app(services)) as client:
        uploaded = client.post(
            "/admin/knowledge/upload",
            headers=headers,
            files={"file": ("new_policy.md", b"# New policy\n\nTest details.", "text/markdown")},
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["title"] == "New policy"
        assert uploaded.json()["indexed_chunks"] == 1

        reindexed = client.post("/admin/knowledge/reindex", headers=headers)
        assert reindexed.status_code == 200
        assert reindexed.json()["updated"] == 1

        deleted = client.delete("/admin/knowledge", params={"title": "New policy"}, headers=headers)
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": True, "title": "New policy"}
        assert client.get("/admin/knowledge", headers=headers).json()["sources"] == []


def test_admin_url_sources_are_persisted_and_private_hosts_rejected(
    services: AppServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes_admin.load_document",
        lambda url, timeout_seconds=15, url_validator=None: [
            Document(
                page_content="A web policy body.",
                metadata={"title": "Remote policy", "source": url},
            )
        ],
    )
    headers = {"X-Admin-Key": "test-admin-key"}
    with TestClient(create_app(services)) as client:
        invalid = client.post(
            "/admin/knowledge/url", headers=headers, json={"url": "http://localhost/private"}
        )
        assert invalid.status_code == 422
        added = client.post(
            "/admin/knowledge/url",
            headers=headers,
            json={"url": "https://example.com/policies/remote"},
        )
        assert added.status_code == 200
        assert added.json()["title"] == "Remote policy"
        assert added.json()["url"] == "https://example.com/policies/remote"

        listing = client.get("/admin/knowledge", headers=headers).json()["sources"]
        assert listing[0]["kind"] == "url"
        assert listing[0]["url"] == "https://example.com/policies/remote"
