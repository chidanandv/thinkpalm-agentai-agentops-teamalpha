# Fleet Health & Delivery Report — Architecture Write-Up

**Project:** thinkpalm-agentai-agentops-teamalpha  
**Version:** 1.0.0  
**Date:** June 2026

---

## Problem Statement

Ship management operations teams receive daily operational data from multiple sources — noon voyage reports, port call schedules, bunker consumption logs, and planned maintenance system (PMS) alerts. Manually synthesising this into a fleet-wide health and delivery report is time-consuming and error-prone, especially when anomalies require immediate superintendent attention.

## Solution Overview

This system implements a **sequential multi-agent pipeline** powered by LangGraph and Claude API. Four specialised agents process maritime data end-to-end and produce a structured **Fleet Health & Delivery Report** via a FastAPI REST interface.

## Architecture

![Architecture Diagram](architecture.png)

### Data Inputs

| Source | Content |
|--------|---------|
| Daily Noon Reports | Position, speed, distance, fuel consumed/remaining, weather |
| Port Call Schedules | Planned vs actual arrival/departure times |
| Bunker Consumption Logs | Actual vs expected fuel burn by voyage phase |
| Maintenance Alerts | PMS due dates, condition monitoring, regulatory items |

### Agent Pipeline

1. **Ingestion Agent** — Parses raw JSON/CSV inputs, normalises timestamps and units, computes derived metrics (fuel efficiency, schedule slippage), and persists vessel snapshots to SQLite memory.

2. **Anomaly Detection Agent** — Applies threshold-based rules and tool-calling to flag fuel overconsumption (>10% variance), port schedule slippage (>6 hours), and overdue maintenance items.

3. **Performance Summary Agent** — Drafts per-vessel Green/Amber/Red status summaries with fuel, schedule, and maintenance posture for the Fleet Superintendent.

4. **Escalation Agent** — Identifies critical defects (e.g. main engine liner wear, overdue BWTS compliance) requiring shore-side technical support or spare parts dispatch.

### Memory & Persistence

SQLite stores four data categories: vessel snapshots, report history, per-thread agent memory, and LangGraph graph checkpoints for pipeline resumability.

### Technology Stack

- **FastAPI** — REST API with OpenAPI documentation
- **LangGraph** — Multi-agent orchestration with tool-calling
- **Claude API (Anthropic)** — LLM reasoning for agent narratives
- **SQLite** — Persistent memory and checkpointing
- **Pydantic** — Request/response validation

## Key Design Decisions

- **Sequential pipeline** over supervisor pattern: maritime reporting has a natural data flow (ingest → analyse → summarise → escalate) that maps cleanly to ordered agent nodes.
- **Hybrid intelligence**: Rule-based anomaly detection ensures deterministic, auditable thresholds; Claude adds narrative summaries and contextual reasoning.
- **Deterministic fallback**: Pipeline runs without an API key for CI/testing; LLM calls are skipped but structured reports are still generated.

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Service health check |
| `/api/v1/reports/generate` | POST | Generate report from custom payload |
| `/api/v1/reports/generate/sample` | POST | Generate from bundled sample data |
| `/api/v1/reports/history` | GET | Recent reports from SQLite |
| `/api/v1/agents` | GET | Agent catalogue |

---

*ThinkPalm AgentAI — AgentOps Team Alpha*
