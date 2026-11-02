from __future__ import annotations

import pytest

from treta.application.control_plane import ControlPlaneService
from treta.domain.models import FailureType, GpsQuality
from treta.simulation.engine import SimulationClock


def test_clock_and_failure_input_are_bounded(service) -> None:
    with pytest.raises(ValueError, match="positive"):
        SimulationClock().advance(0)
    with pytest.raises(ValueError, match="finite and positive"):
        service.simulator.inject_failure(
            drone_id="TRETA-001",
            failure_type=FailureType.RAPID_BATTERY_DRAIN,
            severity="HIGH",
            multiplier=0,
        )


def test_simulator_requires_explicit_start(service) -> None:
    with pytest.raises(RuntimeError, match="started"):
        service.simulator.step(service.repository.list_drones("tenant-synthetic"))
    with pytest.raises(KeyError):
        service.simulator.latest_telemetry("unknown")


def test_seeded_telemetry_and_initial_failures_are_repeatable() -> None:
    first_service = ControlPlaneService(seed=99)
    second_service = ControlPlaneService(seed=99)
    for service in (first_service, second_service):
        service.simulator.start()
        service.simulator.inject_failure(
            drone_id="TRETA-002",
            failure_type=FailureType.GPS_DEGRADATION,
            severity="HIGH",
            multiplier=1,
        )
        service.simulator.inject_failure(
            drone_id="TRETA-003",
            failure_type=FailureType.TOTAL_LINK_LOSS,
            severity="HIGH",
            multiplier=1,
        )
    first = first_service.simulator.step(first_service.repository.list_drones("tenant-synthetic"))
    second = second_service.simulator.step(
        second_service.repository.list_drones("tenant-synthetic")
    )
    assert first.telemetry == second.telemetry
    assert (
        first_service.repository.get_drone("tenant-synthetic", "TRETA-002").gps_quality
        is GpsQuality.DEGRADED
    )
    assert (
        first_service.repository.get_drone("tenant-synthetic", "TRETA-003").link_quality_percent
        == 0
    )
    assert first.safety_triggers == ()
    assert first.landed_drone_ids == ()


def test_simulator_pause_stops_step(service) -> None:
    service.simulator.start()
    service.simulator.pause()
    with pytest.raises(RuntimeError, match="started"):
        service.simulator.step(service.repository.list_drones("tenant-synthetic"))
