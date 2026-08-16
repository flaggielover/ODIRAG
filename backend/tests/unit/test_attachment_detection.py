from __future__ import annotations

from app.attachments import detect_attachment_type


def test_detection_prefers_mime_over_filename_and_magic() -> None:
    detected = detect_attachment_type(
        content_type="text/plain; charset=utf-8",
        content_disposition='attachment; filename="notice.pdf"',
        content=b"%PDF-1.7\n",
        original_filename="中文通知.pdf",
        source_url="https://example.gov/file?id=1",
    )

    assert detected.file_type == "txt"
    assert detected.extension == ".txt"
    assert detected.source == "content_type"


def test_detection_uses_magic_when_mime_is_generic_and_filename_has_no_suffix() -> None:
    detected = detect_attachment_type(
        content_type="application/octet-stream",
        content=b"%PDF-1.7\nbody",
        original_filename="四川省通知",
        source_url="https://example.gov/download?id=42",
    )

    assert detected.file_type == "pdf"
    assert detected.extension == ".pdf"
    assert detected.source == "magic"


def test_detection_handles_content_disposition_and_query_urls() -> None:
    detected = detect_attachment_type(
        content_type="application/octet-stream",
        content_disposition="attachment; filename*=UTF-8''%E9%80%9A%E7%9F%A5.docx",
        content=b"PK\x03\x04not-a-complete-zip",
        source_url="https://example.gov/download?id=7",
    )

    assert detected.file_type == "docx"
    assert detected.extension == ".docx"
    assert detected.source == "content_disposition"


def test_detection_marks_legacy_and_unknown_formats_without_calling_them_failed() -> None:
    legacy = detect_attachment_type(
        content_type="application/octet-stream",
        content=b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
        original_filename="历史材料.doc",
    )
    unknown = detect_attachment_type(
        content_type="application/octet-stream",
        content=b"\x00\x01\x02\x03",
        original_filename="材料.bin",
    )

    assert legacy.file_type == "doc"
    assert legacy.source == "magic_and_filename"
    assert unknown.file_type == "unknown"
    assert unknown.extension == ""


def test_legacy_magic_overrides_incorrect_modern_office_mime() -> None:
    detected = detect_attachment_type(
        content_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        content=b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy",
        original_filename="legacy-served-as-modern.docx",
    )

    assert detected.file_type == "legacy_office"
    assert detected.extension == ""
    assert detected.source == "magic"
