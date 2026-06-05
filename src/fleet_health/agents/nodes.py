"""LangGraph agent nodes with Claude tool-calling."""

import json
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from fleet_health.agents.state import FleetHealthState
from fleet_health.config import settings
from fleet_health.memory.sqlite_store import memory_store
from fleet_health.schemas.models import (
    Anomaly,
    EscalationItem,
    FleetHealthReport,
    Severity,
    VesselPerformanceSummary,
)
from fleet_health.tools import (
    ANOMALY_TOOLS,
    ESCALATION_TOOLS,
    INGESTION_TOOLS,
    PERFORMANCE_TOOLS,
)
from fleet_health.tools.anomaly_detector import detect_all_anomalies
from fleet_health.tools.parsers import (
    normalize_bunker_logs,
    normalize_maintenance_alerts,
    normalize_port_calls,
    normalize_voyage_reports,
)


def _get_llm() -> ChatAnthropic:
    return ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key or None,
        temperature=0.2,
        max_tokens=4096,
    )


def _run_agent_with_tools(
    agent_name: str,
    system_prompt: str,
    user_message: str,
    tools: list,
    state: FleetHealthState,
) -> str:
    """Execute a ReAct agent and persist output to memory."""
    if not settings.anthropic_api_key:
        output = (
            f"[{agent_name} — deterministic mode, no ANTHROPIC_API_KEY]\n"
            f"Processed fleet '{state['fleet_name']}' for period '{state['report_period']}'. "
            f"Tools available: {[t.name for t in tools]}."
        )
        memory_store.set_agent_memory(
            state["thread_id"], agent_name, "last_output", output
        )
        return output

    llm = _get_llm()
    agent = create_react_agent(llm, tools)

    result = agent.invoke(
        {
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]
        }
    )

    final_message = result["messages"][-1]
    output = (
        final_message.content
        if isinstance(final_message, AIMessage)
        else str(final_message)
    )

    memory_store.set_agent_memory(state["thread_id"], agent_name, "last_output", output)
    return output


def _vessel_ids_from_state(state: FleetHealthState) -> list[str]:
    ids: set[str] = set()
    for key in (
        "voyage_reports_raw",
        "port_calls_raw",
        "bunker_logs_raw",
        "maintenance_alerts_raw",
    ):
        for item in state.get(key, []):
            if vid := item.get("vessel_id"):
                ids.add(vid)
    return sorted(ids)


# ---------------------------------------------------------------------------
# Agent 1: Data Ingestion & Normalisation
# ---------------------------------------------------------------------------

INGESTION_SYSTEM = """You are the Fleet Data Ingestion Agent for a ship management company.
Your role is to parse and normalise maritime operational data:
- Daily noon voyage reports
- Port call schedules
- Bunker consumption logs
- Maintenance alerts

Use your tools to parse each data type. Cross-reference vessel IDs across datasets.
Save normalised snapshots to memory for each vessel.
Provide a concise summary of data quality and any parsing issues found."""


def ingestion_agent(state: FleetHealthState) -> dict[str, Any]:
    voyages = normalize_voyage_reports(state["voyage_reports_raw"])
    ports = normalize_port_calls(state["port_calls_raw"])
    bunkers = normalize_bunker_logs(state["bunker_logs_raw"])
    maintenance = normalize_maintenance_alerts(state["maintenance_alerts_raw"])

    voyage_dicts = [v.model_dump(mode="json") for v in voyages]
    port_dicts = [p.model_dump(mode="json") for p in ports]

    for vessel_id in _vessel_ids_from_state(state):
        vessel_data = {
            "voyages": [v for v in voyage_dicts if v["vessel_id"] == vessel_id],
            "port_calls": [p for p in port_dicts if p["vessel_id"] == vessel_id],
            "bunker_logs": [b for b in bunkers if b["vessel_id"] == vessel_id],
            "maintenance": [m for m in maintenance if m["vessel_id"] == vessel_id],
        }
        memory_store.save_vessel_snapshot(vessel_id, "normalized", vessel_data)

    user_msg = f"""Normalise fleet data for {state['fleet_name']} ({state['report_period']}).

Voyage reports ({len(state['voyage_reports_raw'])} records):
{json.dumps(state['voyage_reports_raw'], indent=2)}

Port calls ({len(state['port_calls_raw'])} records):
{json.dumps(state['port_calls_raw'], indent=2)}

Bunker logs ({len(state['bunker_logs_raw'])} records):
{json.dumps(state['bunker_logs_raw'], indent=2)}

Maintenance alerts ({len(state['maintenance_alerts_raw'])} records):
{json.dumps(state['maintenance_alerts_raw'], indent=2)}

Vessels in scope: {', '.join(_vessel_ids_from_state(state))}
Summarise data quality and coverage after normalisation."""

    summary = _run_agent_with_tools(
        "ingestion_agent",
        INGESTION_SYSTEM,
        user_msg,
        INGESTION_TOOLS,
        state,
    )

    return {
        "normalized_voyages": voyage_dicts,
        "normalized_port_calls": port_dicts,
        "normalized_bunker_logs": bunkers,
        "normalized_maintenance": maintenance,
        "ingestion_summary": summary,
        "agent_outputs": {"ingestion_agent": summary},
        "messages": [AIMessage(content=f"[Ingestion Agent]\n{summary}")],
    }


# ---------------------------------------------------------------------------
# Agent 2: Anomaly Detection
# ---------------------------------------------------------------------------

ANOMALY_SYSTEM = """You are the Fleet Anomaly Detection Agent.
Analyse normalised maritime data to detect:
1. Fuel overconsumption (bunker variance above threshold)
2. Port schedule slippage (late arrivals/departures)
3. Overdue maintenance items

Use your anomaly detection tools. Prioritise by severity.
Reference vessel history from memory when available.
Produce a structured anomaly report with counts by type and severity."""


def anomaly_detection_agent(state: FleetHealthState) -> dict[str, Any]:
    anomalies = detect_all_anomalies(
        state["normalized_bunker_logs"],
        state["normalized_port_calls"],
        state["normalized_maintenance"],
    )
    anomaly_dicts = [a.model_dump(mode="json") for a in anomalies]

    user_msg = f"""Run anomaly detection for {state['fleet_name']}.

Normalised bunker logs:
{json.dumps(state['normalized_bunker_logs'], indent=2)}

Normalised port calls:
{json.dumps(state['normalized_port_calls'], indent=2)}

Normalised maintenance alerts:
{json.dumps(state['normalized_maintenance'], indent=2)}

Pre-computed anomalies ({len(anomalies)} found):
{json.dumps(anomaly_dicts, indent=2)}

Analyse patterns and highlight the most critical issues."""

    summary = _run_agent_with_tools(
        "anomaly_agent",
        ANOMALY_SYSTEM,
        user_msg,
        ANOMALY_TOOLS,
        state,
    )

    return {
        "anomalies": anomaly_dicts,
        "anomaly_summary": summary,
        "agent_outputs": {**state.get("agent_outputs", {}), "anomaly_agent": summary},
        "messages": [AIMessage(content=f"[Anomaly Agent]\n{summary}")],
    }


# ---------------------------------------------------------------------------
# Agent 3: Vessel Performance Summary
# ---------------------------------------------------------------------------

PERFORMANCE_SYSTEM = """You are the Vessel Performance Analyst Agent.
Draft individual vessel performance summaries for the Fleet Superintendent.

For each vessel assess:
- Overall operational status (Green/Amber/Red)
- Fuel efficiency vs plan
- Schedule compliance
- Maintenance posture

Use historical context from memory. Write in professional maritime operations language.
Be specific with numbers and actionable observations."""


def _build_vessel_summaries(
    state: FleetHealthState, narrative: str
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    vessel_ids = _vessel_ids_from_state(state)

    for vid in vessel_ids:
        vessel_anomalies = [a for a in state["anomalies"] if a["vessel_id"] == vid]
        vessel_bunker = [
            b for b in state["normalized_bunker_logs"] if b["vessel_id"] == vid
        ]
        vessel_ports = [
            p for p in state["normalized_port_calls"] if p["vessel_id"] == vid
        ]
        vessel_maint = [
            m for m in state["normalized_maintenance"] if m["vessel_id"] == vid
        ]

        critical_count = sum(
            1 for a in vessel_anomalies if a["severity"] in ("high", "critical")
        )
        overdue_count = sum(1 for m in vessel_maint if m.get("is_overdue"))

        if critical_count >= 2:
            status = "Red"
        elif critical_count >= 1 or overdue_count >= 1:
            status = "Amber"
        else:
            status = "Green"

        avg_variance = (
            sum(b.get("variance_pct", 0) for b in vessel_bunker) / len(vessel_bunker)
            if vessel_bunker
            else 0
        )
        fuel_perf = (
            f"Over plan by {avg_variance:.1f}%"
            if avg_variance > 5
            else "Within tolerance"
            if avg_variance >= -5
            else f"Under plan by {abs(avg_variance):.1f}%"
        )

        slippages = [
            p.get("arrival_slippage_hours")
            for p in vessel_ports
            if p.get("arrival_slippage_hours")
        ]
        schedule = (
            f"Delayed: max {max(slippages):.1f}h slippage"
            if slippages
            else "On schedule"
        )

        maint_status = (
            f"{overdue_count} overdue item(s)"
            if overdue_count
            else "All current"
        )

        observations = [
            a["description"] for a in vessel_anomalies[:3]
        ] or ["No significant anomalies detected"]

        summary = VesselPerformanceSummary(
            vessel_id=vid,
            overall_status=status,
            fuel_performance=fuel_perf,
            schedule_compliance=schedule,
            maintenance_status=maint_status,
            key_observations=observations,
            anomalies_count=len(vessel_anomalies),
        )
        summaries.append(summary.model_dump(mode="json"))

    return summaries


def performance_summary_agent(state: FleetHealthState) -> dict[str, Any]:
    user_msg = f"""Draft vessel performance summaries for {state['fleet_name']}.

Anomalies detected:
{json.dumps(state['anomalies'], indent=2)}

Normalised voyage data:
{json.dumps(state['normalized_voyages'], indent=2)}

Ingestion summary:
{state.get('ingestion_summary', 'N/A')}

Anomaly analysis:
{state.get('anomaly_summary', 'N/A')}

Write a fleet-wide performance narrative and per-vessel assessments."""

    narrative = _run_agent_with_tools(
        "performance_agent",
        PERFORMANCE_SYSTEM,
        user_msg,
        PERFORMANCE_TOOLS,
        state,
    )

    summaries = _build_vessel_summaries(state, narrative)

    return {
        "vessel_summaries": summaries,
        "performance_narrative": narrative,
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "performance_agent": narrative,
        },
        "messages": [AIMessage(content=f"[Performance Agent]\n{narrative}")],
    }


# ---------------------------------------------------------------------------
# Agent 4: Critical Defect Escalation
# ---------------------------------------------------------------------------

ESCALATION_SYSTEM = """You are the Shore-Side Escalation Agent.
Identify critical defects and operational issues requiring immediate
shore-side escalation to the Fleet Technical Superintendent or DPA.

Flag items that are:
- CRITICAL severity maintenance (e.g. main engine defects)
- Regulatory compliance breaches
- Safety-critical equipment failures
- Situations requiring shore technical support or spare parts dispatch

For each escalation provide: vessel, equipment, reason, recommended action."""


def _build_escalations(state: FleetHealthState) -> list[dict[str, Any]]:
    escalations: list[EscalationItem] = []

    for alert in state["normalized_maintenance"]:
        severity = Severity(alert.get("severity", "medium"))
        if severity in (Severity.CRITICAL, Severity.HIGH) and alert.get("is_overdue"):
            action = (
                "Dispatch service engineer and spare parts to next port of call"
                if severity == Severity.CRITICAL
                else "Schedule shore support at next port; monitor condition"
            )
            escalations.append(
                EscalationItem(
                    vessel_id=alert["vessel_id"],
                    equipment=alert["equipment"],
                    severity=severity,
                    reason=alert["description"],
                    recommended_action=action,
                )
            )

    for anomaly in state["anomalies"]:
        if anomaly["severity"] == "critical":
            escalations.append(
                EscalationItem(
                    vessel_id=anomaly["vessel_id"],
                    equipment="Operations",
                    severity=Severity.CRITICAL,
                    reason=anomaly["description"],
                    recommended_action="Immediate superintendent review required",
                )
            )

    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for esc in escalations:
        key = (esc.vessel_id, esc.equipment)
        if key not in seen:
            seen.add(key)
            unique.append(esc.model_dump(mode="json"))
    return unique


def escalation_agent(state: FleetHealthState) -> dict[str, Any]:
    pre_built = _build_escalations(state)

    user_msg = f"""Review fleet data and flag critical defects for shore-side escalation.

Maintenance alerts:
{json.dumps(state['normalized_maintenance'], indent=2)}

All anomalies:
{json.dumps(state['anomalies'], indent=2)}

Pre-identified escalations ({len(pre_built)}):
{json.dumps(pre_built, indent=2)}

Vessel performance context:
{state.get('performance_narrative', 'N/A')}

Confirm escalations and add any additional critical items."""

    narrative = _run_agent_with_tools(
        "escalation_agent",
        ESCALATION_SYSTEM,
        user_msg,
        ESCALATION_TOOLS,
        state,
    )

    return {
        "escalations": pre_built,
        "escalation_narrative": narrative,
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "escalation_agent": narrative,
        },
        "messages": [AIMessage(content=f"[Escalation Agent]\n{narrative}")],
    }


# ---------------------------------------------------------------------------
# Report Compiler (final node)
# ---------------------------------------------------------------------------

def compile_report(state: FleetHealthState) -> dict[str, Any]:
    """Assemble the final Fleet Health & Delivery Report."""
    from datetime import datetime

    critical = sum(1 for a in state["anomalies"] if a["severity"] == "critical")
    high = sum(1 for a in state["anomalies"] if a["severity"] == "high")
    red_vessels = sum(
        1 for v in state["vessel_summaries"] if v["overall_status"] == "Red"
    )

    executive = (
        f"Fleet Health Report for {state['fleet_name']} ({state['report_period']}): "
        f"{len(state['vessel_summaries'])} vessels assessed, "
        f"{len(state['anomalies'])} anomalies detected "
        f"({critical} critical, {high} high). "
        f"{len(state['escalations'])} items require shore-side escalation. "
        f"{red_vessels} vessel(s) in Red status."
    )

    recommendations = []
    if critical > 0:
        recommendations.append(
            "Immediate review of critical defects with Fleet Technical Superintendent"
        )
    if any(a["anomaly_type"] == "fuel_overconsumption" for a in state["anomalies"]):
        recommendations.append(
            "Investigate fuel overconsumption on affected vessels; review weather routing"
        )
    if any(a["anomaly_type"] == "schedule_slippage" for a in state["anomalies"]):
        recommendations.append(
            "Notify charterers of schedule delays; assess knock-on port rotation impact"
        )
    if any(a["anomaly_type"] == "overdue_maintenance" for a in state["anomalies"]):
        recommendations.append(
            "Expedite overdue maintenance; arrange shore support at next port calls"
        )
    if not recommendations:
        recommendations.append("Continue routine monitoring; no immediate action required")

    report = FleetHealthReport(
        fleet_name=state["fleet_name"],
        report_period=state["report_period"],
        generated_at=datetime.utcnow(),
        vessel_summaries=[
            VesselPerformanceSummary(**v) for v in state["vessel_summaries"]
        ],
        anomalies=[Anomaly(**a) for a in state["anomalies"]],
        escalations=[EscalationItem(**e) for e in state["escalations"]],
        executive_summary=executive,
        recommendations=recommendations,
        raw_agent_outputs=state.get("agent_outputs", {}),
    )

    report_dict = report.model_dump(mode="json")
    memory_store.save_report(report_dict)

    return {
        "executive_summary": executive,
        "recommendations": recommendations,
        "final_report": report_dict,
        "messages": [AIMessage(content=f"[Report Compiled]\n{executive}")],
    }
