"""Tools for parsing and normalising maritime operational data."""

from datetime import UTC, datetime
from typing import Any

from langchain_core.tools import tool

from fleet_health.schemas.models import (
    BunkerLogInput,
    MaintenanceAlertInput,
    NormalizedPortCall,
    NormalizedVoyage,
    PortCallInput,
    VoyageReportInput,
)


def _parse_datetime(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Unable to parse datetime: {value}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def normalize_voyage_reports(
    reports: list[dict[str, Any]],
) -> list[NormalizedVoyage]:
    normalized: list[NormalizedVoyage] = []
    for raw in reports:
        report = VoyageReportInput(**raw)
        efficiency = (
            report.fuel_consumed_mt / report.distance_nm
            if report.distance_nm > 0
            else 0.0
        )
        normalized.append(
            NormalizedVoyage(
                vessel_id=report.vessel_id,
                report_date=_parse_datetime(report.report_date),
                position={"lat": report.position_lat, "lon": report.position_lon},
                speed_knots=report.speed_knots,
                distance_nm=report.distance_nm,
                fuel_consumed_mt=report.fuel_consumed_mt,
                fuel_remaining_mt=report.fuel_remaining_mt,
                fuel_efficiency_mt_per_nm=round(efficiency, 4),
                weather=report.weather,
                remarks=report.remarks,
            )
        )
    return normalized


def normalize_port_calls(calls: list[dict[str, Any]]) -> list[NormalizedPortCall]:
    normalized: list[NormalizedPortCall] = []
    for raw in calls:
        call = PortCallInput(**raw)
        planned_arr = _parse_datetime(call.planned_arrival)
        planned_dep = _parse_datetime(call.planned_departure)
        actual_arr = (
            _parse_datetime(call.actual_arrival) if call.actual_arrival else None
        )
        actual_dep = (
            _parse_datetime(call.actual_departure) if call.actual_departure else None
        )

        arr_slip = None
        dep_slip = None
        if actual_arr:
            arr_slip = round(
                (actual_arr - planned_arr).total_seconds() / 3600, 2
            )
        if actual_dep:
            dep_slip = round(
                (actual_dep - planned_dep).total_seconds() / 3600, 2
            )

        normalized.append(
            NormalizedPortCall(
                vessel_id=call.vessel_id,
                port_name=call.port_name,
                planned_arrival=planned_arr,
                planned_departure=planned_dep,
                actual_arrival=actual_arr,
                actual_departure=actual_dep,
                arrival_slippage_hours=arr_slip,
                departure_slippage_hours=dep_slip,
                cargo_operation=call.cargo_operation,
            )
        )
    return normalized


def normalize_bunker_logs(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for raw in logs:
        log = BunkerLogInput(**raw)
        variance_pct = (
            ((log.consumed_mt - log.expected_mt) / log.expected_mt) * 100
            if log.expected_mt > 0
            else 0.0
        )
        normalized.append(
            {
                "vessel_id": log.vessel_id,
                "log_date": _parse_datetime(log.log_date).isoformat(),
                "fuel_type": log.fuel_type,
                "consumed_mt": log.consumed_mt,
                "expected_mt": log.expected_mt,
                "variance_pct": round(variance_pct, 2),
                "voyage_phase": log.voyage_phase,
            }
        )
    return normalized


def normalize_maintenance_alerts(
    alerts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized = []
    now = datetime.now(UTC)
    for raw in alerts:
        alert = MaintenanceAlertInput(**raw)
        due = _parse_datetime(alert.due_date)
        days_overdue = max(0, (now - due).days)
        normalized.append(
            {
                "vessel_id": alert.vessel_id,
                "equipment": alert.equipment,
                "alert_type": alert.alert_type,
                "due_date": due.isoformat(),
                "last_service_date": alert.last_service_date,
                "severity": alert.severity.value,
                "description": alert.description,
                "days_overdue": days_overdue,
                "is_overdue": days_overdue > 0,
            }
        )
    return normalized


@tool
def parse_voyage_data(reports_json: str) -> str:
    """Parse and normalise daily noon voyage reports from JSON string."""
    import json

    reports = json.loads(reports_json)
    normalized = normalize_voyage_reports(reports)
    return json.dumps([v.model_dump(mode="json") for v in normalized], indent=2)


@tool
def parse_port_schedule(port_calls_json: str) -> str:
    """Parse and normalise port call schedules from JSON string."""
    import json

    calls = json.loads(port_calls_json)
    normalized = normalize_port_calls(calls)
    return json.dumps([c.model_dump(mode="json") for c in normalized], indent=2)


@tool
def parse_bunker_logs(bunker_logs_json: str) -> str:
    """Parse and normalise bunker consumption logs from JSON string."""
    import json

    logs = json.loads(bunker_logs_json)
    return json.dumps(normalize_bunker_logs(logs), indent=2)


@tool
def parse_maintenance_alerts(alerts_json: str) -> str:
    """Parse and normalise maintenance alerts from JSON string."""
    import json

    alerts = json.loads(alerts_json)
    return json.dumps(normalize_maintenance_alerts(alerts), indent=2)
