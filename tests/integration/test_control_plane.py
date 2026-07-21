from __future__ import annotations

import pytest

from treta.application.control_plane import (
    ApplicationConflictError,
    run_demo_scenario,
)
from treta.domain.models import FailureType, HealthState, MissionState, Position
from treta.ports.interfaces import AuthorizationError
from treta.simulation.scenarios import load_scenario


def create_mission(service, planner, key="create-1"):
    return service.create_mission(
        planner,
        origin=Position(0.01, 0.01),
        destination=Position(0.014, 0.015),
        payload_kg=1.2,
        minimum_landing_reserve_percent=25,
        idempotency_key=key,
    )


def test_complete_failure_path_is_audited_and_replays() -> None:
    scenario = load_scenario(
        __import__("pathlib").Path("simulators/scenarios/rapid-battery-drain.yaml")
    )
    service, replay = run_demo_scenario(scenario)
    mission = service.repository.list_missions("tenant-synthetic")[0]
    incident = service.repository.list_incidents("tenant-synthetic")[0]
    drone = service.repository.get_drone("tenant-synthetic", mission.assigned_drone_id or "")
    events = service.events(limit=500)
    event_types = [event.event_type for event in events]
    assert mission.state is MissionState.ABORTED
    assert drone.state.value == "LANDED"
    assert incident.resolution == "controlled landing observed; mission aborted"
    assert incident.timeline_event_ids
    assert "safety.rule_triggered" in event_types
    assert "mission.safety_fallback_started" in event_types
    assert "mission.aborted_after_safe_landing" in event_types
    command_types = {command.command_type for command in service.repository.commands.values()}
    assert {"RETURN_TO_HOME", "CONTROLLED_LANDING"} <= command_types
    assert replay.deterministic
    assert replay.original_event_count == replay.replay_event_count
    assert replay.original_final_hash == replay.replay_final_hash
    assert all(event.integrity["event_hash"] for event in events)


def test_mutations_are_idempotent(service, planner, operator, simulator_engineer) -> None:
    service.start_simulation(simulator_engineer)
    first = create_mission(service, planner)
    duplicate = create_mission(service, planner)
    assert duplicate.mission_id == first.mission_id
    service.evaluate_mission(planner, first.mission_id)
    assert service.evaluate_mission(planner, first.mission_id).mission_id == first.mission_id
    assigned = service.assign_mission(planner, first.mission_id, "assign-1")
    duplicate_assigned = service.assign_mission(planner, first.mission_id, "assign-1")
    assert duplicate_assigned.mission_id == assigned.mission_id
    started = service.start_mission(operator, first.mission_id, "start-1")
    duplicate_started = service.start_mission(operator, first.mission_id, "start-1")
    assert duplicate_started.state is started.state is MissionState.ACTIVE
    first_failure = service.inject_failure(
        simulator_engineer,
        drone_id=started.assigned_drone_id or "",
        failure_type=FailureType.RAPID_BATTERY_DRAIN,
        severity="HIGH",
        multiplier=30,
        idempotency_key="failure-1",
    )
    duplicate_failure = service.inject_failure(
        simulator_engineer,
        drone_id=started.assigned_drone_id or "",
        failure_type=FailureType.RAPID_BATTERY_DRAIN,
        severity="HIGH",
        multiplier=30,
        idempotency_key="failure-1",
    )
    assert not first_failure["idempotent_replay"]
    assert duplicate_failure["idempotent_replay"]


def test_authorization_and_state_conflicts_fail_closed(service, viewer, planner, operator) -> None:
    with pytest.raises(AuthorizationError, match="missing permission"):
        create_mission(service, viewer)
    mission = create_mission(service, planner)
    with pytest.raises(ApplicationConflictError, match="no assigned"):
        service.start_mission(operator, mission.mission_id, "too-early")
    for drone in service.repository.list_drones("tenant-synthetic"):
        drone.health = HealthState.CRITICAL
    result = service.evaluate_mission(planner, mission.mission_id)
    assert result.selected_drone_id is None
    assert (
        service.repository.get_mission("tenant-synthetic", mission.mission_id).state
        is MissionState.REJECTED
    )
    with pytest.raises(ApplicationConflictError, match="eligible"):
        service.assign_mission(planner, mission.mission_id, "assign-rejected")


def test_simulation_controls_and_bounds(service, simulator_engineer) -> None:
    status = service.start_simulation(simulator_engineer)
    assert status["running"]
    snapshot = service.step(simulator_engineer)
    assert snapshot["simulation"]["elapsed_seconds"] == 1
    assert len(snapshot["latest_telemetry"]) == 3
    assert not service.pause_simulation(simulator_engineer)["running"]
    with pytest.raises(ValueError, match="between 1 and 60"):
        service.step(simulator_engineer, 0)


def test_demo_runner_rejects_wrong_fleet_size() -> None:
    scenario = load_scenario(
        __import__("pathlib").Path("simulators/scenarios/rapid-battery-drain.yaml")
    )
    smaller = scenario.model_copy(update={"fleet": scenario.fleet[:2]})
    with pytest.raises(ValueError, match="exactly three"):
        run_demo_scenario(smaller)
