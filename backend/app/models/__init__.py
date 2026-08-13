"""Aggregate import for all SQLAlchemy models.

Importing this module registers every table on ``Base.metadata`` for migrations,
tests, and application startup.
"""

from app.models.configuration import PromptVersion, RetrievalConfig
from app.models.document import (
    Attachment,
    Chunk,
    Document,
    DocumentMetadataCorrection,
    DocumentReview,
    DocumentVersion,
    StructuredKnowledge,
)
from app.models.evaluation import EvaluationQuestion, EvaluationRun, Experiment
from app.models.observability import Alert, DataLineage, QueryTrace, UserFeedback
from app.models.source import CozeInvocation, CrawlTask, CrawlTaskFailure, Source, SourceColumn
from app.models.source_discovery import (
    SourceCandidate,
    SourceCandidateColumn,
    SourceDiscoveryEvent,
    SourceDiscoveryRun,
)
from app.models.user import User

__all__ = [
    "Alert",
    "Attachment",
    "Chunk",
    "CozeInvocation",
    "CrawlTask",
    "CrawlTaskFailure",
    "DataLineage",
    "Document",
    "DocumentMetadataCorrection",
    "DocumentReview",
    "DocumentVersion",
    "EvaluationQuestion",
    "EvaluationRun",
    "Experiment",
    "PromptVersion",
    "QueryTrace",
    "RetrievalConfig",
    "Source",
    "SourceCandidate",
    "SourceCandidateColumn",
    "SourceColumn",
    "SourceDiscoveryEvent",
    "SourceDiscoveryRun",
    "StructuredKnowledge",
    "User",
    "UserFeedback",
]
