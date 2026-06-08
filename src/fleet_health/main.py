"""FastAPI application for Fleet Health & Delivery Report generation."""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fleet_health import __version__
from fleet_health.agents.graph import run_pipeline
from fleet_health.config import settings
from fleet_health.memory.sqlite_store import memory_store
from fleet_health.schemas.models import FleetHealthReport, FleetReportRequest

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"

app = FastAPI(
    title="Fleet Health & Delivery Report API",
    description=(
        "Multi-agent pipeline that ingests voyage reports, port schedules, "
        "bunker logs, and maintenance alerts to generate fleet health reports."
    ),
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ReportResponse(BaseModel):
    thread_id: str
    executive_summary: str
    recommendations: list[str]
    anomalies_count: int
    escalations_count: int
    report: FleetHealthReport | dict[str, Any]
    agent_outputs: dict[str, str] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    version: str
    anthropic_configured: bool
    sqlite_path: str


@app.get("/health", response_model=HealthResponse, tags=["health"])
@app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        version=__version__,
        anthropic_configured=bool(settings.anthropic_api_key),
        sqlite_path=str(settings.db_path),
    )


@app.get("/", tags=["dashboard"], include_in_schema=False)
async def serve_dashboard() -> FileResponse:
    """Fleet Health operations dashboard."""
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(index)


@app.get("/index.html", tags=["dashboard"], include_in_schema=False)
async def serve_dashboard_alias() -> FileResponse:
    return await serve_dashboard()


@app.get("/api", tags=["health"])
async def api_root() -> dict[str, str]:
    return {
        "service": "Fleet Health & Delivery Report API",
        "dashboard": "/",
        "docs": "/docs",
        "health": "/health",
    }


@app.post("/api/v1/reports/generate", response_model=ReportResponse)
async def generate_report(request: FleetReportRequest) -> ReportResponse:
    """Generate a Fleet Health & Delivery Report from operational data."""
    if not request.voyage_reports and not request.port_calls:
        raise HTTPException(
            status_code=400,
            detail="At least voyage reports or port calls must be provided",
        )

    try:
        result = run_pipeline(
            voyage_reports=[v.model_dump() for v in request.voyage_reports],
            port_calls=[p.model_dump() for p in request.port_calls],
            bunker_logs=[b.model_dump() for b in request.bunker_logs],
            maintenance_alerts=[m.model_dump() for m in request.maintenance_alerts],
            fleet_name=request.fleet_name,
            report_period=request.report_period,
        )
    except Exception as exc:
        logger.exception("Pipeline execution failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ReportResponse(**result)


@app.post("/api/v1/reports/generate/sample", response_model=ReportResponse)
async def generate_sample_report() -> ReportResponse:
    """Generate a report using bundled sample fleet data."""
    sample_files = {
        "voyage_reports": "voyage_reports.json",
        "port_calls": "port_calls.json",
        "bunker_logs": "bunker_logs.json",
        "maintenance_alerts": "maintenance_alerts.json",
    }

    data: dict[str, list] = {}
    for key, filename in sample_files.items():
        path = SAMPLES_DIR / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Sample file missing: {filename}")
        data[key] = json.loads(path.read_text(encoding="utf-8"))

    request = FleetReportRequest(
        voyage_reports=data["voyage_reports"],
        port_calls=data["port_calls"],
        bunker_logs=data["bunker_logs"],
        maintenance_alerts=data["maintenance_alerts"],
        fleet_name="Fleet Alpha",
        report_period="2026-06-04 Noon Report Cycle",
    )
    return await generate_report(request)


@app.get("/api/v1/reports/history")
async def get_report_history(limit: int = 10) -> dict[str, Any]:
    """Retrieve recent fleet health reports from SQLite memory."""
    reports = memory_store.get_recent_reports(limit=limit)
    return {"count": len(reports), "reports": reports}


@app.get("/api/v1/vessels/{vessel_id}/history")
async def get_vessel_history(
    vessel_id: str, snapshot_type: str | None = None, limit: int = 10
) -> dict[str, Any]:
    """Retrieve historical snapshots for a specific vessel."""
    history = memory_store.get_vessel_history(vessel_id, snapshot_type, limit)
    return {"vessel_id": vessel_id, "count": len(history), "snapshots": history}


@app.get("/api/v1/agents")
async def list_agents() -> dict[str, Any]:
    """List the agents in the multi-agent pipeline."""
    return {
        "pipeline": "sequential",
        "agents": [
            {
                "name": "ingestion_agent",
                "role": "Parse and normalise voyage, port, bunker, and maintenance data",
                "tools": [
                    "parse_voyage_data",
                    "parse_port_schedule",
                    "parse_bunker_logs",
                    "parse_maintenance_alerts",
                    "recall_vessel_history",
                    "save_vessel_snapshot",
                ],
            },
            {
                "name": "anomaly_agent",
                "role": "Detect fuel overconsumption, schedule slippage, overdue maintenance",
                "tools": [
                    "detect_fuel_overconsumption",
                    "detect_schedule_slippage",
                    "detect_overdue_maintenance",
                    "run_full_anomaly_scan",
                ],
            },
            {
                "name": "performance_agent",
                "role": "Draft vessel performance summaries for fleet superintendent",
                "tools": ["recall_vessel_history", "recall_recent_reports", "save_vessel_snapshot"],
            },
            {
                "name": "escalation_agent",
                "role": "Flag critical defects requiring shore-side escalation",
                "tools": ["recall_vessel_history", "recall_recent_reports"],
            },
        ],
        "memory": "SQLite (vessel snapshots, report history, agent memory, LangGraph checkpoints)",
        "llm": settings.anthropic_model,
    }
