from fleet_health.tools.anomaly_detector import (
    detect_fuel_overconsumption,
    detect_overdue_maintenance,
    detect_schedule_slippage,
    run_full_anomaly_scan,
)
from fleet_health.tools.memory_tools import (
    recall_recent_reports,
    recall_vessel_history,
    save_vessel_snapshot,
)
from fleet_health.tools.parsers import (
    parse_bunker_logs,
    parse_maintenance_alerts,
    parse_port_schedule,
    parse_voyage_data,
)

INGESTION_TOOLS = [
    parse_voyage_data,
    parse_port_schedule,
    parse_bunker_logs,
    parse_maintenance_alerts,
    recall_vessel_history,
    save_vessel_snapshot,
]

ANOMALY_TOOLS = [
    detect_fuel_overconsumption,
    detect_schedule_slippage,
    detect_overdue_maintenance,
    run_full_anomaly_scan,
    recall_vessel_history,
]

PERFORMANCE_TOOLS = [
    recall_vessel_history,
    recall_recent_reports,
    save_vessel_snapshot,
]

ESCALATION_TOOLS = [
    recall_vessel_history,
    recall_recent_reports,
]
