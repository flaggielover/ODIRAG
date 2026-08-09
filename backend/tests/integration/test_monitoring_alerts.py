from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.models import CrawlTask, Document, Experiment, QueryTrace, Source, SourceColumn


async def test_operational_metrics_create_and_manage_real_alerts(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    settings = app.state.settings
    settings.alert_minimum_sample_size = 1
    settings.alert_crawl_failure_rate = 0.5
    settings.alert_index_failure_count = 1
    settings.alert_chat_p95_ms = 100
    settings.alert_evaluation_regression_count = 1
    settings.alert_average_cost = 0.5

    async with app.state.database.session_factory() as session:
        source = Source(
            source_key=f"monitor-source-{uuid.uuid4()}",
            name="Monitor Government",
            domain="monitor.gov",
            homepage_url="https://monitor.gov/",
            official_status="official",
        )
        column = SourceColumn(
            source=source,
            column_key="monitor",
            column_name="Monitor",
            column_url="https://monitor.gov/policies",
            request_interval_seconds=0,
        )
        task = CrawlTask(
            source_column=column,
            task_type="incremental",
            trigger_type="scheduled",
            status="failed",
            discovered_count=1,
            fetched_count=1,
            failed_count=1,
            error_message="fixture failure",
        )
        document = Document(
            document_id=str(uuid.uuid4()),
            source=source,
            source_column=column,
            title="Failed index fixture",
            source_url="https://monitor.gov/policies/failed",
            content="Monitoring fixture content.",
            word_count=3,
            final_status="approved",
            index_status="failed",
            version=1,
        )
        trace = QueryTrace(
            trace_id=str(uuid.uuid4()),
            user_query="Slow expensive query",
            query_type="rag",
            parsed_filters_json={},
            bm25_results_json=[],
            vector_results_json=[],
            fusion_results_json=[],
            rerank_results_json=[],
            final_context_json=[],
            prompt_version="v1",
            prompt_snapshot_json={"version": "v1", "content": "Grounded prompt"},
            evidence_decision_json={
                "sufficient": True,
                "confidence": 0.9,
                "latency_ms": 3.5,
            },
            model_name="fixture-model",
            answer="Fixture answer",
            citations_json=[],
            refusal=False,
            latency_ms=6000,
            token_usage_json={"total_tokens": 200},
            cost=Decimal("2.0"),
        )
        experiment = Experiment(
            experiment_name=f"regression-{uuid.uuid4().hex}",
            experiment_type="retrieval",
            baseline_config_json={"top_k": 5},
            candidate_config_json={"top_k": 1},
            status="completed",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            conclusion="Regression detected. Fixture.",
        )
        session.add_all([task, document, trace, experiment])
        await session.commit()

    metrics = await client.get("/api/system/metrics", headers=auth_headers)
    assert metrics.status_code == 200, metrics.text
    metric_body = metrics.json()
    assert metric_body["crawler"]["task_failure_rate"] == 1.0
    assert metric_body["knowledge"]["index_failure_count"] == 1
    assert metric_body["rag"]["p95_latency_ms"] == 6000
    assert metric_body["rag"]["total_tokens"] == 200
    assert float(metric_body["rag"]["average_cost"]) == 2.0
    assert metric_body["rag"]["evaluation_regression_count"] == 1
    assert metric_body["rag"]["evidence_assessed_count"] == 1
    assert metric_body["rag"]["evidence_sufficiency_rate"] == 1.0
    assert metric_body["rag"]["citation_rate"] == 0.0

    alerts = await client.get("/api/system/alerts", headers=auth_headers)
    assert alerts.status_code == 200, alerts.text
    alert_body = alerts.json()
    types = {item["alert_type"] for item in alert_body}
    assert {
        "high_failure_rate",
        "index_failures",
        "service_unavailable",
        "latency_regression",
        "evaluation_regression",
        "abnormal_cost",
    }.issubset(types)

    selected = next(item for item in alert_body if item["alert_type"] == "index_failures")
    acknowledged = await client.post(
        f"/api/system/alerts/{selected['id']}/acknowledge",
        headers=auth_headers,
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"

    resolved = await client.post(
        f"/api/system/alerts/{selected['id']}/resolve",
        headers=auth_headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    stored = await client.get(
        "/api/system/alerts",
        params={"refresh": "false", "status": "resolved"},
        headers=auth_headers,
    )
    assert stored.status_code == 200
    assert any(item["id"] == selected["id"] for item in stored.json())
