from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    pages: tuple[str, ...] = ()
    status: Literal["success", "partial", "failed"] = "success"
    provider: str = "unknown"
    version: str = "unknown"
    error_code: str | None = None
    error_message: str | None = None


class OcrProvider(Protocol):
    name: str
    version: str

    async def recognize(
        self,
        content: bytes,
        *,
        file_type: str,
        filename: str,
    ) -> OcrResult: ...
