from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.metrics import CONTENT_TYPE_LATEST, MetricsRegistry

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    """Expose the private in-process Prometheus registry.

    This route is intentionally mounted only on the backend application.  No
    public reverse-proxy location or credential-bearing payload is involved.
    A collector failure returns a generic 503 and never exposes exception text.
    """

    registry = getattr(request.app.state, "metrics", None)
    if not isinstance(registry, MetricsRegistry):
        return Response(status_code=503)
    try:
        payload = registry.prometheus_payload()
    except Exception:
        return Response(status_code=503)
    return Response(
        content=payload,
        media_type=None,
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
