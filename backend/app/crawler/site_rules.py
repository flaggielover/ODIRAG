from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SiteRules:
    """Typed, auditable site-specific hints used by the generic crawler.

    Rules are intentionally data-only.  They can live in ``pagination_json`` or
    ``selectors_json`` under ``site_rules`` today, and can be promoted to a
    dedicated configuration table later without changing crawler behavior.
    """

    host: str | None = None
    mode: str = "html"
    list: dict[str, Any] = field(default_factory=dict)
    pagination: dict[str, Any] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)
    attachments: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> SiteRules:
        if not value:
            return cls()
        return cls(
            host=_string(value.get("host")),
            mode=_string(value.get("mode")) or "html",
            list=_mapping(value.get("list")),
            pagination=_mapping(value.get("pagination")),
            detail=_mapping(value.get("detail")),
            attachments=_mapping(value.get("attachments")),
            enabled=value.get("enabled", True) is not False,
        )

    def merged(self) -> dict[str, Any]:
        """Flatten list/pagination hints for the existing selector contract."""

        values: dict[str, Any] = {
            **self.list,
            **self.pagination,
            "mode": self.mode,
        }
        if self.host:
            values["host"] = self.host
        if self.detail:
            values["detail"] = dict(self.detail)
        if self.attachments:
            values["attachments"] = dict(self.attachments)
        return values


def site_rules_from_configs(
    selectors: Mapping[str, Any] | None,
    pagination: Mapping[str, Any] | None,
) -> SiteRules:
    selectors = selectors or {}
    pagination = pagination or {}
    raw = pagination.get("site_rules") or selectors.get("site_rules")
    if isinstance(raw, Mapping):
        return SiteRules.from_mapping(raw)
    return SiteRules()


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
