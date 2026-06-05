from fleet_health.tools.parsers import (
    normalize_bunker_logs,
    normalize_maintenance_alerts,
    normalize_port_calls,
    normalize_voyage_reports,
)


def test_normalize_voyage_reports(sample_voyage_reports):
    result = normalize_voyage_reports(sample_voyage_reports)
    assert len(result) == 3
    assert result[0].vessel_id == "MV OCEAN STAR"
    assert result[0].fuel_efficiency_mt_per_nm > 0


def test_normalize_port_calls_detects_slippage(sample_port_calls):
    result = normalize_port_calls(sample_port_calls)
    pacific = next(r for r in result if r.vessel_id == "MV PACIFIC TRADER")
    assert pacific.arrival_slippage_hours == 12.0


def test_normalize_bunker_logs_variance(sample_bunker_logs):
    result = normalize_bunker_logs(sample_bunker_logs)
    pacific = next(r for r in result if r["vessel_id"] == "MV PACIFIC TRADER")
    assert pacific["variance_pct"] > 10


def test_normalize_maintenance_overdue(sample_maintenance_alerts):
    result = normalize_maintenance_alerts(sample_maintenance_alerts)
    overdue = [r for r in result if r["is_overdue"]]
    assert len(overdue) >= 2
