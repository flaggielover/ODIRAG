from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


def safe_filename(name: str, *, fallback: str = "attachment") -> str:
    decoded = unquote(name).strip()
    basename = Path(decoded.replace("\\", "/")).name
    raw_suffix = Path(basename).suffix.lower()
    suffix = raw_suffix if re.fullmatch(r"\.[a-z0-9]{1,15}", raw_suffix) else ""
    raw_stem = Path(basename).stem if suffix else basename
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_stem).strip("_-")[:100] or fallback
    digest = hashlib.sha256(decoded.encode("utf-8")).hexdigest()[:10]
    return f"{stem}-{digest}{suffix}"


class FileStorage:
    def __init__(self, root: Path, *, max_bytes: int, allowed_extensions: set[str]) -> None:
        self.root = root.resolve()
        self.max_bytes = max_bytes
        self.allowed_extensions = {extension.lower() for extension in allowed_extensions}

    def save(self, *, source_url: str, content: bytes, namespace: str) -> Path:
        if len(content) > self.max_bytes:
            raise ValueError("attachment exceeds configured size limit")
        source_name = Path(urlsplit(source_url).path).name
        filename = safe_filename(source_name)
        if Path(filename).suffix.lower() not in self.allowed_extensions:
            raise ValueError("attachment extension is not allowed")
        directory = (self.root / safe_filename(namespace, fallback="source")).resolve()
        target = (directory / filename).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("attachment path escaped storage root")
        directory.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target
