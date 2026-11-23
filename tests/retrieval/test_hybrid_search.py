from pathlib import Path
from typing import Any

import yaml
from langchain_core.documents import Document

from app.ingestion.chunker import KnowledgeChunker
from app.ingestion.indexer import KnowledgeIndexer
from app.ingestion.loaders import load_document
from app.retrieval.hybrid_search import HybridSearch
from app.retrieval.keyword_search import KeywordSearch

ROOT = Path(__file__).resolve().parents[2]


def test_thirty_policy_questions_find_expected_source_in_top_five() -> None:
    policy_documents = [
        document
        for path in (ROOT / "knowledge_base").glob("*.md")
        for document in load_document(path)
    ]
    search = KeywordSearch(policy_documents)
    cases = yaml.safe_load((ROOT / "tests/retrieval/questions.yaml").read_text(encoding="utf-8"))

    assert len(cases) == 30
    for case in cases:
        results = search.search(case["input"], limit=5)
        result_sources = {Path(item.document.metadata["source"]).name for item in results}
        assert case["expected_source"] in result_sources, case["input"]


class _VectorStore:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents

    def similarity_search(self, query: str, k: int = 4) -> list[Document]:
        return self.documents[:k]


class _Reranker:
    def score(self, query: str, documents: list[Document]) -> list[float]:
        return [0.95 if "refund" in document.page_content else 0.1 for document in documents]


def test_hybrid_search_fuses_candidates_and_reranks_top_results() -> None:
    documents = [
        Document(page_content="cancellation fees and approval", metadata={"chunk_id": "cancel"}),
        Document(page_content="refund timing and payment method", metadata={"chunk_id": "refund"}),
    ]
    search = HybridSearch(
        KeywordSearch(documents),
        _VectorStore(list(reversed(documents))),
        _Reranker(),
        candidate_count=2,
        result_count=1,
        rrf_k=60,
    )

    results = search.search("refund method")

    assert len(results) == 1
    assert results[0].document.metadata["chunk_id"] == "refund"
    assert results[0].score == 0.95
    assert results[0].fused_score > 0


def test_hybrid_search_checks_for_file_changes_before_retrieval() -> None:
    synchronized: list[bool] = []
    search = HybridSearch(
        KeywordSearch(),
        _VectorStore([]),
        _Reranker(),
        sync_callback=lambda: synchronized.append(True),
    )

    assert search.search("a new policy") == []
    assert synchronized == [True]


class _FakeSplitter:
    def split_documents(self, documents: list[Document]) -> list[Document]:
        return documents


class _MemoryVectorStore:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}

    def add_documents(self, documents: list[Document], ids: list[str] | None = None) -> None:
        for document, document_id in zip(documents, ids or [], strict=True):
            self.documents[document_id] = document

    def delete(self, ids: list[str] | None = None, **kwargs: Any) -> None:
        for document_id in ids or []:
            self.documents.pop(document_id, None)


def test_indexer_updates_changed_and_removed_files_without_restarting(tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    source = knowledge_dir / "first.md"
    source.write_text("# First\nCancellation policy old text.", encoding="utf-8")
    store = _MemoryVectorStore()
    keywords = KeywordSearch()
    indexer = KnowledgeIndexer(
        knowledge_dir,
        store,
        keywords,
        KnowledgeChunker(splitter=_FakeSplitter()),
        tmp_path / "data" / "manifest.json",
    )

    first_update = indexer.sync()
    assert len(first_update[str(source.resolve())]) == 1
    assert len(store.documents) == 1
    assert indexer.sync() == {}

    source.write_text("# First\nCancellation policy updated text.", encoding="utf-8")
    second_update = indexer.sync()
    assert len(second_update[str(source.resolve())]) == 1
    assert len(store.documents) == 1

    added_source = knowledge_dir / "second.txt"
    added_source.write_text("Payment failure policy text.", encoding="utf-8")
    indexer.sync()
    assert len(store.documents) == 2

    source.unlink()
    indexer.sync()
    assert len(store.documents) == 1
    added_source.unlink()
    indexer.sync()
    assert store.documents == {}
    assert keywords.search("cancellation", limit=5) == []
