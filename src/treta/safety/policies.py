from __future__ import annotations

import math
from datetime import datetime, timedelta

from treta.domain.models import (
    Drone,
    DroneEligibility,
    DroneState,
    EligibilityResult,
    GpsQuality,
    HealthState,
    Mission,
    PolicyDecision,
    SafetyAction,
)

POLICY_VERSION = "2026-07-21.1"
STALE_AFTER = timedelta(seconds=10)
EMERGENCY_LANDING_THRESHOLD_PERCENT = 10.0


def _decision(
    *,
    allowed: bool,
    rule_id: str,
    severity: str,
    facts: dict[str, object],
    reason: str,
    action: str,
    evaluated_at: datetime,
) -> PolicyDecision:
    return PolicyDecision(
        decision="ALLOW" if allowed else "REJECT",
        rule_id=rule_id,
        rule_version=POLICY_VERSION,
        severity=severity,
        input_facts=facts,
        reason=reason,
        recommended_action=action,
        human_approval_required=False,
        evaluated_at=evaluated_at,
    )


def _distance_m(mission: Mission) -> float:
    lat_scale = 111_320.0
    mean_lat_rad = math.radians(
        (mission.origin.latitude_deg + mission.destination.latitude_deg) / 2
    )
    lat_delta = (mission.destination.latitude_deg - mission.origin.latitude_deg) * lat_scale
    lon_delta = (
        (mission.destination.longitude_deg - mission.origin.longitude_deg)
        * lat_scale
        * math.cos(mean_lat_rad)
    )
    return math.hypot(lat_delta, lon_delta)


def _estimated_arrival_battery(drone: Drone, mission: Mission) -> float:
    distance_energy = (_distance_m(mission) / drone.profile.nominal_range_m) * 100.0
    payload_energy = (mission.payload_kg / drone.profile.maximum_payload_kg) * 8.0
    takeoff_and_reserve_margin = 8.0
    return drone.battery_percent - distance_energy - payload_energy - takeoff_and_reserve_margin


class EligibilityPolicy:
    def evaluate(self, mission: Mission, drones: list[Drone], now: datetime) -> EligibilityResult:
        results = tuple(self._evaluate_drone(mission, drone, now) for drone in drones)
        eligible = [result for result in results if result.eligible and result.score is not None]
        selected = max(
            eligible,
            key=lambda item: (item.score if item.score is not None else -math.inf, item.drone_id),
            default=None,
        )
        return EligibilityResult(
            mission_id=mission.mission_id,
            policy_version=POLICY_VERSION,
            drones=results,
            selected_drone_id=selected.drone_id if selected else None,
        )

    def _evaluate_drone(self, mission: Mission, drone: Drone, now: datetime) -> DroneEligibility:
        failures: list[PolicyDecision] = []
        malformed = not all(
            math.isfinite(value)
            for value in (
                mission.payload_kg,
                mission.minimum_landing_reserve_percent,
                drone.battery_percent,
            )
        )
        if malformed or mission.payload_kg <= 0:
            failures.append(
                _decision(
                    allowed=False,
                    rule_id="MALFORMED_MISSION_INPUT",
                    severity="CRITICAL",
                    facts={"payload_kg": mission.payload_kg},
                    reason="Mission numeric inputs must be finite and payload must be positive.",
                    action="CORRECT_MISSION",
                    evaluated_at=now,
                )
            )
            return DroneEligibility(drone.drone_id, False, None, None, tuple(failures))

        checks: tuple[tuple[bool, str, str, dict[str, object], str, str], ...] = (
            (
                drone.health not in {HealthState.CRITICAL, HealthState.DISCONNECTED},
                "DRONE_HEALTH_ACCEPTABLE",
                "CRITICAL",
                {"health": drone.health.value},
                "Drone health is critical or disconnected.",
                "SELECT_ANOTHER_DRONE",
            ),
            (
                drone.link_quality_percent > 0,
                "DRONE_CONNECTED",
                "HIGH",
                {"link_quality_percent": drone.link_quality_percent},
                "Drone has no current control-plane link.",
                "WAIT_FOR_RECONNECT",
            ),
            (
                now - drone.last_observed_at <= STALE_AFTER,
                "TELEMETRY_FRESH",
                "HIGH",
                {"age_seconds": (now - drone.last_observed_at).total_seconds()},
                "Drone telemetry is stale.",
                "WAIT_FOR_FRESH_TELEMETRY",
            ),
            (
                drone.state is DroneState.IDLE and drone.current_mission_id is None,
                "DRONE_AVAILABLE",
                "HIGH",
                {"state": drone.state.value, "current_mission_id": drone.current_mission_id},
                "Drone is not idle and unassigned.",
                "SELECT_ANOTHER_DRONE",
            ),
            (
                mission.mission_type in drone.profile.supported_mission_types,
                "MISSION_TYPE_SUPPORTED",
                "HIGH",
                {"mission_type": mission.mission_type},
                "Drone capability profile does not support this mission type.",
                "SELECT_COMPATIBLE_DRONE",
            ),
            (
                mission.payload_kg <= drone.profile.maximum_payload_kg,
                "PAYLOAD_WITHIN_LIMIT",
                "CRITICAL",
                {
                    "payload_kg": mission.payload_kg,
                    "maximum_payload_kg": drone.profile.maximum_payload_kg,
                },
                "Mission payload exceeds the drone limit.",
                "REDUCE_PAYLOAD_OR_SELECT_ANOTHER_DRONE",
            ),
            (
                drone.gps_quality is GpsQuality.GOOD,
                "GPS_QUALITY_VALID",
                "HIGH",
                {"gps_quality": drone.gps_quality.value},
                "GPS quality is not valid for mission dispatch.",
                "WAIT_OR_SELECT_ANOTHER_DRONE",
            ),
        )
        for allowed, rule_id, severity, facts, reason, action in checks:
            if not allowed:
                failures.append(
                    _decision(
                        allowed=False,
                        rule_id=rule_id,
                        severity=severity,
                        facts=facts,
                        reason=reason,
                        action=action,
                        evaluated_at=now,
                    )
                )

        arrival = None if failures else _estimated_arrival_battery(drone, mission)
        if arrival is not None and arrival < mission.minimum_landing_reserve_percent:
            failures.append(
                _decision(
                    allowed=False,
                    rule_id="BATTERY_LANDING_RESERVE",
                    severity="CRITICAL",
                    facts={
                        "estimated_arrival_battery_percent": round(arrival, 3),
                        "minimum_landing_reserve_percent": mission.minimum_landing_reserve_percent,
                    },
                    reason="Estimated arrival battery is below the landing reserve.",
                    action="SELECT_ANOTHER_DRONE_OR_REPLAN",
                    evaluated_at=now,
                )
            )

        if failures:
            return DroneEligibility(drone.drone_id, False, None, arrival, tuple(failures))

        assert arrival is not None
        score = arrival + drone.profile.redundancy_score
        allowed_decision = _decision(
            allowed=True,
            rule_id="MISSION_ELIGIBILITY",
            severity="INFO",
            facts={
                "estimated_arrival_battery_percent": round(arrival, 3),
                "redundancy_score": drone.profile.redundancy_score,
            },
            reason="Drone satisfies all deterministic eligibility rules.",
            action="ELIGIBLE_FOR_ASSIGNMENT",
            evaluated_at=now,
        )
        return DroneEligibility(
            drone.drone_id,
            True,
            round(score, 3),
            round(arrival, 3),
            (allowed_decision,),
        )


class LocalLandingReservePolicy:
    """A vehicle-boundary decision that does not depend on cloud connectivity."""

    def evaluate(
        self,
        *,
        battery_percent: float,
        landing_reserve_percent: float,
        supports_return_to_home: bool,
        supports_controlled_landing: bool,
        now: datetime,
    ) -> tuple[SafetyAction, PolicyDecision | None]:
        if not math.isfinite(battery_percent) or not math.isfinite(landing_reserve_percent):
            return SafetyAction.CONTROLLED_LANDING, _decision(
                allowed=False,
                rule_id="BATTERY_TELEMETRY_INVALID",
                severity="CRITICAL",
                facts={"battery_percent": battery_percent},
                reason=(
                    "Battery telemetry is not finite; safe continued mission cannot be established."
                ),
                action="CONTROLLED_LANDING",
                evaluated_at=now,
            )
        if battery_percent > landing_reserve_percent:
            return SafetyAction.NONE, None
        if supports_return_to_home and battery_percent >= EMERGENCY_LANDING_THRESHOLD_PERCENT:
            action = SafetyAction.RETURN_TO_HOME
        elif supports_controlled_landing:
            action = SafetyAction.CONTROLLED_LANDING
        else:
            action = SafetyAction.CONTROLLED_LANDING
        return action, _decision(
            allowed=False,
            rule_id="BATTERY_LANDING_RESERVE",
            severity="CRITICAL",
            facts={
                "battery_percent": round(battery_percent, 3),
                "landing_reserve_percent": landing_reserve_percent,
                "return_to_home_supported": supports_return_to_home,
                "controlled_landing_supported": supports_controlled_landing,
            },
            reason="Battery is at or below the mission landing reserve.",
            action=action.value,
            evaluated_at=now,
        )
