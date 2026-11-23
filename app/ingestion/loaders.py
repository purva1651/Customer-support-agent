from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path

import httpx
from langchain_core.documents import Document


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._inside_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._inside_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._inside_title:
            self.title_parts.append(cleaned)
        elif not self._skip_depth:
            self.text_parts.append(cleaned)


def _html_document(source: str, content: str) -> Document:
    parser = _ArticleParser()
    parser.feed(content)
    title = " ".join(parser.title_parts).strip() or source
    return Document(
        page_content="\n".join(parser.text_parts),
        metadata={"title": title, "source": source},
    )


def load_document(source: str | Path, timeout_seconds: float = 15) -> list[Document]:
    """Load one local supported file or an HTTP(S) page as LangChain documents."""
    source_value = str(source)
    if source_value.startswith(("http://", "https://")):
        response = httpx.get(source_value, timeout=timeout_seconds, follow_redirects=True)
        response.raise_for_status()
        return [_html_document(source_value, response.text)]

    path = Path(source_value).expanduser().resolve()
    extension = path.suffix.lower()
    if extension in {".md", ".txt"}:
        text = path.read_text(encoding="utf-8")
        title = _markdown_title(text) or path.stem
        return [Document(page_content=text, metadata={"title": title, "source": str(path)})]
    if extension == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(path.read_bytes()))
        title = (reader.metadata.title if reader.metadata else None) or path.stem
        return [
            Document(
                page_content=page.extract_text() or "",
                metadata={"title": title, "source": str(path), "page": page_number},
            )
            for page_number, page in enumerate(reader.pages, start=1)
        ]
    if extension == ".docx":
        from docx import Document as WordDocument

        word = WordDocument(BytesIO(path.read_bytes()))
        text_parts = [paragraph.text for paragraph in word.paragraphs if paragraph.text.strip()]
        for table in word.tables:
            text_parts.extend(
                " | ".join(cell.text for cell in row.cells).strip()
                for row in table.rows
                if any(cell.text.strip() for cell in row.cells)
            )
        return [
            Document(
                page_content="\n".join(text_parts),
                metadata={"title": path.stem, "source": str(path)},
            )
        ]
    raise ValueError(f"Unsupported knowledge source: {source_value}")


def _markdown_title(content: str) -> str | None:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or None
    return None
