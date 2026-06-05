"""Memory tools for agents to read/write fleet historical context."""

import json

from langchain_core.tools import tool

from fleet_health.memory.sqlite_store import memory_store


@tool
def recall_vessel_history(vessel_id: str, snapshot_type: str = "") -> str:
    """Recall historical snapshots for a vessel from SQLite memory."""
    history = memory_store.get_vessel_history(
        vessel_id, snapshot_type or None, limit=5
    )
    return json.dumps(history, indent=2)


@tool
def save_vessel_snapshot(
    vessel_id: str, snapshot_type: str, data_json: str
) -> str:
    """Save a vessel data snapshot to persistent SQLite memory."""
    data = json.loads(data_json)
    memory_store.save_vessel_snapshot(vessel_id, snapshot_type, data)
    return json.dumps(
        {"status": "saved", "vessel_id": vessel_id, "type": snapshot_type}
    )


@tool
def recall_recent_reports(limit: int = 3) -> str:
    """Recall recent fleet health reports from SQLite memory."""
    reports = memory_store.get_recent_reports(limit=limit)
    return json.dumps(reports, indent=2, default=str)
