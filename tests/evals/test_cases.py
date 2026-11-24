from pathlib import Path
from typing import Any

import yaml
from langchain_core.documents import Document

from app.ingestion.loaders import load_document
from app.retrieval.keyword_search import KeywordSearch

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_INTENTS = {"question", "action", "complaint", "small_talk"}
EXPECTED_TOOLS = {None, "get_booking_status", "create_ticket", "update_contact", "cancel_booking"}


def _load_cases() -> list[dict[str, Any]]:
    return yaml.safe_load((ROOT / "tests/evals/cases.yaml").read_text(encoding="utf-8"))


def test_eval_case_inventory_has_twenty_five_typed_cases() -> None:
    cases = _load_cases()
    policy_names = {path.name for path in (ROOT / "knowledge_base").glob("*.md")}

    assert len(cases) >= 25
    for case in cases:
        assert set(case) == {"input", "expected_intent", "expected_tool", "expected_source"}
        assert case["input"].strip()
        assert case["expected_intent"] in EXPECTED_INTENTS
        assert case["expected_tool"] in EXPECTED_TOOLS
        assert case["expected_source"] is None or case["expected_source"] in policy_names


def test_eval_policy_cases_retrieve_the_expected_source() -> None:
    documents: list[Document] = []
    for path in (ROOT / "knowledge_base").glob("*.md"):
        documents.extend(load_document(path))
    search = KeywordSearch(documents)

    for case in _load_cases():
        expected_source = case["expected_source"]
        if expected_source is None:
            continue
        results = search.search(case["input"], limit=5)
        sources = {Path(result.document.metadata["source"]).name for result in results}
        assert expected_source in sources, case["input"]


