from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings
from app.database.session import DatabaseManager
from app.repositories.indexing import IndexRepository
from app.services.bm25 import BM25RebuildService


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild the BM25 index from indexed chunks"
    )
    parser.add_argument("--database-url", help="Override ODIRAG_DATABASE_URL")
    parser.add_argument("--output", type=Path, help="Override the BM25 snapshot path")
    return parser.parse_args()


async def _run(arguments: argparse.Namespace) -> None:
    overrides = (
        {"database_url": arguments.database_url} if arguments.database_url else {}
    )
    settings = Settings(**overrides)
    output = arguments.output or settings.bm25_snapshot_path
    if not output.is_absolute():
        output = (BACKEND_ROOT / output).resolve()
    database = DatabaseManager(settings)
    try:
        async with database.session_factory() as session:
            result = await BM25RebuildService(IndexRepository(session)).rebuild(output)
    finally:
        await database.dispose()
    print(
        json.dumps(
            {
                "document_count": result.document_count,
                "snapshot_path": str(result.snapshot_path),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    asyncio.run(_run(_arguments()))


if __name__ == "__main__":
    main()
