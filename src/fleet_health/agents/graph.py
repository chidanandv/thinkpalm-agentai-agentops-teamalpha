"""LangGraph multi-agent pipeline for Fleet Health & Delivery Reports."""

import sqlite3
import uuid
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from fleet_health.agents.nodes import (
    anomaly_detection_agent,
    compile_report,
    escalation_agent,
    ingestion_agent,
    performance_summary_agent,
)
from fleet_health.agents.state import FleetHealthState
from fleet_health.config import settings


def build_fleet_health_graph():
    """Build the 4-agent sequential pipeline with SQLite checkpointing."""
    graph = StateGraph(FleetHealthState)

    graph.add_node("ingestion_agent", ingestion_agent)
    graph.add_node("anomaly_agent", anomaly_detection_agent)
    graph.add_node("performance_agent", performance_summary_agent)
    graph.add_node("escalation_agent", escalation_agent)
    graph.add_node("compile_report", compile_report)

    graph.set_entry_point("ingestion_agent")
    graph.add_edge("ingestion_agent", "anomaly_agent")
    graph.add_edge("anomaly_agent", "performance_agent")
    graph.add_edge("performance_agent", "escalation_agent")
    graph.add_edge("escalation_agent", "compile_report")
    graph.add_edge("compile_report", END)

    conn = sqlite3.connect(
        str(settings.db_path.parent / "langgraph_checkpoints.db"),
        check_same_thread=False,
    )
    checkpointer = SqliteSaver(conn)

    return graph.compile(checkpointer=checkpointer)


def run_pipeline(
    voyage_reports: list[dict[str, Any]],
    port_calls: list[dict[str, Any]],
    bunker_logs: list[dict[str, Any]],
    maintenance_alerts: list[dict[str, Any]],
    fleet_name: str = "Fleet Alpha",
    report_period: str = "",
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Execute the full multi-agent pipeline and return the final report."""
    graph = build_fleet_health_graph()
    tid = thread_id or str(uuid.uuid4())

    initial_state: FleetHealthState = {
        "messages": [],
        "thread_id": tid,
        "fleet_name": fleet_name,
        "report_period": report_period or "Current period",
        "voyage_reports_raw": voyage_reports,
        "port_calls_raw": port_calls,
        "bunker_logs_raw": bunker_logs,
        "maintenance_alerts_raw": maintenance_alerts,
        "normalized_voyages": [],
        "normalized_port_calls": [],
        "normalized_bunker_logs": [],
        "normalized_maintenance": [],
        "ingestion_summary": "",
        "anomalies": [],
        "anomaly_summary": "",
        "vessel_summaries": [],
        "performance_narrative": "",
        "escalations": [],
        "escalation_narrative": "",
        "executive_summary": "",
        "recommendations": [],
        "final_report": {},
        "agent_outputs": {},
    }

    config = {"configurable": {"thread_id": tid}}
    result = graph.invoke(initial_state, config=config)
    return {
        "thread_id": tid,
        "report": result.get("final_report", {}),
        "executive_summary": result.get("executive_summary", ""),
        "recommendations": result.get("recommendations", []),
        "anomalies_count": len(result.get("anomalies", [])),
        "escalations_count": len(result.get("escalations", [])),
        "agent_outputs": result.get("agent_outputs", {}),
    }
