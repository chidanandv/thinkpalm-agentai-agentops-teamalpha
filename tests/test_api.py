from fastapi.testclient import TestClient

from fleet_health.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["version"] == "1.0.0"


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "docs" in response.json()


def test_list_agents():
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    agents = response.json()["agents"]
    assert len(agents) == 4
    names = {a["name"] for a in agents}
    assert "ingestion_agent" in names
    assert "escalation_agent" in names


def test_generate_sample_report():
    response = client.post("/api/v1/reports/generate/sample")
    assert response.status_code == 200
    body = response.json()
    assert body["anomalies_count"] >= 1
    assert body["executive_summary"]
    assert body["report"]["fleet_name"] == "Fleet Alpha"
