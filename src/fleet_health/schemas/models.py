from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyType(str, Enum):
    FUEL_OVERCONSUMPTION = "fuel_overconsumption"
    SCHEDULE_SLIPPAGE = "schedule_slippage"
    OVERDUE_MAINTENANCE = "overdue_maintenance"


class VoyageReportInput(BaseModel):
    vessel_id: str
    report_date: str
    position_lat: float
    position_lon: float
    speed_knots: float
    distance_nm: float
    fuel_consumed_mt: float
    fuel_remaining_mt: float
    weather: str = ""
    remarks: str = ""


class PortCallInput(BaseModel):
    vessel_id: str
    port_name: str
    planned_arrival: str
    planned_departure: str
    actual_arrival: str | None = None
    actual_departure: str | None = None
    cargo_operation: str = ""


class BunkerLogInput(BaseModel):
    vessel_id: str
    log_date: str
    fuel_type: str
    consumed_mt: float
    expected_mt: float
    voyage_phase: str = "at_sea"


class MaintenanceAlertInput(BaseModel):
    vessel_id: str
    equipment: str
    alert_type: str
    due_date: str
    last_service_date: str | None = None
    severity: Severity = Severity.MEDIUM
    description: str = ""


class FleetReportRequest(BaseModel):
    voyage_reports: list[VoyageReportInput] = Field(default_factory=list)
    port_calls: list[PortCallInput] = Field(default_factory=list)
    bunker_logs: list[BunkerLogInput] = Field(default_factory=list)
    maintenance_alerts: list[MaintenanceAlertInput] = Field(default_factory=list)
    fleet_name: str = "Fleet Alpha"
    report_period: str = ""


class NormalizedVoyage(BaseModel):
    vessel_id: str
    report_date: datetime
    position: dict[str, float]
    speed_knots: float
    distance_nm: float
    fuel_consumed_mt: float
    fuel_remaining_mt: float
    fuel_efficiency_mt_per_nm: float
    weather: str
    remarks: str


class NormalizedPortCall(BaseModel):
    vessel_id: str
    port_name: str
    planned_arrival: datetime
    planned_departure: datetime
    actual_arrival: datetime | None
    actual_departure: datetime | None
    arrival_slippage_hours: float | None
    departure_slippage_hours: float | None
    cargo_operation: str


class Anomaly(BaseModel):
    vessel_id: str
    anomaly_type: AnomalyType
    severity: Severity
    description: str
    metric_value: float | None = None
    threshold_value: float | None = None
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class EscalationItem(BaseModel):
    vessel_id: str
    equipment: str
    severity: Severity
    reason: str
    recommended_action: str
    shore_contact: str = "Fleet Technical Superintendent"


class VesselPerformanceSummary(BaseModel):
    vessel_id: str
    overall_status: str
    fuel_performance: str
    schedule_compliance: str
    maintenance_status: str
    key_observations: list[str]
    anomalies_count: int


class FleetHealthReport(BaseModel):
    fleet_name: str
    report_period: str
    generated_at: datetime
    vessel_summaries: list[VesselPerformanceSummary]
    anomalies: list[Anomaly]
    escalations: list[EscalationItem]
    executive_summary: str
    recommendations: list[str]
    raw_agent_outputs: dict[str, Any] = Field(default_factory=dict)
