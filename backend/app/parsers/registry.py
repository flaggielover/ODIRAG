from __future__ import annotations

from pathlib import Path

from app.parsers.base import ParsedArtifact, Parser
from app.parsers.docx import DocxParser
from app.parsers.html import HtmlParser
from app.parsers.pdf import PdfParser
from app.parsers.text import TextParser
from app.parsers.xlsx import XlsxParser
from app.parsers.zip_metadata import ZipMetadataParser


class ParserRegistry:
    def __init__(self, parsers: dict[str, Parser] | None = None) -> None:
        self._parsers = parsers or {
            ".html": HtmlParser(),
            ".htm": HtmlParser(),
            ".pdf": PdfParser(),
            ".docx": DocxParser(),
            ".xlsx": XlsxParser(),
            ".txt": TextParser(),
            ".zip": ZipMetadataParser(),
        }

    def get(self, filename: str) -> Parser:
        extension = Path(filename).suffix.lower()
        try:
            return self._parsers[extension]
        except KeyError as exc:
            raise ValueError(f"unsupported parser extension: {extension or '<none>'}") from exc

    def parse(self, filename: str, content: bytes) -> ParsedArtifact:
        return self.get(filename).parse(content, filename=filename)
