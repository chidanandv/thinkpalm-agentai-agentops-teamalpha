import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = PROJECT_ROOT / "src" / "data" / "samples"


@pytest.fixture
def sample_voyage_reports() -> list[dict]:
    return json.loads((SAMPLES_DIR / "voyage_reports.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_port_calls() -> list[dict]:
    return json.loads((SAMPLES_DIR / "port_calls.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_bunker_logs() -> list[dict]:
    return json.loads((SAMPLES_DIR / "bunker_logs.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_maintenance_alerts() -> list[dict]:
    return json.loads((SAMPLES_DIR / "maintenance_alerts.json").read_text(encoding="utf-8"))
