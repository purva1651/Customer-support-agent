from pathlib import Path

import pytest
import yaml

from app.config import load_runtime_files
from app.ingestion.chunker import KnowledgeChunker
from app.ingestion.indexer import KnowledgeIndexer
from app.retrieval.hybrid_search import HybridSearch
from app.retrieval.keyword_search import KeywordSearch
from app.retrieval.reranker import BGEReranker
from app.retrieval.vector_store import create_vector_store

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.eval
def test_thirty_policy_questions_find_expected_source_in_hybrid_top_five(
    tmp_path: Path,
) -> None:
    """Evaluate real keyword + Chroma + BGE reranking on the policy question set."""
    retrieval = load_runtime_files(ROOT / "config").config.retrieval
    vector_store = create_vector_store(
        tmp_path / "chroma",
        retrieval.embedding_model,
        collection_name="rag_eval",
    )
    keyword_search = KeywordSearch()
    chunker = KnowledgeChunker(
        chunk_size=retrieval.chunk_size,
        chunk_overlap=retrieval.chunk_overlap,
    )
    indexer = KnowledgeIndexer(
        ROOT / "knowledge_base",
        vector_store,
        keyword_search,
        chunker,
        tmp_path / "index_manifest.json",
    )
    indexer.sync()
    search = HybridSearch(
        keyword_search,
        vector_store,
        BGEReranker(retrieval.reranker_model),
        candidate_count=max(retrieval.candidate_count, 5),
        result_count=5,
        rrf_k=retrieval.rrf_k,
    )
    cases = yaml.safe_load(
        (ROOT / "tests" / "retrieval" / "questions.yaml").read_text(encoding="utf-8")
    )

    assert len(cases) == 30
    misses: list[str] = []
    for case in cases:
        results = search.search(case["input"], limit=5)
        result_sources = {
            Path(item.document.metadata["source"]).name
            for item in results
            if item.document.metadata.get("source")
        }
        if case["expected_source"] not in result_sources:
            actual_sources = sorted(result_sources)
            misses.append(
                f"{case['input']} (expected {case['expected_source']}; got {actual_sources})"
            )

    assert not misses, "Expected source missing from hybrid top five:\n" + "\n".join(misses)
