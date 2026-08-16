from __future__ import annotations

# ruff: noqa: I001

import argparse
import asyncio
import hashlib
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote

from sqlalchemy import select

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings
from app.database.session import DatabaseManager
from app.models import (
    Attachment,
    CrawlTask,
    DataLineage,
    Document,
    DocumentReview,
    DocumentVersion,
    EvaluationQuestion,
    Experiment,
    Source,
    SourceColumn,
)

DEMO_NAMESPACE = uuid.UUID("b5898c35-2369-4dd5-810a-bab86fe470fb")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed an ODIRAG database with local demo data"
    )
    parser.add_argument(
        "--database-url",
        default=f"sqlite+aiosqlite:///{(BACKEND_ROOT / '.test-data/ui-demo.db').as_posix()}",
    )
    parser.add_argument(
        "--index",
        action="store_true",
        help="Run the real configured indexing pipeline for approved demo documents.",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run the verified demo question through the real chat/evaluation pipeline.",
    )
    return parser.parse_args()


async def _seed(
    database_url: str,
    *,
    index: bool = False,
    evaluate: bool = False,
) -> None:
    if evaluate and not index:
        raise ValueError("--evaluate requires --index")
    _ensure_sqlite_parent(database_url)
    settings = Settings(database_url=database_url, bootstrap_admin=False)
    database = DatabaseManager(settings)
    await database.create_schema()
    approved_document_ids: list[int] = []
    try:
        async with database.session_factory() as session:
            existing = await session.scalar(
                select(Source).where(Source.source_key == "demo-sichuan-policy")
            )
            if existing is not None:
                approved_document_ids = list(
                    await session.scalars(
                        select(Document.id)
                        .join(Source, Source.id == Document.source_id)
                        .where(
                            Source.source_key.in_(
                                ["demo-sichuan-policy", "demo-chengdu-policy"]
                            ),
                            Document.final_status == "approved",
                        )
                    )
                )
                print("Demo data already exists; base records were not duplicated.")
                if index:
                    await session.close()
                    await _run_demo_pipeline(
                        database,
                        settings,
                        approved_document_ids,
                        evaluate=evaluate,
                    )
                return

            now = datetime.now(UTC)
            source = Source(
                source_key="demo-sichuan-policy",
                name="四川省政策公开平台",
                domain="policy.sc.gov.cn",
                region="四川省",
                organization_level="provincial",
                organization_type="government",
                official_status="official",
                homepage_url="https://www.sc.gov.cn/",
                priority=100,
                crawl_frequency="daily",
                last_crawl_time=now - timedelta(hours=2),
            )
            city_source = Source(
                source_key="demo-chengdu-policy",
                name="成都市企业服务平台",
                domain="cdenterprise.chengdu.gov.cn",
                region="四川省",
                city="成都市",
                organization_level="municipal",
                organization_type="government",
                official_status="official",
                homepage_url="https://www.chengdu.gov.cn/",
                priority=80,
                crawl_frequency="daily",
                last_crawl_time=now - timedelta(hours=5),
            )
            source_column = SourceColumn(
                source=source,
                column_key="industry-policies",
                column_name="产业政策",
                column_url="https://www.sc.gov.cn/10462/10464/10797/index.shtml",
                max_pages=20,
                request_interval_seconds=1,
            )
            city_column = SourceColumn(
                source=city_source,
                column_key="enterprise-support",
                column_name="企业扶持",
                column_url="https://www.chengdu.gov.cn/chengdu/c152282/list.shtml",
                max_pages=10,
                request_interval_seconds=1,
            )
            session.add_all([source, city_source])
            await session.flush()

            completed_task = CrawlTask(
                source_column=source_column,
                task_type="incremental",
                trigger_type="schedule",
                status="completed",
                started_at=now - timedelta(hours=2, minutes=12),
                finished_at=now - timedelta(hours=2),
                discovered_count=18,
                fetched_count=18,
                success_count=16,
                url_duplicate_count=1,
                content_duplicate_count=1,
            )
            failed_task = CrawlTask(
                source_column=city_column,
                task_type="incremental",
                trigger_type="schedule",
                status="failed",
                started_at=now - timedelta(hours=5, minutes=4),
                finished_at=now - timedelta(hours=5),
                discovered_count=8,
                fetched_count=4,
                success_count=3,
                failed_count=1,
                retry_count=1,
                error_message="Remote endpoint returned HTTP 503",
            )
            session.add_all([completed_task, failed_task])

            documents = _documents(source, source_column, city_source, city_column, now)
            session.add_all(documents)
            await session.flush()

            versions: dict[int, DocumentVersion] = {}
            for document in documents:
                version = DocumentVersion(
                    document_id=document.id,
                    version=document.version,
                    content_hash=document.content_hash or _hash(document.content),
                    content=document.content,
                    metadata_json={
                        "seed": "local-demo",
                        "source_url": document.source_url,
                    },
                    changed_fields_json=["content", "publish_date"],
                )
                session.add(version)
                versions[document.id] = version

            attachment = Attachment(
                document_id=documents[0].id,
                attachment_name="申报材料清单.pdf",
                source_url="https://www.sc.gov.cn/demo/application-materials.pdf",
                mime_type="application/pdf",
                file_extension=".pdf",
                file_size=286_720,
                file_hash=_hash("demo-attachment"),
                download_status="completed",
                parse_status="completed",
                parsed_text="申报书、营业执照、研发投入证明。",
                page_count=6,
            )
            session.add(attachment)
            session.add(
                DocumentReview(
                    document_id=documents[0].id,
                    review_type="llm",
                    reviewer="demo-reviewer",
                    decision="approve",
                    quality_score=Decimal("0.9400"),
                    document_type="industry_policy",
                    topics_json=["软件产业", "研发补助"],
                    summary="政策主体、支持范围和申报期限清晰。",
                    reasons_json=["official_source", "complete_policy_fields"],
                    extracted_fields_json={
                        "support_measures": {
                            "value": "研发投入补助最高 200 万元",
                            "confidence": 0.96,
                        }
                    },
                    model_name="demo-review-model",
                    prompt_name="document_review",
                    prompt_version="v1",
                )
            )
            await session.flush()

            for document in documents:
                task = (
                    completed_task if document.source_id == source.id else failed_task
                )
                session.add(
                    DataLineage(
                        lineage_id=_stable_id(
                            f"lineage:document:{document.document_id}"
                        ),
                        source_id=document.source_id,
                        crawl_task_id=task.id,
                        document_id=document.id,
                        document_version_id=versions[document.id].id,
                        attachment_id=(
                            attachment.id if document.id == documents[0].id else None
                        ),
                    )
                )

            question = EvaluationQuestion(
                question_id="demo-rd-support",
                question="软件企业研发投入支持措施",
                query_type="rag",
                expected_document_ids=[documents[0].document_id],
                expected_chunk_ids=[],
                expected_answer_points=["最高 200 万元"],
                expected_filters={"region": "四川省"},
                difficulty="easy",
                category="research_support",
                created_by="demo-seed",
                verified=True,
            )
            experiment = Experiment(
                experiment_name="demo_chunk_600_vs_800",
                experiment_type="retrieval",
                baseline_config_json={"chunk_size": 600, "top_k": 5},
                candidate_config_json={"chunk_size": 800, "top_k": 5},
                status="pending",
            )
            session.add_all([question, experiment])
            await session.commit()
            approved_document_ids = [
                document.id
                for document in documents
                if document.final_status == "approved"
            ]
            print(
                f"Seeded {len(documents)} documents, one verified evaluation question, "
                "and one pending experiment without fabricated metrics."
            )
        if index:
            await _run_demo_pipeline(
                database,
                settings,
                approved_document_ids,
                evaluate=evaluate,
            )
    finally:
        await database.dispose()


async def _run_demo_pipeline(
    database: DatabaseManager,
    settings: Settings,
    document_ids: list[int],
    *,
    evaluate: bool,
) -> None:
    from app.rag import GroundingService
    from app.repositories.chat import ChatRepository
    from app.repositories.evaluation import EvaluationRepository
    from app.repositories.indexing import IndexRepository
    from app.router import QueryRouter
    from app.runtime import build_application_runtime, resolve_runtime_path
    from app.schemas.evaluation import EvaluationRunRequest
    from app.services.bm25 import BM25RebuildService
    from app.services.chat import ChatService
    from app.services.evaluation import EvaluationApplicationService
    from app.services.indexing import IndexingService

    runtime = build_application_runtime(settings)
    async with database.session_factory() as session:
        index_repository = IndexRepository(session)
        indexing_service = IndexingService(
            index_repository,
            runtime.chunker,
            runtime.embedding_batcher,
            runtime.vector_store,
            dimensions=settings.embedding_dimensions,
            embedding_version=settings.embedding_version,
        )
        for document_id in document_ids:
            result = await indexing_service.index_document(document_id)
            print(
                f"Indexed demo document {document_id}: "
                f"{result.chunk_count} chunks, {result.embedded_count} embeddings."
            )
        runtime.bm25_index = await BM25RebuildService(index_repository).build_index()
        runtime.bm25_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        runtime.bm25_index.save(runtime.bm25_snapshot_path)
        print(
            f"Rebuilt BM25 snapshot with {runtime.bm25_index.document_count} documents."
        )
        if not evaluate:
            return

        chat_service = ChatService(
            ChatRepository(session),
            QueryRouter(),
            runtime.retrieval_engine(),
            GroundingService(
                minimum_hits=settings.grounding_minimum_hits,
                minimum_score=settings.grounding_minimum_score,
                require_official_source=settings.grounding_require_official_source,
                refuse_on_conflict=settings.grounding_refuse_on_conflict,
            ),
            orchestrator=runtime.llm_orchestrator,
            prompt=runtime.grounded_answer_prompt,
            prompt_version=runtime.grounded_answer_prompt_version,
        )
        evaluation_service = EvaluationApplicationService(
            EvaluationRepository(session),
            chat_service,
            artifact_root=resolve_runtime_path(settings.evaluation_artifact_dir),
            embedding_model=runtime.embedding_provider.model_name,
            rerank_model=runtime.rerank_provider.model_name,
            default_retrieval_version="hybrid-rrf-rerank-v1",
            default_prompt_version=runtime.grounded_answer_prompt_version,
        )
        run = await evaluation_service.run(
            EvaluationRunRequest(
                run_name=f"demo-policy-regression-{datetime.now(UTC):%Y%m%dT%H%M%SZ}",
                question_ids=["demo-rd-support"],
                top_k=settings.retrieval_final_top_k,
            )
        )
        print(
            f"Completed real demo evaluation run {run.id}: "
            f"{run.question_count} question, P95 {run.p95_latency} ms."
        )


def _ensure_sqlite_parent(database_url: str) -> None:
    prefixes = ("sqlite+aiosqlite:///", "sqlite+pysqlite:///", "sqlite:///")
    prefix = next((item for item in prefixes if database_url.startswith(item)), None)
    if prefix is None:
        return
    raw_path = unquote(database_url[len(prefix) :])
    if raw_path in {"", ":memory:"}:
        return
    database_path = Path(raw_path)
    if not database_path.is_absolute():
        database_path = (Path.cwd() / database_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)


def _documents(
    source: Source,
    source_column: SourceColumn,
    city_source: Source,
    city_column: SourceColumn,
    now: datetime,
) -> list[Document]:
    contents = [
        (
            "四川省软件产业高质量发展支持办法",
            (
                "# 支持对象\n\n在四川省依法登记、具有独立法人资格的软件企业。\n\n"
                "# 支持措施\n\n对符合条件的研发投入给予补助，单个项目最高 200 万元。\n\n"
                "# 申报期限\n\n本年度申报截止日期为 2026 年 9 月 30 日。"
            ),
        ),
        (
            "成都市中小企业数字化转型补贴实施细则",
            (
                "# 适用范围\n\n成都市行政区域内的中小企业。\n\n"
                "# 补贴标准\n\n数字化改造项目按核定投入的 30% 给予补贴，最高 80 万元。"
            ),
        ),
        (
            "人工智能产业项目申报通知（待审核）",
            (
                "# 申报方向\n\n支持人工智能基础软件和行业应用项目。\n\n"
                "# 状态\n\n该文档等待人工审核，不应进入生产检索。"
            ),
        ),
    ]
    documents = [
        Document(
            document_id=_stable_id("document:software-support"),
            source=source,
            source_column=source_column,
            title=contents[0][0],
            source_url="https://www.sc.gov.cn/demo/software-support.html",
            publish_date=(now - timedelta(days=35)).date(),
            issuing_authority="四川省经济和信息化厅",
            document_number="川经信软件〔2026〕18号",
            region="四川省",
            document_type="industry_policy",
            content=contents[0][1],
            raw_content=contents[0][1],
            content_hash=_hash(contents[0][1]),
            word_count=len(contents[0][1]),
            language="zh-CN",
            quality_score=Decimal("0.9400"),
            rule_filter_status="approved",
            llm_review_status="approved",
            manual_review_status="approved",
            final_status="approved",
            index_status="pending",
            version=2,
            first_crawl_time=now - timedelta(days=34),
            last_crawl_time=now - timedelta(hours=2),
        ),
        Document(
            document_id=_stable_id("document:digital-subsidy"),
            source=city_source,
            source_column=city_column,
            title=contents[1][0],
            source_url="https://www.chengdu.gov.cn/demo/digital-subsidy.html",
            publish_date=(now - timedelta(days=12)).date(),
            issuing_authority="成都市经济和信息化局",
            document_number="成经信发〔2026〕42号",
            region="四川省",
            city="成都市",
            document_type="funding_policy",
            content=contents[1][1],
            raw_content=contents[1][1],
            content_hash=_hash(contents[1][1]),
            word_count=len(contents[1][1]),
            language="zh-CN",
            quality_score=Decimal("0.9000"),
            rule_filter_status="approved",
            llm_review_status="approved",
            manual_review_status="approved",
            final_status="approved",
            index_status="pending",
            version=1,
            first_crawl_time=now - timedelta(days=11),
            last_crawl_time=now - timedelta(hours=5),
        ),
        Document(
            document_id=_stable_id("document:ai-pending"),
            source=source,
            source_column=source_column,
            title=contents[2][0],
            source_url="https://www.sc.gov.cn/demo/ai-pending.html",
            publish_date=(now - timedelta(days=2)).date(),
            issuing_authority="四川省科学技术厅",
            region="四川省",
            document_type="application_notice",
            content=contents[2][1],
            raw_content=contents[2][1],
            content_hash=_hash(contents[2][1]),
            word_count=len(contents[2][1]),
            language="zh-CN",
            quality_score=Decimal("0.7200"),
            rule_filter_status="approved",
            llm_review_status="pending",
            manual_review_status="pending",
            final_status="pending",
            index_status="pending",
            version=1,
            first_crawl_time=now - timedelta(days=1),
            last_crawl_time=now - timedelta(hours=2),
        ),
    ]
    return documents


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_id(value: str) -> str:
    return str(uuid.uuid5(DEMO_NAMESPACE, value))


if __name__ == "__main__":
    arguments = _arguments()
    asyncio.run(
        _seed(
            arguments.database_url,
            index=arguments.index,
            evaluate=arguments.evaluate,
        )
    )
