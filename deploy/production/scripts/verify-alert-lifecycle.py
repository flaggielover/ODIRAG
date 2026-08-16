from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast

PROMETHEUS_URL = "http://127.0.0.1:9090"
ALERTMANAGER_URL = "http://127.0.0.1:9093"
POLL_SECONDS = 5.0


class LifecycleError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    container: str
    alert: str
    condition_query: str
    job: str
    instance: str
    service: str
    require_healthy: bool = False


SCENARIOS = {
    "node-exporter": Scenario(
        name="node-exporter",
        container="odirag-monitoring-node-exporter-1",
        alert="HostDown",
        condition_query='up{job="node"} == 0',
        job="node",
        instance="node-exporter:9100",
        service="host",
    ),
    "backend": Scenario(
        name="backend",
        container="odirag-prod-backend-1",
        alert="BackendDown",
        condition_query='up{job="backend"} == 0',
        job="backend",
        instance="backend:8000",
        service="backend",
        require_healthy=True,
    ),
}


def _api_json(base_url: str, path: str) -> dict[str, Any] | list[Any]:
    with urllib.request.urlopen(f"{base_url}{path}", timeout=10) as response:
        return cast(dict[str, Any] | list[Any], json.load(response))


def _prometheus_query(expression: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"query": expression})
    payload = _api_json(PROMETHEUS_URL, f"/api/v1/query?{query}")
    if not isinstance(payload, dict):
        raise LifecycleError("prometheus_query_response_invalid")
    result = payload.get("data", {}).get("result", [])
    return result if isinstance(result, list) else []


def _rule_state(alert_name: str) -> str:
    payload = _api_json(PROMETHEUS_URL, "/api/v1/rules?type=alert")
    if not isinstance(payload, dict):
        raise LifecycleError("prometheus_rules_response_invalid")
    for group in payload.get("data", {}).get("groups", []):
        for rule in group.get("rules", []):
            if rule.get("name") == alert_name:
                return str(rule.get("state", "unknown"))
    return "missing"


def _alertmanager_has(scenario: Scenario, *, not_before: datetime | None = None) -> bool:
    payload = _api_json(ALERTMANAGER_URL, "/api/v2/alerts")
    if not isinstance(payload, list):
        raise LifecycleError("alertmanager_alerts_response_invalid")
    for alert in payload:
        labels = alert.get("labels", {})
        if not all(
            (
                labels.get("alertname") == scenario.alert,
                labels.get("job") == scenario.job,
                labels.get("instance") == scenario.instance,
                labels.get("service") == scenario.service,
                alert.get("status", {}).get("state") == "active",
            )
        ):
            continue
        if not_before is None:
            return True
        starts_at = str(alert.get("startsAt", ""))
        try:
            started = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if started >= not_before - timedelta(seconds=5):
            return True
    return False


def _docker(*arguments: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["docker", *arguments],
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=45,
    )
    if result.returncode != 0:
        raise LifecycleError("docker_command_failed")
    return result.stdout.strip() if capture else ""


def _container_ready(scenario: Scenario) -> bool:
    template = "{{.State.Running}}"
    if scenario.require_healthy:
        template = "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}"
    state = _docker("inspect", "--format", template, scenario.container, capture=True)
    return state == ("healthy" if scenario.require_healthy else "true")


def _ensure_container_ready(scenario: Scenario) -> float:
    _docker("start", scenario.container)
    return _wait_for(
        lambda: _container_ready(scenario),
        timeout_seconds=300,
        failure_code="container_recovery_timeout",
    )


def _wait_for(
    predicate: Callable[[], bool],
    *,
    timeout_seconds: float,
    failure_code: str,
) -> float:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return time.monotonic()
        except InterruptedError:
            raise
        except (OSError, TimeoutError, urllib.error.URLError, LifecycleError):
            pass
        time.sleep(POLL_SECONDS)
    raise LifecycleError(failure_code)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(  # noqa: UP017 - host Python 3.10
        timespec="milliseconds"
    )


def _install_signal_handlers() -> None:
    def interrupted(signum: int, _frame: object) -> None:
        raise InterruptedError(f"signal_{signum}")

    signums = [signal.SIGINT, signal.SIGTERM]
    sighup = getattr(signal, "SIGHUP", None)
    if sighup is not None:
        signums.append(sighup)
    for signum in signums:
        signal.signal(signum, interrupted)


def run(scenario: Scenario) -> None:
    if not _container_ready(scenario):
        raise LifecycleError("precondition_container_not_ready")
    if _rule_state(scenario.alert) != "inactive":
        raise LifecycleError("precondition_alert_not_inactive")
    if _prometheus_query(scenario.condition_query):
        raise LifecycleError("precondition_fault_condition_active")
    if _alertmanager_has(scenario):
        raise LifecycleError("precondition_alertmanager_alert_active")

    timestamps: dict[str, str] = {}
    monotonic: dict[str, float] = {}
    t0_datetime: datetime | None = None
    lifecycle_complete = False
    try:
        _docker("stop", "--time", "10", scenario.container)
        timestamps["T0"] = _utc_now()
        t0_datetime = datetime.now(timezone.utc)  # noqa: UP017 - host Python 3.10
        monotonic["T0"] = time.monotonic()
        print(f"scenario={scenario.name} event=T0 fault_injected at={timestamps['T0']}", flush=True)

        monotonic["T1"] = _wait_for(
            lambda: bool(_prometheus_query(scenario.condition_query)),
            timeout_seconds=75,
            failure_code="prometheus_condition_timeout",
        )
        timestamps["T1"] = _utc_now()
        print(
            f"scenario={scenario.name} event=T1 condition_observed at={timestamps['T1']}",
            flush=True,
        )

        monotonic["T2_pending"] = _wait_for(
            lambda: _rule_state(scenario.alert) in {"pending", "firing"},
            timeout_seconds=75,
            failure_code="alert_pending_timeout",
        )
        timestamps["T2_pending"] = _utc_now()
        print(
            f"scenario={scenario.name} event=T2_pending alert={scenario.alert} "
            f"at={timestamps['T2_pending']}",
            flush=True,
        )

        monotonic["T2_firing"] = _wait_for(
            lambda: _rule_state(scenario.alert) == "firing",
            timeout_seconds=210,
            failure_code="alert_firing_timeout",
        )
        timestamps["T2_firing"] = _utc_now()
        print(
            f"scenario={scenario.name} event=T2_firing alert={scenario.alert} "
            f"at={timestamps['T2_firing']}",
            flush=True,
        )

        monotonic["T3"] = _wait_for(
            lambda: _alertmanager_has(scenario, not_before=t0_datetime),
            timeout_seconds=120,
            failure_code="alertmanager_receipt_timeout",
        )
        timestamps["T3"] = _utc_now()
        print(
            f"scenario={scenario.name} event=T3 alertmanager_received at={timestamps['T3']}",
            flush=True,
        )

        recovery_started = _utc_now()
        print(
            f"scenario={scenario.name} event=recovery_started at={recovery_started}",
            flush=True,
        )

        _ensure_container_ready(scenario)
        _wait_for(
            lambda: not _prometheus_query(scenario.condition_query),
            timeout_seconds=120,
            failure_code="prometheus_condition_recovery_timeout",
        )
        timestamps["T5"] = _utc_now()
        monotonic["T5"] = time.monotonic()
        print(
            f"scenario={scenario.name} event=T5 fault_recovered at={timestamps['T5']}",
            flush=True,
        )
        _wait_for(
            lambda: _rule_state(scenario.alert) == "inactive",
            timeout_seconds=120,
            failure_code="prometheus_alert_resolution_timeout",
        )
        monotonic["T6"] = _wait_for(
            lambda: not _alertmanager_has(scenario, not_before=t0_datetime),
            timeout_seconds=180,
            failure_code="alertmanager_resolution_timeout",
        )
        timestamps["T6"] = _utc_now()
        print(f"scenario={scenario.name} event=T6 alert_resolved at={timestamps['T6']}", flush=True)
        lifecycle_complete = True
    finally:
        try:
            _ensure_container_ready(scenario)
            if not lifecycle_complete:
                print(f"scenario={scenario.name} emergency_recovery=CONFIRMED", flush=True)
        except Exception:
            print(f"scenario={scenario.name} emergency_recovery=FAILED", file=sys.stderr)
            raise LifecycleError("emergency_recovery_failed") from None

    print(
        f"scenario={scenario.name} status=PASS-LIVE alert={scenario.alert} "
        f"detection_seconds={monotonic['T1'] - monotonic['T0']:.3f} "
        f"pending_seconds={monotonic['T2_pending'] - monotonic['T0']:.3f} "
        f"firing_seconds={monotonic['T2_firing'] - monotonic['T0']:.3f} "
        f"delivery_seconds={monotonic['T3'] - monotonic['T2_firing']:.3f} "
        f"resolution_seconds={monotonic['T6'] - monotonic['T5']:.3f} "
        "external_delivery=BLOCKED",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    arguments = parser.parse_args()
    _install_signal_handlers()
    run(SCENARIOS[arguments.scenario])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"alert_lifecycle=FAIL error_type={type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
