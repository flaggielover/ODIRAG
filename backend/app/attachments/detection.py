from __future__ import annotations

import re
from dataclasses import dataclass
from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import BadZipFile, ZipFile

_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "text/html": "html",
    "application/xhtml+xml": "html",
    "text/plain": "txt",
}
_EXTENSION_TYPES = {
    ".doc": "doc",
    ".docx": "docx",
    ".htm": "html",
    ".html": "html",
    ".jpeg": "jpg",
    ".jpg": "jpg",
    ".pdf": "pdf",
    ".png": "png",
    ".shtml": "html",
    ".txt": "txt",
    ".webp": "webp",
    ".xls": "xls",
    ".xlsx": "xlsx",
    ".et": "et",
    ".jsp": "jsp",
    ".mp4": "mp4",
    ".ofd": "ofd",
    ".wps": "wps",
}
_CANONICAL_EXTENSIONS = {
    "doc": ".doc",
    "docx": ".docx",
    "html": ".html",
    "jpg": ".jpg",
    "pdf": ".pdf",
    "png": ".png",
    "txt": ".txt",
    "webp": ".webp",
    "xls": ".xls",
    "xlsx": ".xlsx",
}
_GENERIC_MIME_TYPES = {"", "application/octet-stream", "binary/octet-stream"}


@dataclass(frozen=True, slots=True)
class DetectedAttachmentType:
    file_type: str
    extension: str
    filename: str | None
    mime_type: str | None
    source: str


def detect_attachment_type(
    *,
    content_type: str | None = None,
    content_disposition: str | None = None,
    content: bytes | None = None,
    original_filename: str | None = None,
    source_url: str | None = None,
) -> DetectedAttachmentType:
    """Infer an attachment type using stable, auditable evidence precedence."""

    normalized_mime = _normalized_mime(content_type)
    disposition_filename = _content_disposition_filename(content_disposition)
    candidates: list[tuple[str, str | None, str | None]] = []
    if normalized_mime not in _GENERIC_MIME_TYPES:
        candidates.append(("content_type", _MIME_TYPES.get(normalized_mime), None))
    if disposition_filename:
        candidates.append(
            ("content_disposition", _type_from_filename(disposition_filename), disposition_filename)
        )
    magic_type = _type_from_magic(content)
    if magic_type == "legacy_office":
        for filename in (disposition_filename, original_filename, _url_filename(source_url)):
            file_type = _type_from_filename(filename)
            if file_type in {"doc", "xls"}:
                return DetectedAttachmentType(
                    file_type,
                    _CANONICAL_EXTENSIONS[file_type],
                    filename,
                    normalized_mime or None,
                    "magic_and_filename",
                )
        return DetectedAttachmentType(
            "legacy_office",
            "",
            disposition_filename or original_filename or _url_filename(source_url),
            normalized_mime or None,
            "magic",
        )
    if magic_type:
        candidates.append(("magic", magic_type, disposition_filename))
    if original_filename:
        candidates.append(
            ("original_filename", _type_from_filename(original_filename), original_filename)
        )
    url_filename = _url_filename(source_url)
    if url_filename:
        candidates.append(("url_suffix", _type_from_filename(url_filename), url_filename))

    for source, file_type, filename in candidates:
        if file_type:
            return DetectedAttachmentType(
                file_type=file_type,
                extension=_CANONICAL_EXTENSIONS.get(file_type, _safe_suffix(filename)),
                filename=filename or disposition_filename or original_filename or url_filename,
                mime_type=normalized_mime or None,
                source=source,
            )

    return DetectedAttachmentType(
        "unknown",
        "",
        disposition_filename or original_filename or url_filename,
        normalized_mime or None,
        "unknown",
    )


def _normalized_mime(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def _content_disposition_filename(value: str | None) -> str | None:
    if not value:
        return None
    message = Message()
    message["content-disposition"] = value
    filename = message.get_filename()
    if not filename:
        return None
    return Path(unquote(filename).replace("\\", "/")).name[:1024] or None


def _url_filename(value: str | None) -> str | None:
    if not value:
        return None
    return Path(unquote(urlsplit(value).path)).name[:1024] or None


def _type_from_filename(value: str | None) -> str | None:
    return _EXTENSION_TYPES.get(_safe_suffix(value))


def _safe_suffix(value: str | None) -> str:
    suffix = Path((value or "").replace("\\", "/")).suffix.lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,15}", suffix) else ""


def _type_from_magic(content: bytes | None) -> str | None:
    if not content:
        return None
    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "webp"
    if content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "legacy_office"
    if content.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist())
        except BadZipFile:
            return None
        if any(name.startswith("word/") for name in names):
            return "docx"
        if any(name.startswith("xl/") for name in names):
            return "xlsx"
    prefix = content[:4096].lstrip().lower()
    if prefix.startswith((b"<!doctype html", b"<html", b"<?xml")) or b"<body" in prefix:
        return "html"
    if b"\x00" not in content[:4096]:
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                content[:4096].decode(encoding)
                return "txt"
            except UnicodeDecodeError:
                continue
    return None
