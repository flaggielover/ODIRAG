from __future__ import annotations

from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile

from app.parsers.base import ParsedArtifact


class ZipMetadataParser:
    def parse(self, content: bytes, *, filename: str | None = None) -> ParsedArtifact:
        del filename
        entries = []
        with ZipFile(BytesIO(content)) as archive:
            for info in archive.infolist():
                path = PurePosixPath(info.filename.replace("\\", "/"))
                unsafe = path.is_absolute() or ".." in path.parts
                entries.append(
                    {
                        "name": info.filename,
                        "compressed_size": info.compress_size,
                        "uncompressed_size": info.file_size,
                        "is_directory": info.is_dir(),
                        "unsafe_path": unsafe,
                    }
                )
        lines = [
            f"{entry['name']} ({entry['uncompressed_size']} bytes)"
            for entry in entries
            if not entry["is_directory"]
        ]
        return ParsedArtifact(text="\n".join(lines), metadata={"entries": entries})
