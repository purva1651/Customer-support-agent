import re
from collections.abc import Callable
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import httpx
from langchain_core.documents import Document

_SOURCE_URL_MARKER = re.compile(r"\A<!--\s*source_url:\s*(https?://[^\s]+)\s*-->\s*\n?")


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


def load_document(
    source: str | Path,
    timeout_seconds: float = 15,
    url_validator: Callable[[str], None] | None = None,
) -> list[Document]:
    """Load one local supported file or an HTTP(S) page as LangChain documents."""
    source_value = str(source)
    if source_value.startswith(("http://", "https://")):
        current_url = source_value
        for _ in range(6):
            if url_validator is not None:
                url_validator(current_url)
            response = httpx.get(
                current_url,
                timeout=timeout_seconds,
                follow_redirects=False,
            )
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    response.raise_for_status()
                current_url = urljoin(current_url, location)
                continue
            response.raise_for_status()
            return [_html_document(current_url, response.text)]
        raise ValueError("knowledge URL exceeded the redirect limit")

    path = Path(source_value).expanduser().resolve()
    extension = path.suffix.lower()
    if extension in {".md", ".txt"}:
        text = path.read_text(encoding="utf-8")
        source_url: str | None = None
        if extension == ".md":
            marker = _SOURCE_URL_MARKER.match(text)
            if marker is not None:
                source_url = marker.group(1)
                text = text[marker.end() :]
        title = _markdown_title(text) or path.stem
        metadata = {"title": title, "source": str(path)}
        if source_url:
            metadata["source_url"] = source_url
        return [Document(page_content=text, metadata=metadata)]
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
