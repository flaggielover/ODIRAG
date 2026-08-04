from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import JSON_VALUE, Base, CreatedAtMixin, IdMixin, JsonObject


class PromptVersion(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_name", "version", name="uq_prompt_versions_name_version"),
        Index("ix_prompt_versions_name_active", "prompt_name", "active"),
    )

    prompt_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    change_description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )


class RetrievalConfig(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "retrieval_configs"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_retrieval_configs_name_version"),
        CheckConstraint("vector_top_k > 0", name="vector_top_k_positive"),
        CheckConstraint("bm25_top_k > 0", name="bm25_top_k_positive"),
        CheckConstraint("rrf_k > 0", name="rrf_k_positive"),
        CheckConstraint("rerank_top_k > 0", name="rerank_top_k_positive"),
        CheckConstraint(
            "score_threshold >= 0 AND score_threshold <= 1", name="score_threshold_range"
        ),
        Index("ix_retrieval_configs_name_created", "name", "created_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    vector_top_k: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20, server_default="20"
    )
    bm25_top_k: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20, server_default="20"
    )
    fusion_method: Mapped[str] = mapped_column(
        String(64), nullable=False, default="rrf", server_default="rrf"
    )
    rrf_k: Mapped[int] = mapped_column(Integer, nullable=False, default=60, server_default="60")
    rerank_top_k: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )
    score_threshold: Mapped[Decimal] = mapped_column(
        Numeric(7, 6), nullable=False, default=0, server_default="0"
    )
    metadata_rules_json: Mapped[JsonObject] = mapped_column(
        JSON_VALUE, nullable=False, default=dict
    )
