import hashlib
from typing import Protocol

from langchain_core.documents import Document


class DocumentSplitter(Protocol):
    def split_documents(self, documents: list[Document]) -> list[Document]: ...


class KnowledgeChunker:
    def __init__(
        self,
        chunk_size: int = 400,
        chunk_overlap: int = 60,
        splitter: DocumentSplitter | None = None,
    ) -> None:
        if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk size must be positive and overlap smaller than chunk size")
        if splitter is None:
            from langchain_text_splitters import TokenTextSplitter

            splitter = TokenTextSplitter(
                encoding_name="cl100k_base",
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                add_start_index=True,
            )
        self._splitter = splitter

    def split_documents(self, documents: list[Document]) -> list[Document]:
        chunks = self._splitter.split_documents(documents)
        results: list[Document] = []
        for index, chunk in enumerate(chunks):
            if not chunk.page_content.strip():
                continue
            metadata = dict(chunk.metadata)
            metadata.setdefault("title", metadata.get("source", "Knowledge base"))
            source = str(metadata.get("source", ""))
            chunk_hash = hashlib.sha256(
                f"{source}\0{index}\0{chunk.page_content}".encode()
            ).hexdigest()
            metadata["chunk_id"] = chunk_hash
            results.append(Document(page_content=chunk.page_content, metadata=metadata))
        return results
