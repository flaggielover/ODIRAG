from __future__ import annotations

# ruff: noqa: I001

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and parse existing attachments safely")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--ids",
        type=int,
        nargs="+",
        help="process only these existing attachment IDs",
    )
    selection.add_argument(
        "--eligible-only",
        action="store_true",
        help="process the current pending/retryable/historical eligible set",
    )
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument(
        "--concurrency",
        type=int,
        choices=(1,),
        default=1,
        help="bounded worker count; this single-machine closure is fixed at one",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


async def _run(arguments: argparse.Namespace) -> None:
    from app.config import Settings
    from app.crawler.storage import FileStorage
    from app.database.session import DatabaseManager
    from app.repositories.documents import DocumentRepository
    from app.services.attachment_download import AttachmentDownloadService
    from app.services.attachment_fetcher import build_attachment_fetcher
    from app.services.attachment_processing import AttachmentProcessingService
    from app.services.parsing import ParsingService

    if arguments.limit < 1:
        raise ValueError("limit must be positive")
    if arguments.ids and len(set(arguments.ids)) != len(arguments.ids):
        raise ValueError("attachment IDs must be unique")
    settings = Settings()
    if settings.source_discovery_validation_dns_url is None:
        raise RuntimeError("trusted validation DNS is required for attachment reprocessing")
    database = DatabaseManager(settings)
    output: dict[str, object]
    try:
        async with database.session_factory() as session:
            repository = DocumentRepository(session)
            attachments = await repository.list_attachment_processing_batch(
                limit=arguments.limit,
                attachment_ids=arguments.ids,
                eligible_only=arguments.eligible_only,
            )
            if arguments.ids:
                found_ids = {attachment.id for attachment in attachments}
                missing_ids = sorted(set(arguments.ids) - found_ids)
                if missing_ids:
                    raise ValueError(f"attachment IDs do not exist: {missing_ids}")
            fetcher = build_attachment_fetcher(settings)
            storage = FileStorage(
                settings.data_dir / "attachments",
                max_bytes=settings.max_download_bytes,
                allowed_extensions=settings.allowed_attachment_extensions,
            )
            downloader = AttachmentDownloadService(repository, fetcher, storage)
            processor = AttachmentProcessingService(
                repository,
                downloader,
                ParsingService(repository, max_file_bytes=settings.max_download_bytes),
            )
            results = await processor.process_many(
                [attachment.id for attachment in attachments],
                force=arguments.force,
            )
            output = {
                "concurrency": arguments.concurrency,
                "eligible_only": arguments.eligible_only,
                "selected_count": len(attachments),
                "results": [asdict(result) for result in results],
            }
    finally:
        await database.dispose()
    print(json.dumps(output, ensure_ascii=True, sort_keys=True))


def main() -> None:
    asyncio.run(_run(_args()))


if __name__ == "__main__":
    main()
