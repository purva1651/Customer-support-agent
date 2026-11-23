from io import BytesIO
from pathlib import Path

import httpx
import pytest
from docx import Document as WordDocument
from langchain_core.documents import Document

from app.ingestion.chunker import KnowledgeChunker
from app.ingestion.loaders import load_document


def test_load_markdown_and_text_with_titles(tmp_path: Path) -> None:
    markdown = tmp_path / "policy.md"
    markdown.write_text("# Seat rules\nCarry your ticket.", encoding="utf-8")
    text = tmp_path / "notes.txt"
    text.write_text("Plain ticket notes.", encoding="utf-8")

    markdown_doc = load_document(markdown)[0]
    text_doc = load_document(text)[0]

    assert markdown_doc.metadata["title"] == "Seat rules"
    assert markdown_doc.metadata["source"] == str(markdown.resolve())
    assert text_doc.metadata["title"] == "notes"
    assert text_doc.page_content == "Plain ticket notes."


def test_load_docx_paragraphs_and_table(tmp_path: Path) -> None:
    path = tmp_path / "terms.docx"
    word = WordDocument()
    word.add_paragraph("Ticket terms")
    table = word.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Fee"
    table.cell(0, 1).text = "Ten percent"
    word.save(path)

    document = load_document(path)[0]

    assert "Ticket terms" in document.page_content
    assert "Fee | Ten percent" in document.page_content


def test_load_pdf_pages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "policy.pdf"
    path.write_bytes(b"pdf content handled by patched reader")

    class FakePage:
        def extract_text(self) -> str:
            return "PDF policy content"

    class FakeReader:
        metadata = None
        pages = [FakePage()]

        def __init__(self, source: BytesIO) -> None:
            assert source.read()

    monkeypatch.setattr("pypdf.PdfReader", FakeReader)
    document = load_document(path)[0]

    assert document.page_content == "PDF policy content"
    assert document.metadata["page"] == 1
    assert document.metadata["title"] == "policy"


def test_load_web_url_extracts_text_and_omits_scripts(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("GET", "https://example.com/policy")
    response = httpx.Response(
        200,
        text="<html><head><title>Refunds</title></head><body><p>Refund times vary.</p>"
        "<script>ignore this</script></body></html>",
        request=request,
    )
    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: response)

    document = load_document("https://example.com/policy")[0]

    assert document.metadata["title"] == "Refunds"
    assert "Refund times vary." in document.page_content
    assert "ignore this" not in document.page_content


def test_chunker_uses_token_chunks_and_preserves_source_metadata() -> None:
    document = Document(
        page_content="Policy sentence about booking status. " * 500,
        metadata={"title": "Status policy", "source": "knowledge_base/status.md"},
    )
    chunker = KnowledgeChunker(chunk_size=100, chunk_overlap=10)

    chunks = chunker.split_documents([document])

    assert len(chunks) > 1
    assert all(chunk.metadata["title"] == "Status policy" for chunk in chunks)
    assert all(chunk.metadata["source"] == "knowledge_base/status.md" for chunk in chunks)
    assert all(chunk.metadata["chunk_id"] for chunk in chunks)
    assert len({chunk.metadata["chunk_id"] for chunk in chunks}) == len(chunks)


def test_loader_rejects_unsupported_file(tmp_path: Path) -> None:
    path = tmp_path / "policy.csv"
    path.write_text("term,definition", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported knowledge source"):
        load_document(path)
