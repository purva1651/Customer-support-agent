from pathlib import Path
from typing import Any


def create_vector_store(
    persist_directory: Path,
    embedding_model: str,
    collection_name: str = "ticket_support_policies",
) -> Any:
    """Create a persistent Chroma collection with local BGE-M3 embeddings."""
    from langchain_chroma import Chroma
    from langchain_community.embeddings import HuggingFaceEmbeddings

    embeddings = HuggingFaceEmbeddings(
        model_name=embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=str(persist_directory),
    )
