"""Run the Fleet Health API: python -m fleet_health (from project root with PYTHONPATH=src)."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "fleet_health.main:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
    )
