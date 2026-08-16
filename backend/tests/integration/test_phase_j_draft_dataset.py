from __future__ import annotations

from app.evaluation.draft_dataset import (
    DATASET_STATUS,
    build_draft_evaluation_dataset,
    validate_draft_dataset,
)
from app.models import Chunk, Document, Source


async def test_phase_j_draft_is_real_corpus_traceable_and_not_human_verified(app) -> None:
    async with app.state.database.session_factory() as session:
        for index in range(3):
            source = Source(
                source_key=f"phase-j-source-{index}",
                name=f"Official source {index}",
                domain=f"agency-{index}.gov.cn",
                region="四川省",
                organization_level="provincial",
                organization_type="government",
                official_status="official",
                homepage_url=f"https://agency-{index}.gov.cn/",
            )
            session.add(source)
            await session.flush()
            document = Document(
                document_id=f"PHASE-J-DOC-{index}",
                source_id=source.id,
                title=f"Official policy {index}",
                source_url=f"https://agency-{index}.gov.cn/policy/{index}",
                content=f"Policy {index} provides an auditable implementation requirement.",
                word_count=70,
                region="四川省",
                final_status="approved",
                manual_review_status="approved",
                index_status="indexed",
            )
            session.add(document)
            await session.flush()
            session.add(
                Chunk(
                    chunk_id=f"phase-j-chunk-{index}",
                    document_id=document.id,
                    chunk_index=0,
                    content=document.content,
                    content_hash=f"hash-{index}",
                    char_count=len(document.content),
                    token_count=10,
                    vector_status="indexed",
                )
            )
        await session.commit()

        dataset = await build_draft_evaluation_dataset(session, limit=3)
        validate_draft_dataset(dataset, expected_size=3)

    assert dataset.status == DATASET_STATUS
    assert dataset.question_count == 3
    assert dataset.human_verified_count == 0
    assert dataset.human_review_required_count == 3
    assert all(case.expected_documents for case in dataset.cases)
    assert all(
        case.expected_sources[0].endswith(f"/{index}") for index, case in enumerate(dataset.cases)
    )
    assert all(case.expected_chunk_ids for case in dataset.cases)
    assert all(case.expected_answer for case in dataset.cases)
    assert not any(case.human_verified for case in dataset.cases)


async def test_phase_j_large_draft_covers_required_safety_categories(app) -> None:
    async with app.state.database.session_factory() as session:
        for index in range(18):
            source = Source(
                source_key=f"phase-j-category-source-{index}",
                name=f"Official category source {index}",
                domain=f"category-{index}.gov.cn",
                official_status="official",
                homepage_url=f"https://category-{index}.gov.cn/",
            )
            session.add(source)
            await session.flush()
            document = Document(
                document_id=f"PHASE-J-CATEGORY-DOC-{index}",
                source_id=source.id,
                title=f"Category policy {index}",
                source_url=f"https://category-{index}.gov.cn/policy/{index}",
                content=f"Category evidence {index} with a bounded official statement.",
                word_count=60,
                final_status="approved",
                manual_review_status="approved",
                index_status="indexed",
            )
            session.add(document)
            await session.flush()
            session.add(
                Chunk(
                    chunk_id=f"phase-j-category-chunk-{index}",
                    document_id=document.id,
                    chunk_index=0,
                    content=document.content,
                    content_hash=f"category-hash-{index}",
                    char_count=len(document.content),
                    token_count=10,
                    vector_status="indexed",
                )
            )
        await session.commit()

        dataset = await build_draft_evaluation_dataset(session, limit=18)
        validate_draft_dataset(dataset, expected_size=18)

    assert len({case.category for case in dataset.cases}) == 18
    assert sum(case.should_refuse for case in dataset.cases) == 10


async def test_phase_j_draft_excludes_nonofficial_or_unindexed_documents(app) -> None:
    async with app.state.database.session_factory() as session:
        source = Source(
            source_key="phase-j-association",
            name="Association",
            domain="association.example",
            official_status="association",
            homepage_url="https://association.example/",
        )
        session.add(source)
        await session.flush()
        document = Document(
            document_id="PHASE-J-ASSOCIATION",
            source_id=source.id,
            title="Association content",
            source_url="https://association.example/content",
            content="This content cannot satisfy official-only evaluation selection.",
            word_count=60,
            final_status="approved",
            manual_review_status="approved",
            index_status="indexed",
        )
        session.add(document)
        await session.flush()
        session.add(
            Chunk(
                chunk_id="phase-j-association-chunk",
                document_id=document.id,
                chunk_index=0,
                content=document.content,
                content_hash="association-hash",
                char_count=len(document.content),
                token_count=10,
                vector_status="indexed",
            )
        )
        await session.commit()

        dataset = await build_draft_evaluation_dataset(session, limit=100)

    assert dataset.question_count == 0
