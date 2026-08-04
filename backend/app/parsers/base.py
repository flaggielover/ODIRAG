from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ParsedSection:
    title: str | None
    level: int
    text: str


@dataclass(frozen=True, slots=True)
class ParsedTable:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    markdown: str


@dataclass(frozen=True, slots=True)
class ParsedArtifact:
    text: str
    sections: tuple[ParsedSection, ...] = ()
    tables: tuple[ParsedTable, ...] = ()
    pages: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    requires_ocr: bool = False


class Parser(Protocol):
    def parse(self, content: bytes, *, filename: str | None = None) -> ParsedArtifact: ...


def table_to_markdown(headers: list[str], rows: list[list[str]]) -> str:
    width = max([len(headers), *(len(row) for row in rows)], default=0)
    if width == 0:
        return ""
    normalized_headers = (headers + [f"column_{index + 1}" for index in range(width)])[:width]
    normalized_rows = [(row + [""] * width)[:width] for row in rows]
    lines = [
        "| " + " | ".join(_escape(value) for value in normalized_headers) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_escape(value) for value in row) + " |" for row in normalized_rows
    )
    return "\n".join(lines)


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()
