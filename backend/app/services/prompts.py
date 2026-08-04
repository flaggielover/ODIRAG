from __future__ import annotations

import hashlib

from app.models import PromptVersion
from app.repositories.reviews import ReviewRepository


class PromptService:
    def __init__(self, repository: ReviewRepository) -> None:
        self.repository = repository

    async def ensure(
        self,
        *,
        name: str,
        version: str,
        content: str,
        change_description: str | None = None,
    ) -> PromptVersion:
        content_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = await self.repository.get_prompt(name, version)
        if existing is not None:
            if existing.content_hash != content_digest:
                raise ValueError("stored prompt version content does not match configured content")
            return existing
        prompt = PromptVersion(
            prompt_name=name,
            version=version,
            content_hash=content_digest,
            content=content,
            change_description=change_description,
            active=True,
        )
        await self.repository.activate_prompt(prompt)
        await self.repository.commit()
        return prompt
