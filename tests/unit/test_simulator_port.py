from __future__ import annotations

import pytest

from treta.application.control_plane import ApplicationConflictError, ControlPlaneService
from treta.domain.models import Drone
from treta.ports.interfaces import Principal
from treta.simulation.engine import DeterministicFleetSimulator, SimulationTickResult


class TrackingSimulator(DeterministicFleetSimulator):
    """Independent injected backend exercised through the application boundary."""

    def __init__(self, *, seed: int) -> None:
        super().__init__(seed=seed)
        self.register_calls = 0
        self.step_calls = 0

    def register_drones(self, drones: list[Drone]) -> None:
        self.register_calls += 1
        super().register_drones(drones)

    def step(self, drones: list[Drone], seconds: int = 1) -> SimulationTickResult:
        self.step_calls += 1
        return super().step(drones, seconds)


def test_control_plane_accepts_injected_simulation_backend(
    simulator_engineer: Principal,
) -> None:
    backend = TrackingSimulator(seed=42)
    service = ControlPlaneService(seed=42, simulator=backend)

    assert service.simulator is backend
    assert backend.register_calls == 1
    assert service.status()["drone_count"] == 3

    service.start_simulation(simulator_engineer)
    snapshot = service.step(simulator_engineer)
    assert backend.step_calls == 1
    assert snapshot["simulation"]["elapsed_seconds"] == 1
    assert len(snapshot["latest_telemetry"]) == 3


def test_injected_backend_cannot_claim_builtin_deterministic_replay() -> None:
    backend = TrackingSimulator(seed=42)
    service = ControlPlaneService(seed=42, simulator=backend)
    with pytest.raises(ApplicationConflictError, match="built-in deterministic simulator"):
        service.replay()


def test_injected_backend_cannot_fake_mission_dispatch(operator: Principal) -> None:
    service = ControlPlaneService(seed=42, simulator=TrackingSimulator(seed=42))
    with pytest.raises(ApplicationConflictError, match="validated command receipt"):
        service.start_mission(operator, "mission-001", "start-unsupported")


def test_injected_backend_seed_must_match_service_seed() -> None:
    with pytest.raises(ValueError, match="must match"):
        ControlPlaneService(seed=42, simulator=TrackingSimulator(seed=99))
