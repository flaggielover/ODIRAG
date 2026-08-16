from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

import app.crawler.storage as storage_module
from app.crawler.storage import FileStorage


def _storage(root: Path) -> FileStorage:
    return FileStorage(root, max_bytes=1024, allowed_extensions={".pdf"})


@pytest.fixture
def storage_root() -> Iterator[Path]:
    parent = Path(".test-data") / "attachment-storage"
    parent.mkdir(parents=True, exist_ok=True)
    root = parent / f"case-{uuid4().hex}"
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root)


def test_storage_key_includes_attachment_identity(storage_root: Path) -> None:
    storage = _storage(storage_root)

    first = storage.save(
        source_url="https://example.gov/notice.pdf",
        content=b"first",
        namespace="document-7",
        filename="notice.pdf",
        identity="attachment-1",
    )
    second = storage.save(
        source_url="https://example.gov/notice.pdf",
        content=b"second",
        namespace="document-7",
        filename="notice.pdf",
        identity="attachment-2",
    )

    assert first != second
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"


def test_storage_verifies_checksum_before_atomic_replace(storage_root: Path) -> None:
    storage = _storage(storage_root)
    content = b"verified bytes"

    path = storage.save(
        source_url="https://example.gov/notice.pdf",
        content=content,
        namespace="document-7",
        filename="notice.pdf",
        identity="attachment-1",
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )

    assert path.read_bytes() == content
    assert not list(storage_root.rglob("*.tmp"))


def test_storage_removes_temp_file_when_checksum_fails(storage_root: Path) -> None:
    storage = _storage(storage_root)

    with pytest.raises(ValueError, match="checksum"):
        storage.save(
            source_url="https://example.gov/notice.pdf",
            content=b"corrupt bytes",
            namespace="document-7",
            filename="notice.pdf",
            identity="attachment-1",
            expected_sha256="0" * 64,
        )

    assert not list(storage_root.rglob("*.tmp"))
    assert not list(storage_root.rglob("*.pdf"))


def test_storage_removes_temp_file_and_preserves_target_when_replace_fails(
    storage_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = _storage(storage_root)
    existing = storage.save(
        source_url="https://example.gov/notice.pdf",
        content=b"old bytes",
        namespace="document-7",
        filename="notice.pdf",
        identity="attachment-1",
    )

    def fail_replace(_source: str | Path, _target: str | Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(storage_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        storage.save(
            source_url="https://example.gov/notice.pdf",
            content=b"new bytes",
            namespace="document-7",
            filename="notice.pdf",
            identity="attachment-1",
        )

    assert existing.read_bytes() == b"old bytes"
    assert not list(storage_root.rglob("*.tmp"))
