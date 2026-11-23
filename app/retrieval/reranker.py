import math
from typing import Protocol

from langchain_core.documents import Document


class DocumentScorer(Protocol):
    def score(self, query: str, documents: list[Document]) -> list[float]: ...


class BGEReranker:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name, device="cpu")

    def score(self, query: str, documents: list[Document]) -> list[float]:
        if not documents:
            return []
        raw_scores = self._model.predict([(query, doc.page_content) for doc in documents])
        return [_sigmoid(float(score)) for score in raw_scores]


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-min(value, 700)))
    exp_value = math.exp(max(value, -700))
    return exp_value / (1 + exp_value)
