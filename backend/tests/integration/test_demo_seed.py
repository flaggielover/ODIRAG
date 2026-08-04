from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

from sqlalchemy import func, select

from app.config import Settings
from app.database.session import DatabaseManager
from app.models import (
    Alert,
    Chunk,
    Document,
    EvaluationQuestion,
    EvaluationRun,
    Experiment,
    QueryTrace,
    Source,
    UserFeedback,
)


def _load_seed_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "seed_demo.py"
    specification = importlib.util.spec_from_file_location("odirag_seed_demo", script_path)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


async def test_demo_seed_is_idempotent_and_does_not_fabricate_results() -> None:
    module = _load_seed_module()
    database_path = (
        Path(".test-data") / f"seed-test-{uuid.uuid4().hex}" / "nested" / "demo.db"
    ).resolve()
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    await module._seed(database_url)
    await module._seed(database_url)

    assert database_path.is_file()
    database = DatabaseManager(Settings(database_url=database_url, bootstrap_admin=False))
    try:
        async with database.session_factory() as session:
            assert await session.scalar(select(func.count(Source.id))) == 2
            assert await session.scalar(select(func.count(Document.id))) == 3
            assert await session.scalar(select(func.count(Chunk.id))) == 0
            assert await session.scalar(select(func.count(QueryTrace.id))) == 0
            assert await session.scalar(select(func.count(UserFeedback.id))) == 0
            assert await session.scalar(select(func.count(EvaluationRun.id))) == 0
            assert await session.scalar(select(func.count(Alert.id))) == 0

            approved = list(
                await session.scalars(select(Document).where(Document.final_status == "approved"))
            )
            assert len(approved) == 2
            assert {document.index_status for document in approved} == {"pending"}

            questions = list(await session.scalars(select(EvaluationQuestion)))
            assert len(questions) == 1
            assert questions[0].verified is True
            assert questions[0].expected_chunk_ids == []

            experiments = list(await session.scalars(select(Experiment)))
            assert len(experiments) == 1
            assert experiments[0].status == "pending"
            assert experiments[0].conclusion is None
    finally:
        await database.dispose()
        database_path.unlink(missing_ok=True)
        database_path.parent.rmdir()
        database_path.parent.parent.rmdir()
