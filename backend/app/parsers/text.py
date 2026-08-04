from __future__ import annotations

from app.parsers.base import ParsedArtifact


class TextParser:
    def parse(self, content: bytes, *, filename: str | None = None) -> ParsedArtifact:
        del filename
        for encoding in ("utf-8-sig", "gb18030", "utf-16"):
            try:
                return ParsedArtifact(text=content.decode(encoding))
            except UnicodeDecodeError:
                continue
        return ParsedArtifact(text=content.decode("utf-8", errors="replace"))
