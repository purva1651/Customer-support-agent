import re
from dataclasses import dataclass

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

_TOKEN_PATTERN = re.compile(r"(?u)\b\w+\b")


def tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.casefold())


@dataclass(frozen=True)
class KeywordResult:
    document: Document
    score: float


class KeywordSearch:
    def __init__(self, documents: list[Document] | None = None) -> None:
        self.replace_documents(documents or [])

    def replace_documents(self, documents: list[Document]) -> None:
        self._documents = list(documents)
        tokenized = [tokenize(doc.page_content) for doc in self._documents]
        self._index = BM25Okapi(tokenized) if tokenized else None

    def search(self, query: str, limit: int = 8) -> list[KeywordResult]:
        if self._index is None or limit <= 0:
            return []
        scores = self._index.get_scores(tokenize(query))
        ordered = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)
        return [
            KeywordResult(self._documents[index], float(score))
            for index, score in ordered[:limit]
            if score > 0
        ]
