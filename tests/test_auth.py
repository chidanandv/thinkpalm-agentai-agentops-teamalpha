"""Tests for dashboard authentication."""

import pytest
from fastapi.testclient import TestClient

from fleet_health.config import Settings
from fleet_health.main import app

auth_client = TestClient(app)


@pytest.fixture(autouse=True)
def _enable_auth(monkeypatch):
    monkeypatch.setattr(
        "fleet_health.main.settings",
        Settings(
            auth_enabled=True,
            auth_username="admin",
            auth_password="fleetops",
            session_secret="test-secret-key",
        ),
    )


def test_protected_dashboard_redirects_to_login():
    response = auth_client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_login_success_sets_cookie():
    response = auth_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "fleetops"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "admin"
    assert "fleet_session" in response.cookies


def test_login_invalid_credentials():
    response = auth_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert response.status_code == 401


def test_authenticated_access_dashboard():
    login = auth_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "fleetops"},
    )
    assert login.status_code == 200
    response = auth_client.get("/")
    assert response.status_code == 200
    assert "Fleet Health" in response.text
