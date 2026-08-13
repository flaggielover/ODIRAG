from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the bounded Phase G data-debt cleanup"
    )
    parser.add_argument("--limit", type=int, default=1000)
    return parser.parse_args()


async def _run(limit: int) -> None:
    from app.config import Settings
    from app.database.session import DatabaseManager
    from app.repositories.documents import DocumentRepository
    from app.services.data_quality import DataDebtCleanupService

    if limit < 1:
        raise ValueError("limit must be positive")
    database = DatabaseManager(Settings())
    try:
        async with database.session_factory() as session:
            result = await DataDebtCleanupService(DocumentRepository(session)).run(
                limit=limit
            )
    finally:
        await database.dispose()
    print(json.dumps(asdict(result), ensure_ascii=True, sort_keys=True))


def main() -> None:
    asyncio.run(_run(_arguments().limit))


if __name__ == "__main__":
    main()
