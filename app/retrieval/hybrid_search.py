from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from langchain_core.documents import Document

from app.retrieval.keyword_search import KeywordSearch
from app.retrieval.reranker import DocumentScorer


class VectorSearcher(Protocol):
    def similarity_search(self, query: str, k: int = 4) -> list[Document]: ...


@dataclass(frozen=True)
class HybridResult:
    document: Document
    score: float
    fused_score: float


class HybridSearch:
    def __init__(
        self,
        keyword_search: KeywordSearch,
        vector_store: VectorSearcher,
        reranker: DocumentScorer,
        candidate_count: int = 8,
        result_count: int = 3,
        rrf_k: int = 60,
        sync_callback: Callable[[], object] | None = None,
    ) -> None:
        if candidate_count <= 0 or result_count <= 0 or rrf_k <= 0:
            raise ValueError("retrieval counts and RRF constant must be positive")
        self._keyword_search = keyword_search
        self._vector_store = vector_store
        self._reranker = reranker
        self._candidate_count = candidate_count
        self._result_count = result_count
        self._rrf_k = rrf_k
        self._sync_callback = sync_callback

    def search(self, query: str, limit: int | None = None) -> list[HybridResult]:
        if self._sync_callback is not None:
            self._sync_callback()
        keyword_results = self._keyword_search.search(query, self._candidate_count)
        vector_documents = self._vector_store.similarity_search(query, k=self._candidate_count)
        fused_scores: dict[str, float] = {}
        documents_by_id: dict[str, Document] = {}

        for ranking in (
            [result.document for result in keyword_results],
            vector_documents,
        ):
            for rank, document in enumerate(ranking, start=1):
                document_id = _document_id(document)
                documents_by_id[document_id] = document
                fused_scores[document_id] = fused_scores.get(document_id, 0.0) + 1 / (
                    self._rrf_k + rank
                )

        candidates = sorted(
            documents_by_id.values(),
            key=lambda document: fused_scores[_document_id(document)],
            reverse=True,
        )
        if not candidates:
            return []
        raw_scores = self._reranker.score(query, candidates)
        if len(raw_scores) != len(candidates):
            raise ValueError("reranker must return one score per document")
        maximum_fused = 2 / (self._rrf_k + 1)
        results = [
            HybridResult(
                document=document,
                score=float(score),
                fused_score=min(fused_scores[_document_id(document)] / maximum_fused, 1.0),
            )
            for document, score in zip(candidates, raw_scores, strict=True)
        ]
        results.sort(key=lambda result: result.score, reverse=True)
        return results[: limit if limit is not None else self._result_count]


def _document_id(document: Document) -> str:
    chunk_id = document.metadata.get("chunk_id")
    if chunk_id:
        return str(chunk_id)
    return str(document.metadata.get("source", "")) + "\0" + document.page_content
