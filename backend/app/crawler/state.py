from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from app.models import CrawlTask


class InvalidTaskTransitionError(ValueError):
    """Raised when a crawl task is asked to enter an invalid state."""


class CrawlTaskStateMachine:
    transitions: ClassVar[dict[str, set[str]]] = {
        "pending": {"queued", "running", "failed", "cancelled"},
        "queued": {"running", "calling_coze", "failed", "cancelled"},
        "running": {"calling_coze", "completed", "failed", "cancelled"},
        "calling_coze": {"coze_running", "normalizing", "failed", "cancelled"},
        "coze_running": {"normalizing", "failed", "cancelled"},
        "normalizing": {"saving_documents", "failed", "cancelled"},
        "saving_documents": {"waiting_review", "completed", "partial_failed", "failed"},
        "waiting_review": {"completed", "partial_failed", "failed", "cancelled"},
        "partial_failed": {"pending", "waiting_review", "completed"},
        "failed": {"pending"},
        "cancelled": {"pending"},
        "completed": set(),
    }

    def transition(self, task: CrawlTask, target: str, *, error: str | None = None) -> None:
        allowed = self.transitions.get(task.status, set())
        if target not in allowed:
            raise InvalidTaskTransitionError(
                f"cannot transition crawl task from {task.status} to {target}"
            )
        now = datetime.now(UTC)
        task.status = target
        task.current_stage = target
        if target == "running":
            task.started_at = now
            task.finished_at = None
            task.error_message = None
        elif target == "waiting_review":
            task.finished_at = None
            task.completed_at = None
            task.provider_error_code = None
            task.provider_error_message = None
            task.next_retry_at = None
        elif target in {"completed", "partial_failed", "failed", "cancelled"}:
            task.finished_at = now
            task.completed_at = now
            task.error_message = error
        elif target == "pending":
            task.started_at = None
            task.finished_at = None
            task.error_message = None
            task.provider_error_code = None
            task.provider_error_message = None
            task.next_retry_at = None
            task.completed_at = None
            task.current_stage = "pending"
            task.discovered_count = 0
            task.fetched_count = 0
            task.success_count = 0
            task.url_duplicate_count = 0
            task.content_duplicate_count = 0
            task.semantic_duplicate_count = 0
            task.failed_count = 0
            task.accepted_count = 0
            task.rejected_count = 0
            task.pending_review_count = 0
            task.provider_status = None
            task.provider_error_code = None
            task.provider_error_message = None
            task.provider_task_id = None
            task.coze_execution_id = None
            task.next_retry_at = None
