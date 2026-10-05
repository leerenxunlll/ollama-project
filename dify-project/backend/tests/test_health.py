"""Tests for the Phase 0 health endpoint."""


def test_health_returns_ok(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "AI Murder Mystery"}
