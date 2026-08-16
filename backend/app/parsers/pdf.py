from __future__ import annotations

from collections import Counter
from importlib import import_module
from typing import Any

from app.parsers.base import ParsedArtifact


class PdfParser:
    version = "1"

    def __init__(self, *, minimum_chars_per_page: int = 20) -> None:
        self.minimum_chars_per_page = minimum_chars_per_page

    def parse(self, content: bytes, *, filename: str | None = None) -> ParsedArtifact:
        del filename
        pymupdf = import_module("pymupdf")
        document: Any = pymupdf.open(stream=content, filetype="pdf")
        try:
            pages = [page.get_text("text").strip() for page in document]
            cleaned_pages = _remove_repeated_headers_and_footers(pages)
            total_chars = sum(len(page) for page in cleaned_pages)
            requires_ocr = bool(cleaned_pages) and total_chars < (
                len(cleaned_pages) * self.minimum_chars_per_page
            )
            return ParsedArtifact(
                text="\n\n".join(page for page in cleaned_pages if page),
                pages=tuple(cleaned_pages),
                metadata={"page_count": len(cleaned_pages)},
                requires_ocr=requires_ocr,
            )
        finally:
            document.close()


def _remove_repeated_headers_and_footers(pages: list[str]) -> list[str]:
    if len(pages) < 2:
        return pages
    split_pages = [[line.strip() for line in page.splitlines() if line.strip()] for page in pages]
    first_counts = Counter(lines[0] for lines in split_pages if lines)
    last_counts = Counter(lines[-1] for lines in split_pages if lines)
    threshold = max(2, (len(pages) + 1) // 2)
    repeated_first = {line for line, count in first_counts.items() if count >= threshold}
    repeated_last = {line for line, count in last_counts.items() if count >= threshold}
    cleaned = []
    for lines in split_pages:
        if lines and lines[0] in repeated_first:
            lines = lines[1:]
        if lines and lines[-1] in repeated_last:
            lines = lines[:-1]
        cleaned.append("\n".join(lines))
    return cleaned
