"""Tools for detecting operational anomalies across the fleet."""

import json
from datetime import datetime
from typing import Any

from langchain_core.tools import tool

from fleet_health.config import settings
from fleet_health.schemas.models import Anomaly, AnomalyType, Severity


def detect_fuel_anomalies(bunker_logs: list[dict[str, Any]]) -> list[Anomaly]:
    anomalies: list[Anomaly] = []
    threshold = settings.fuel_overconsumption_pct

    for log in bunker_logs:
        variance = log.get("variance_pct", 0)
        if variance > threshold:
            severity = Severity.HIGH if variance > 20 else Severity.MEDIUM
            anomalies.append(
                Anomaly(
                    vessel_id=log["vessel_id"],
                    anomaly_type=AnomalyType.FUEL_OVERCONSUMPTION,
                    severity=severity,
                    description=(
                        f"Fuel overconsumption of {variance:.1f}% during "
                        f"{log.get('voyage_phase', 'voyage')} "
                        f"({log['consumed_mt']} MT vs expected {log['expected_mt']} MT)"
                    ),
                    metric_value=variance,
                    threshold_value=threshold,
                )
            )
    return anomalies


def detect_schedule_anomalies(port_calls: list[dict[str, Any]]) -> list[Anomaly]:
    anomalies: list[Anomaly] = []
    threshold = settings.schedule_slippage_hours

    for call in port_calls:
        for slip_field, label in [
            ("arrival_slippage_hours", "arrival"),
            ("departure_slippage_hours", "departure"),
        ]:
            slippage = call.get(slip_field)
            if slippage is not None and slippage > threshold:
                severity = Severity.HIGH if slippage > 12 else Severity.MEDIUM
                anomalies.append(
                    Anomaly(
                        vessel_id=call["vessel_id"],
                        anomaly_type=AnomalyType.SCHEDULE_SLIPPAGE,
                        severity=severity,
                        description=(
                            f"Port {label} slippage of {slippage:.1f}h at "
                            f"{call['port_name']} (threshold: {threshold}h)"
                        ),
                        metric_value=slippage,
                        threshold_value=threshold,
                    )
                )
    return anomalies


def detect_maintenance_anomalies(
    alerts: list[dict[str, Any]],
) -> list[Anomaly]:
    anomalies: list[Anomaly] = []
    threshold_days = settings.maintenance_overdue_days

    for alert in alerts:
        if not alert.get("is_overdue"):
            continue
        days_overdue = alert["days_overdue"]
        base_severity = Severity(alert.get("severity", "medium"))
        severity = (
            Severity.CRITICAL
            if base_severity == Severity.CRITICAL
            else Severity.HIGH
            if days_overdue > threshold_days
            else Severity.MEDIUM
        )
        anomalies.append(
            Anomaly(
                vessel_id=alert["vessel_id"],
                anomaly_type=AnomalyType.OVERDUE_MAINTENANCE,
                severity=severity,
                description=(
                    f"Overdue maintenance: {alert['equipment']} - "
                    f"{alert['description']} ({days_overdue} days overdue)"
                ),
                metric_value=float(days_overdue),
                threshold_value=float(threshold_days),
            )
        )
    return anomalies


def detect_all_anomalies(
    bunker_logs: list[dict[str, Any]],
    port_calls: list[dict[str, Any]],
    maintenance_alerts: list[dict[str, Any]],
) -> list[Anomaly]:
    return (
        detect_fuel_anomalies(bunker_logs)
        + detect_schedule_anomalies(port_calls)
        + detect_maintenance_anomalies(maintenance_alerts)
    )


@tool
def detect_fuel_overconsumption(bunker_logs_json: str) -> str:
    """Detect fuel overconsumption anomalies from normalised bunker logs JSON."""
    logs = json.loads(bunker_logs_json)
    anomalies = detect_fuel_anomalies(logs)
    return json.dumps([a.model_dump(mode="json") for a in anomalies], indent=2)


@tool
def detect_schedule_slippage(port_calls_json: str) -> str:
    """Detect port schedule slippage anomalies from normalised port calls JSON."""
    calls = json.loads(port_calls_json)
    anomalies = detect_schedule_anomalies(calls)
    return json.dumps([a.model_dump(mode="json") for a in anomalies], indent=2)


@tool
def detect_overdue_maintenance(alerts_json: str) -> str:
    """Detect overdue maintenance items from normalised alerts JSON."""
    alerts = json.loads(alerts_json)
    anomalies = detect_maintenance_anomalies(alerts)
    return json.dumps([a.model_dump(mode="json") for a in anomalies], indent=2)


@tool
def run_full_anomaly_scan(
    bunker_logs_json: str,
    port_calls_json: str,
    maintenance_alerts_json: str,
) -> str:
    """Run complete anomaly detection across fuel, schedule, and maintenance data."""
    bunker = json.loads(bunker_logs_json)
    ports = json.loads(port_calls_json)
    maintenance = json.loads(maintenance_alerts_json)
    anomalies = detect_all_anomalies(bunker, ports, maintenance)
    summary = {
        "total_anomalies": len(anomalies),
        "by_type": {
            t.value: sum(1 for a in anomalies if a.anomaly_type == t)
            for t in AnomalyType
        },
        "by_severity": {
            s.value: sum(1 for a in anomalies if a.severity == s)
            for s in Severity
        },
        "anomalies": [a.model_dump(mode="json") for a in anomalies],
        "scanned_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(summary, indent=2)
