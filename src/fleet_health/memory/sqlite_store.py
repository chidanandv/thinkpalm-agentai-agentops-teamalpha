"""SQLite-backed memory for fleet health pipeline."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fleet_health.config import settings


class FleetMemoryStore:
    """Persistent memory for vessel history, past reports, and agent context."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or settings.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS vessel_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vessel_id TEXT NOT NULL,
                    snapshot_type TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS report_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fleet_name TEXT NOT NULL,
                    report_period TEXT,
                    report_json TEXT NOT NULL,
                    anomaly_count INTEGER DEFAULT 0,
                    escalation_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    memory_value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(thread_id, agent_name, memory_key)
                );

                CREATE INDEX IF NOT EXISTS idx_vessel_snapshots_vessel
                    ON vessel_snapshots(vessel_id);
                CREATE INDEX IF NOT EXISTS idx_agent_memory_thread
                    ON agent_memory(thread_id);
                """
            )

    def save_vessel_snapshot(
        self, vessel_id: str, snapshot_type: str, data: dict[str, Any]
    ) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO vessel_snapshots (vessel_id, snapshot_type, data_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (vessel_id, snapshot_type, json.dumps(data), datetime.utcnow().isoformat()),
            )

    def get_vessel_history(
        self, vessel_id: str, snapshot_type: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM vessel_snapshots WHERE vessel_id = ?"
        params: list[Any] = [vessel_id]
        if snapshot_type:
            query += " AND snapshot_type = ?"
            params.append(snapshot_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "vessel_id": row["vessel_id"],
                "snapshot_type": row["snapshot_type"],
                "data": json.loads(row["data_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def save_report(self, report: dict[str, Any]) -> int:
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO report_history
                    (fleet_name, report_period, report_json, anomaly_count,
                     escalation_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report.get("fleet_name", "Unknown"),
                    report.get("report_period", ""),
                    json.dumps(report),
                    len(report.get("anomalies", [])),
                    len(report.get("escalations", [])),
                    datetime.utcnow().isoformat(),
                ),
            )
            return cursor.lastrowid or 0

    def get_recent_reports(self, limit: int = 5) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM report_history
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "fleet_name": row["fleet_name"],
                "report_period": row["report_period"],
                "report": json.loads(row["report_json"]),
                "anomaly_count": row["anomaly_count"],
                "escalation_count": row["escalation_count"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def set_agent_memory(
        self, thread_id: str, agent_name: str, key: str, value: Any
    ) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_memory (thread_id, agent_name, memory_key, memory_value, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(thread_id, agent_name, memory_key)
                DO UPDATE SET memory_value = excluded.memory_value,
                              created_at = excluded.created_at
                """,
                (
                    thread_id,
                    agent_name,
                    key,
                    json.dumps(value),
                    datetime.utcnow().isoformat(),
                ),
            )

    def get_agent_memory(
        self, thread_id: str, agent_name: str | None = None
    ) -> dict[str, Any]:
        query = "SELECT agent_name, memory_key, memory_value FROM agent_memory WHERE thread_id = ?"
        params: list[Any] = [thread_id]
        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()

        result: dict[str, Any] = {}
        for row in rows:
            agent = row["agent_name"]
            if agent not in result:
                result[agent] = {}
            result[agent][row["memory_key"]] = json.loads(row["memory_value"])
        return result


memory_store = FleetMemoryStore()
