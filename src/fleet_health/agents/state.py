"""Shared state for the fleet health LangGraph pipeline."""

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage


class FleetHealthState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    thread_id: str
    fleet_name: str
    report_period: str

    # Raw inputs
    voyage_reports_raw: list[dict[str, Any]]
    port_calls_raw: list[dict[str, Any]]
    bunker_logs_raw: list[dict[str, Any]]
    maintenance_alerts_raw: list[dict[str, Any]]

    # Normalised data (Agent 1 output)
    normalized_voyages: list[dict[str, Any]]
    normalized_port_calls: list[dict[str, Any]]
    normalized_bunker_logs: list[dict[str, Any]]
    normalized_maintenance: list[dict[str, Any]]
    ingestion_summary: str

    # Anomalies (Agent 2 output)
    anomalies: list[dict[str, Any]]
    anomaly_summary: str

    # Performance summaries (Agent 3 output)
    vessel_summaries: list[dict[str, Any]]
    performance_narrative: str

    # Escalations (Agent 4 output)
    escalations: list[dict[str, Any]]
    escalation_narrative: str

    # Final report
    executive_summary: str
    recommendations: list[str]
    final_report: dict[str, Any]

    # Agent outputs for traceability
    agent_outputs: dict[str, str]
