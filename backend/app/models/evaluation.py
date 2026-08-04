from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import JSON_VALUE, Base, CreatedAtMixin, IdMixin, JsonObject, TimestampMixin

if TYPE_CHECKING:
    from app.models.observability import DataLineage


class EvaluationQuestion(IdMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_questions"
    __table_args__ = (
        Index("ix_evaluation_questions_verified_category", "verified", "category"),
        Index("ix_evaluation_questions_query_difficulty", "query_type", "difficulty"),
    )

    question_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    expected_document_ids: Mapped[list[str]] = mapped_column(
        JSON_VALUE, nullable=False, default=list
    )
    expected_chunk_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)
    expected_answer_points: Mapped[list[str]] = mapped_column(
        JSON_VALUE, nullable=False, default=list
    )
    expected_filters: Mapped[JsonObject] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    should_refuse: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )
    difficulty: Mapped[str | None] = mapped_column(String(32), index=True)
    category: Mapped[str | None] = mapped_column(String(128), index=True)
    created_by: Mapped[str | None] = mapped_column(String(255))
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )


class Experiment(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "experiments"
    __table_args__ = (
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="finish_not_before_start",
        ),
        Index("ix_experiments_status_created", "status", "created_at"),
    )

    experiment_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    experiment_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    baseline_config_json: Mapped[JsonObject] = mapped_column(
        JSON_VALUE, nullable=False, default=dict
    )
    candidate_config_json: Mapped[JsonObject] = mapped_column(
        JSON_VALUE, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conclusion: Mapped[str | None] = mapped_column(Text)
    artifact_path: Mapped[str | None] = mapped_column(String(4096))

    runs: Mapped[list[EvaluationRun]] = relationship(back_populates="experiment")


class EvaluationRun(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint("top_k > 0", name="top_k_positive"),
        CheckConstraint("question_count >= 0", name="question_count_nonnegative"),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="finish_not_before_start",
        ),
        CheckConstraint(
            "recall_at_1 IS NULL OR (recall_at_1 >= 0 AND recall_at_1 <= 1)",
            name="recall_at_1_range",
        ),
        CheckConstraint(
            "recall_at_5 IS NULL OR (recall_at_5 >= 0 AND recall_at_5 <= 1)",
            name="recall_at_5_range",
        ),
        CheckConstraint(
            "recall_at_10 IS NULL OR (recall_at_10 >= 0 AND recall_at_10 <= 1)",
            name="recall_at_10_range",
        ),
        CheckConstraint("mrr IS NULL OR (mrr >= 0 AND mrr <= 1)", name="mrr_range"),
        CheckConstraint("ndcg IS NULL OR (ndcg >= 0 AND ndcg <= 1)", name="ndcg_range"),
        CheckConstraint(
            "citation_accuracy IS NULL OR (citation_accuracy >= 0 AND citation_accuracy <= 1)",
            name="citation_accuracy_range",
        ),
        CheckConstraint(
            "refusal_accuracy IS NULL OR (refusal_accuracy >= 0 AND refusal_accuracy <= 1)",
            name="refusal_accuracy_range",
        ),
        CheckConstraint(
            "hallucination_rate IS NULL OR (hallucination_rate >= 0 AND hallucination_rate <= 1)",
            name="hallucination_rate_range",
        ),
        CheckConstraint(
            "average_latency IS NULL OR average_latency >= 0", name="average_latency_nonnegative"
        ),
        CheckConstraint("p95_latency IS NULL OR p95_latency >= 0", name="p95_latency_nonnegative"),
        CheckConstraint(
            "average_cost IS NULL OR average_cost >= 0", name="average_cost_nonnegative"
        ),
        Index("ix_evaluation_runs_experiment_created", "experiment_id", "created_at"),
        Index("ix_evaluation_runs_retrieval_prompt", "retrieval_version", "prompt_version"),
    )

    run_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    experiment_id: Mapped[int | None] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL"), index=True
    )
    retrieval_version: Mapped[str | None] = mapped_column(String(64), index=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), index=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    rerank_model: Mapped[str | None] = mapped_column(String(255))
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=10, server_default="10")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    question_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    recall_at_1: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    recall_at_5: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    recall_at_10: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    mrr: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    ndcg: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    citation_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    refusal_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    hallucination_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    average_latency: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    p95_latency: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    average_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    result_path: Mapped[str | None] = mapped_column(String(4096))

    experiment: Mapped[Experiment | None] = relationship(back_populates="runs")
    lineage_records: Mapped[list[DataLineage]] = relationship(back_populates="evaluation_run")
