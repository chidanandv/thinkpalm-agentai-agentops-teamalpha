"""Run the Fleet Health API: python -m fleet_health (from project root with PYTHONPATH=src)."""

from pathlib import Path

import uvicorn

# Only watch Python source — never reload on SQLite writes in data/
SRC_DIR = str(Path(__file__).resolve().parent)

if __name__ == "__main__":
    uvicorn.run(
        "fleet_health.main:app",
        host="127.0.0.1",
        port=8001,
        reload=False,
    )
