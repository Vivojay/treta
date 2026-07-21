from __future__ import annotations

from fastapi.testclient import TestClient

from treta.api.app import InMemoryRateLimiter, create_app
from treta.application.control_plane import ControlPlaneService


def headers(role: str = "viewer", *, tenant: str = "tenant-synthetic", key: str | None = None):
    result = {
        "X-Treta-Actor": f"test-{role}",
        "X-Treta-Role": role,
        "X-Treta-Tenant-ID": tenant,
        "X-Request-ID": "integration-request",
    }
    if key:
        result["Idempotency-Key"] = key
    return result


def test_health_version_authentication_and_openapi() -> None:
    client = TestClient(create_app(ControlPlaneService()))
    assert client.get("/api/v1/health/live").json() == {"status": "live"}
    assert client.get("/api/v1/health/ready").json()["mode"] == "simulation-only"
    version = client.get("/api/v1/system/version").json()
    assert version["physical_pilot"] == "disabled"
    assert client.get("/api/v1/drones").status_code == 401
    assert client.get("/api/v1/drones", headers=headers(tenant="other")).status_code == 403
    response = client.get("/api/v1/drones", headers=headers())
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "integration-request"
    assert len(response.json()) == 3
    schema = client.get("/openapi.json").json()
    assert "/api/v1/missions/{mission_id}/replay" in schema["paths"]
    assert "/api/v1/simulation/failures" in schema["paths"]


def test_api_complete_vertical_slice_and_read_surfaces() -> None:
    client = TestClient(create_app(ControlPlaneService()))
    assert client.get("/api/v1/fleets", headers=headers()).json()[0]["drone_count"] == 3
    assert (
        client.post(
            "/api/v1/simulation/start", headers=headers("simulator_engineer", key="sim-start")
        ).status_code
        == 200
    )
    create = client.post(
        "/api/v1/missions",
        headers=headers("mission_planner", key="mission-create"),
        json={
            "origin": {"latitude_deg": 0.01, "longitude_deg": 0.01},
            "destination": {"latitude_deg": 0.014, "longitude_deg": 0.015},
            "payload_kg": 1.2,
            "minimum_landing_reserve_percent": 25,
        },
    )
    assert create.status_code == 201
    mission_id = create.json()["mission_id"]
    duplicate = client.post(
        "/api/v1/missions",
        headers=headers("mission_planner", key="mission-create"),
        json={
            "origin": {"latitude_deg": 0.01, "longitude_deg": 0.01},
            "destination": {"latitude_deg": 0.014, "longitude_deg": 0.015},
            "payload_kg": 1.2,
            "minimum_landing_reserve_percent": 25,
        },
    )
    assert duplicate.json()["mission_id"] == mission_id
    evaluate = client.post(
        f"/api/v1/missions/{mission_id}/evaluate",
        headers=headers("mission_planner", key="evaluate"),
    )
    assert evaluate.status_code == 200
    assert evaluate.json()["selected_drone_id"] == "TRETA-001"
    assert any(not item["eligible"] for item in evaluate.json()["drones"])
    assert (
        client.post(
            f"/api/v1/missions/{mission_id}/assign",
            headers=headers("mission_planner", key="assign"),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/missions/{mission_id}/start",
            headers=headers("operator", key="start"),
        ).json()["state"]
        == "ACTIVE"
    )
    assert (
        client.post(
            "/api/v1/simulation/failures",
            headers=headers("simulator_engineer", key="failure"),
            json={
                "drone_id": "TRETA-001",
                "failure_type": "RAPID_BATTERY_DRAIN",
                "severity": "HIGH",
                "multiplier": 25,
            },
        ).status_code
        == 201
    )
    step = client.post(
        "/api/v1/simulation/step",
        headers=headers("simulator_engineer", key="step"),
        json={"seconds": 8},
    )
    assert step.json()["missions"][0]["state"] == "ABORTED"
    assert client.get("/api/v1/drones/TRETA-001", headers=headers()).status_code == 200
    assert (
        client.get("/api/v1/drones/TRETA-001/telemetry/latest", headers=headers()).json()[
            "sequence"
        ]
        > 1
    )
    assert (
        client.get(f"/api/v1/missions/{mission_id}", headers=headers()).json()["state"] == "ABORTED"
    )
    assert client.get("/api/v1/missions", headers=headers()).status_code == 200
    assert client.get(f"/api/v1/missions/{mission_id}/events", headers=headers()).status_code == 200
    incidents = client.get("/api/v1/incidents", headers=headers()).json()
    assert incidents[0]["resolution"]
    assert (
        client.get(
            f"/api/v1/incidents/{incidents[0]['incident_id']}", headers=headers()
        ).status_code
        == 200
    )
    events = client.get("/api/v1/events?limit=500", headers=headers()).json()
    assert (
        client.get(
            f"/api/v1/events?after={events[0]['event_id']}&limit=1", headers=headers()
        ).json()[0]["event_id"]
        == events[1]["event_id"]
    )
    assert client.get("/api/v1/safety-decisions", headers=headers()).json()
    replay = client.get(f"/api/v1/missions/{mission_id}/replay", headers=headers()).json()
    assert replay["deterministic"]
    assert client.get("/api/v1/simulation/status", headers=headers()).json()["elapsed_seconds"] == 8
    assert (
        client.post(
            "/api/v1/simulation/pause", headers=headers("simulator_engineer", key="pause")
        ).json()["running"]
        is False
    )


def test_api_denials_validation_and_explicit_errors() -> None:
    client = TestClient(create_app(ControlPlaneService()))
    body = {
        "origin": {"latitude_deg": 0.01, "longitude_deg": 0.01},
        "destination": {"latitude_deg": 0.014, "longitude_deg": 0.015},
        "payload_kg": 1.2,
        "minimum_landing_reserve_percent": 25,
    }
    assert (
        client.post("/api/v1/missions", headers=headers("mission_planner"), json=body).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/missions", headers=headers("viewer", key="denied"), json=body
        ).status_code
        == 403
    )
    invalid = dict(body, payload_kg=0)
    assert (
        client.post(
            "/api/v1/missions", headers=headers("mission_planner", key="invalid"), json=invalid
        ).status_code
        == 422
    )
    assert client.get("/api/v1/drones/missing", headers=headers()).status_code == 404
    assert client.get("/api/v1/incidents/missing", headers=headers()).status_code == 404
    assert client.get("/api/v1/events?after=missing", headers=headers()).status_code == 404
    too_large = client.post(
        "/api/v1/missions",
        headers={**headers("mission_planner", key="large"), "Content-Length": "70000"},
        content=b"{}",
    )
    assert too_large.status_code == 413
    invalid_length = client.get("/api/v1/health/live", headers={"Content-Length": "not-a-number"})
    assert invalid_length.status_code == 400


def test_rate_limiter_enforces_bound(monkeypatch) -> None:
    from treta.api import app as app_module

    monkeypatch.setattr(app_module, "RATE_LIMIT_PER_MINUTE", 2)
    limiter = InMemoryRateLimiter()
    assert limiter.allow("actor", 0)
    assert limiter.allow("actor", 1)
    assert not limiter.allow("actor", 2)
    assert limiter.allow("actor", 61)


def test_stream_requires_identity_and_returns_snapshot() -> None:
    client = TestClient(create_app(ControlPlaneService()))
    with client.websocket_connect("/api/v1/stream") as websocket:
        websocket.send_json(
            {"actor_id": "stream-viewer", "tenant_id": "tenant-synthetic", "role": "viewer"}
        )
        assert websocket.receive_json()["simulation"]["drone_count"] == 3
    with client.websocket_connect("/api/v1/stream") as websocket:
        websocket.send_json({"actor_id": "bad"})
        assert websocket.receive_json()["error"]["code"] == "AUTHORIZATION_DENIED"
