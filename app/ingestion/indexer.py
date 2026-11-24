import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from langchain_core.documents import Document

from app.ingestion.chunker import KnowledgeChunker
from app.ingestion.loaders import load_document
from app.retrieval.keyword_search import KeywordSearch


class VectorIndex(Protocol):
    def add_documents(self, documents: list[Document], ids: list[str] | None = None) -> Any: ...

    def delete(self, ids: list[str] | None = None, **kwargs: Any) -> Any: ...


class KnowledgeIndexer:
    def __init__(
        self,
        knowledge_dir: Path,
        vector_store: VectorIndex,
        keyword_search: KeywordSearch,
        chunker: KnowledgeChunker,
        manifest_path: Path | None = None,
    ) -> None:
        self._knowledge_dir = knowledge_dir
        self._vector_store = vector_store
        self._keyword_search = keyword_search
        self._chunker = chunker
        self._manifest_path = manifest_path or knowledge_dir.parent / "data" / "index_manifest.json"
        self._entries = self._read_manifest()
        self._cached_chunks: dict[str, list[Document]] = {}

    def sync(self, force: bool = False) -> dict[str, list[str]]:
        self._knowledge_dir.mkdir(parents=True, exist_ok=True)
        supported_extensions = {".md", ".txt", ".pdf", ".docx"}
        files = sorted(
            path
            for path in self._knowledge_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in supported_extensions
        )
        current_sources = {str(path.resolve()) for path in files}
        removed_sources = set(self._entries) - current_sources
        for source in removed_sources:
            self._delete_ids(self._entries[source].get("chunk_ids", []))
            self._entries.pop(source)
            self._cached_chunks.pop(source, None)

        changed: dict[str, list[str]] = {}
        for path in files:
            source = str(path.resolve())
            content_hash = _file_hash(path)
            entry = self._entries.get(source)
            if force or entry is None or entry.get("sha256") != content_hash:
                if entry is not None:
                    self._delete_ids(entry.get("chunk_ids", []))
                chunks = self._chunker.split_documents(load_document(path))
                chunk_ids = [str(chunk.metadata["chunk_id"]) for chunk in chunks]
                if chunks:
                    self._vector_store.add_documents(chunks, ids=chunk_ids)
                self._cached_chunks[source] = chunks
                self._entries[source] = {"sha256": content_hash, "chunk_ids": chunk_ids}
                changed[source] = chunk_ids
            elif source not in self._cached_chunks:
                self._cached_chunks[source] = self._chunker.split_documents(load_document(path))

        self._keyword_search.replace_documents(
            [chunk for chunks in self._cached_chunks.values() for chunk in chunks]
        )
        self._write_manifest()
        return changed

    def index_source(self, document: Document) -> list[str]:
        """Index an already-loaded external document, such as an admin-added URL."""
        chunks = self._chunker.split_documents([document])
        ids = [str(chunk.metadata["chunk_id"]) for chunk in chunks]
        source = str(document.metadata.get("source", ""))
        previous_chunks = self._cached_chunks.get(source, [])
        self._delete_ids([str(chunk.metadata["chunk_id"]) for chunk in previous_chunks])
        if chunks:
            self._vector_store.add_documents(chunks, ids=ids)
        self._cached_chunks[source] = chunks
        self._keyword_search.replace_documents(
            [chunk for source_chunks in self._cached_chunks.values() for chunk in source_chunks]
        )
        return ids

    def remove_source(self, source: str) -> None:
        chunks = self._cached_chunks.pop(source, [])
        self._delete_ids([str(chunk.metadata["chunk_id"]) for chunk in chunks])
        self._keyword_search.replace_documents(
            [chunk for source_chunks in self._cached_chunks.values() for chunk in source_chunks]
        )

    def remove_file(self, source: str) -> bool:
        root = self._knowledge_dir.resolve()
        path = Path(source).resolve()
        if root not in path.parents or not path.is_file():
            return False
        path.unlink()
        self.sync()
        return True

    def status(self) -> list[dict[str, str | int]]:
        self.sync()
        results: list[dict[str, str | int]] = []
        for source, entry in sorted(self._entries.items()):
            chunks = self._cached_chunks.get(source, [])
            title = (
                str(chunks[0].metadata.get("title", Path(source).stem))
                if chunks
                else Path(source).stem
            )
            source_url = (
                str(chunks[0].metadata["source_url"])
                if chunks and chunks[0].metadata.get("source_url")
                else source
            )
            results.append(
                {
                    "title": title,
                    "source": source,
                    "url": source_url,
                    "kind": "url" if source_url != source else "file",
                    "indexed_chunks": len(entry.get("chunk_ids", [])),
                    "status": "indexed" if entry.get("chunk_ids") else "empty",
                }
            )
        return results

    def _delete_ids(self, ids: list[str]) -> None:
        if ids:
            self._vector_store.delete(ids=ids)

    def _read_manifest(self) -> dict[str, dict[str, Any]]:
        if not self._manifest_path.is_file():
            return {}
        try:
            data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_manifest(self) -> None:
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._manifest_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
        temporary_path.replace(self._manifest_path)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
