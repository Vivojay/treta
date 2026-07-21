from __future__ import annotations

import copy
from datetime import timedelta

import pytest

from treta.application.control_plane import ControlPlaneService
from treta.domain.models import (
    DroneState,
    GpsQuality,
    HealthState,
    Mission,
    MissionState,
    Position,
    SafetyAction,
)
from treta.safety.policies import EligibilityPolicy, LocalLandingReservePolicy


def mission(service: ControlPlaneService, *, payload: float = 1.2) -> Mission:
    return Mission(
        "mission-test",
        "tenant-synthetic",
        "fleet-demo",
        "DELIVERY_SIMULATION",
        Position(0.01, 0.01),
        Position(0.014, 0.015),
        payload,
        25,
        MissionState.DRAFT,
        "test",
        service.simulator.clock.now,
    )


def test_eligibility_selects_safest_and_explains_rejections(service) -> None:
    result = EligibilityPolicy().evaluate(
        mission(service),
        service.repository.list_drones("tenant-synthetic"),
        service.simulator.clock.now,
    )
    assert result.selected_drone_id == "TRETA-001"
    by_id = {item.drone_id: item for item in result.drones}
    assert by_id["TRETA-001"].eligible
    assert by_id["TRETA-002"].eligible
    assert not by_id["TRETA-003"].eligible
    assert {reason.rule_id for reason in by_id["TRETA-003"].reasons} >= {
        "MISSION_TYPE_SUPPORTED",
        "PAYLOAD_WITHIN_LIMIT",
        "GPS_QUALITY_VALID",
    }


@pytest.mark.parametrize(
    ("mutation", "expected_rule"),
    [
        (
            lambda drone, now: setattr(drone, "health", HealthState.CRITICAL),
            "DRONE_HEALTH_ACCEPTABLE",
        ),
        (lambda drone, now: setattr(drone, "link_quality_percent", 0), "DRONE_CONNECTED"),
        (
            lambda drone, now: setattr(drone, "last_observed_at", now - timedelta(seconds=11)),
            "TELEMETRY_FRESH",
        ),
        (
            lambda drone, now: setattr(drone, "state", DroneState.MAINTENANCE_REQUIRED),
            "DRONE_AVAILABLE",
        ),
        (lambda drone, now: setattr(drone, "gps_quality", GpsQuality.INVALID), "GPS_QUALITY_VALID"),
        (lambda drone, now: setattr(drone, "battery_percent", 26), "BATTERY_LANDING_RESERVE"),
    ],
)
def test_each_dispatch_guard_rejects(mutation, expected_rule, service) -> None:
    now = service.simulator.clock.now
    drone = copy.deepcopy(service.repository.get_drone("tenant-synthetic", "TRETA-001"))
    mutation(drone, now)
    result = EligibilityPolicy().evaluate(mission(service), [drone], now).drones[0]
    assert not result.eligible
    assert expected_rule in {reason.rule_id for reason in result.reasons}


def test_malformed_mission_is_rejected_without_computation(service) -> None:
    malformed = mission(service)
    malformed.payload_kg = float("nan")
    result = (
        EligibilityPolicy()
        .evaluate(
            malformed,
            [service.repository.get_drone("tenant-synthetic", "TRETA-001")],
            service.simulator.clock.now,
        )
        .drones[0]
    )
    assert result.reasons[0].rule_id == "MALFORMED_MISSION_INPUT"


def test_local_reserve_policy_negative_boundary_and_emergency(service) -> None:
    policy = LocalLandingReservePolicy()
    now = service.simulator.clock.now
    assert policy.evaluate(
        battery_percent=25.1,
        landing_reserve_percent=25,
        supports_return_to_home=True,
        supports_controlled_landing=True,
        now=now,
    ) == (SafetyAction.NONE, None)
    action, decision = policy.evaluate(
        battery_percent=25,
        landing_reserve_percent=25,
        supports_return_to_home=True,
        supports_controlled_landing=True,
        now=now,
    )
    assert action is SafetyAction.RETURN_TO_HOME
    assert decision and decision.rule_id == "BATTERY_LANDING_RESERVE"
    action, _ = policy.evaluate(
        battery_percent=9,
        landing_reserve_percent=25,
        supports_return_to_home=True,
        supports_controlled_landing=True,
        now=now,
    )
    assert action is SafetyAction.CONTROLLED_LANDING
    action, _ = policy.evaluate(
        battery_percent=20,
        landing_reserve_percent=25,
        supports_return_to_home=False,
        supports_controlled_landing=False,
        now=now,
    )
    assert action is SafetyAction.CONTROLLED_LANDING


def test_local_reserve_malformed_input_fails_safe(service) -> None:
    action, decision = LocalLandingReservePolicy().evaluate(
        battery_percent=float("nan"),
        landing_reserve_percent=25,
        supports_return_to_home=True,
        supports_controlled_landing=True,
        now=service.simulator.clock.now,
    )
    assert action is SafetyAction.CONTROLLED_LANDING
    assert decision and decision.rule_id == "BATTERY_TELEMETRY_INVALID"
