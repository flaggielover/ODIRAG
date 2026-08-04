from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    target_chars: int = 800
    min_chars: int = 160
    max_chars: int = 1200
    overlap_chars: int = 120

    def __post_init__(self) -> None:
        if not 0 <= self.overlap_chars < self.target_chars:
            raise ValueError("overlap_chars must be non-negative and below target_chars")
        if not 0 < self.min_chars <= self.target_chars <= self.max_chars:
            raise ValueError("expected min_chars <= target_chars <= max_chars")


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    index: int
    content: str
    section_path: tuple[str, ...]
    section_title: str | None
    char_count: int


_HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+.+|第[一二三四五六七八九十百千万零〇两\d]+[章节条编部分]\s*.*|"
    r"[一二三四五六七八九十百千万零〇两]+、\s*.+|\d+(?:\.\d+)*[.、)]\s*.+)$"
)


class HeadingAwareChunker:
    """Split text on headings and paragraph boundaries with bounded overlap."""

    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()

    def chunk(self, text: str) -> list[ChunkDraft]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            return []
        sections = self._sections(normalized)
        raw_chunks: list[tuple[str, tuple[str, ...], str | None]] = []
        for path, title, body in sections:
            prefix = f"{title}\n" if title else ""
            pieces = self._split_body(prefix + body)
            for piece in pieces:
                raw_chunks.append((piece, path, title))
        return [
            ChunkDraft(i, content, path, title, len(content))
            for i, (content, path, title) in enumerate(raw_chunks)
            if content.strip()
        ]

    def _sections(self, text: str) -> list[tuple[tuple[str, ...], str | None, str]]:
        sections: list[tuple[tuple[str, ...], str | None, str]] = []
        heading_stack: list[str] = []
        title: str | None = None
        body: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and _HEADING_RE.match(stripped):
                if title is not None or body:
                    sections.append((tuple(heading_stack), title, "\n".join(body).strip()))
                level = len(stripped) - len(stripped.lstrip("#")) if stripped.startswith("#") else 1
                clean_title = stripped.lstrip("#").strip()
                heading_stack = [*heading_stack[: max(0, level - 1)], clean_title]
                title, body = clean_title, []
            else:
                body.append(line)
        sections.append((tuple(heading_stack), title, "\n".join(body).strip()))
        return sections

    def _split_body(self, body: str) -> list[str]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        if not paragraphs:
            paragraphs = [body.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            for part in self._hard_split(paragraph):
                candidate = f"{current}\n\n{part}".strip() if current else part
                should_flush = len(candidate) > self.config.max_chars or (
                    len(candidate) > self.config.target_chars
                    and len(current) >= self.config.min_chars
                )
                if current and should_flush:
                    chunks.append(current)
                    overlap = (
                        current[-self.config.overlap_chars :].lstrip()
                        if self.config.overlap_chars
                        else ""
                    )
                    current = f"{overlap}\n\n{part}".strip()
                else:
                    current = candidate
        if current:
            chunks.append(current)
        return chunks

    def _hard_split(self, text: str) -> list[str]:
        separator_size = 2 if self.config.overlap_chars else 0
        piece_limit = max(
            1,
            self.config.max_chars - self.config.overlap_chars - separator_size,
        )
        if len(text) <= piece_limit:
            return [text]
        return self._separator_fallback(text, piece_limit)

    @staticmethod
    def _separator_fallback(text: str, limit: int) -> list[str]:
        """Prefer semantic boundaries, then fall back to a strict character limit."""
        remaining = text.strip()
        pieces: list[str] = []
        separators = ("\n", "。", "！", "？", "；", ";", "，", ",", " ")
        while len(remaining) > limit:
            window = remaining[: limit + 1]
            minimum_boundary = max(1, limit // 3)
            boundary = -1
            boundary_size = 0
            for separator in separators:
                candidate = window.rfind(separator, minimum_boundary)
                if candidate > boundary:
                    boundary = candidate
                    boundary_size = len(separator)
            cut = boundary + boundary_size if boundary >= minimum_boundary else limit
            piece = remaining[:cut].strip()
            if piece:
                pieces.append(piece)
            remaining = remaining[cut:].strip()
        if remaining:
            pieces.append(remaining)
        return pieces
