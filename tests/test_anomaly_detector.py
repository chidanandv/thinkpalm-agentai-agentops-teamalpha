from fleet_health.tools.anomaly_detector import detect_all_anomalies
from fleet_health.tools.parsers import (
    normalize_bunker_logs,
    normalize_maintenance_alerts,
    normalize_port_calls,
)


def test_detect_all_anomalies(sample_bunker_logs, sample_port_calls, sample_maintenance_alerts):
    bunker = normalize_bunker_logs(sample_bunker_logs)
    ports = normalize_port_calls(sample_port_calls)
    ports_dicts = [p.model_dump(mode="json") for p in ports]
    maintenance = normalize_maintenance_alerts(sample_maintenance_alerts)

    anomalies = detect_all_anomalies(bunker, ports_dicts, maintenance)
    types = {a.anomaly_type.value for a in anomalies}

    assert "fuel_overconsumption" in types
    assert "schedule_slippage" in types
    assert "overdue_maintenance" in types
    assert len(anomalies) >= 4
