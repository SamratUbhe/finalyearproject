"""Unit tests for FastAPI server health check endpoints."""

import tests  # noqa: F401 - ensure sandbox-safe TestClient patch is initialized
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_health_root():
    """Verify GET /health returns 200 OK and valid status metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert "Automated Code Vulnerability Reviewer" in data["app_name"]


def test_health_api_v1():
    """Verify GET /api/v1/health returns 200 OK and valid status metadata."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert "Automated Code Vulnerability Reviewer" in data["app_name"]

