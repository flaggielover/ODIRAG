from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

DEFAULT_BOILERPLATE_PATTERNS = (
    r"^打印本页$",
    r"^关闭窗口$",
    r"^责任编辑[:：].+$",
    r"^扫一扫在手机打开当前页$",
)


def clean_text(
    text: str, *, boilerplate_patterns: Iterable[str] = DEFAULT_BOILERPLATE_PATTERNS
) -> str:
    normalized = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    patterns = [re.compile(pattern) for pattern in boilerplate_patterns]
    lines = []
    for line in normalized.splitlines():
        value = re.sub(r"[\t \u3000]+", " ", line).strip()
        if value and not any(pattern.match(value) for pattern in patterns):
            lines.append(value)
        elif not value and lines and lines[-1] != "":
            lines.append("")
    return remove_duplicate_paragraphs("\n".join(lines)).strip()


def remove_duplicate_paragraphs(text: str) -> str:
    paragraphs = [
        paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()
    ]
    seen: set[str] = set()
    unique = []
    for paragraph in paragraphs:
        fingerprint = re.sub(r"\s+", "", paragraph)
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(paragraph)
    return "\n\n".join(unique)
