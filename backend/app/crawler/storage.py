from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit


def safe_filename(
    name: str,
    *,
    fallback: str = "attachment",
    identity: str | None = None,
) -> str:
    decoded = unquote(name).strip()
    basename = Path(decoded.replace("\\", "/")).name
    raw_suffix = Path(basename).suffix.lower()
    suffix = raw_suffix if re.fullmatch(r"\.[a-z0-9]{1,15}", raw_suffix) else ""
    raw_stem = Path(basename).stem if suffix else basename
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_stem).strip("_-")[:100] or fallback
    digest_input = decoded if identity is None else f"{identity}\0{decoded}"
    digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:10]
    return f"{stem}-{digest}{suffix}"


class FileStorage:
    def __init__(self, root: Path, *, max_bytes: int, allowed_extensions: set[str]) -> None:
        self.root = root.resolve()
        self.max_bytes = max_bytes
        self.allowed_extensions = {extension.lower() for extension in allowed_extensions}

    def save(
        self,
        *,
        source_url: str,
        content: bytes,
        namespace: str,
        filename: str | None = None,
        identity: str | None = None,
        expected_sha256: str | None = None,
    ) -> Path:
        if len(content) > self.max_bytes:
            raise ValueError("attachment exceeds configured size limit")
        expected_checksum = _expected_checksum(content, expected_sha256)
        source_name = filename or Path(urlsplit(source_url).path).name
        filename = safe_filename(source_name, identity=identity)
        if Path(filename).suffix.lower() not in self.allowed_extensions:
            raise ValueError("attachment extension is not allowed")
        directory = (self.root / safe_filename(namespace, fallback="source")).resolve()
        target = (directory / filename).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("attachment path escaped storage root")
        directory.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=directory,
                prefix=f".{filename}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            if temporary_path.stat().st_size != len(content):
                raise OSError("attachment temporary file size mismatch")
            if _sha256_path(temporary_path) != expected_checksum:
                raise ValueError("attachment temporary file checksum mismatch")
            os.replace(temporary_path, target)
            temporary_path = None
            return target
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def _expected_checksum(content: bytes, expected_sha256: str | None) -> str:
    if expected_sha256 is None:
        return hashlib.sha256(content).hexdigest()
    normalized = expected_sha256.strip().lower()
    if re.fullmatch(r"[a-f0-9]{64}", normalized) is None:
        raise ValueError("expected attachment checksum must be a SHA-256 hex digest")
    return normalized


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
