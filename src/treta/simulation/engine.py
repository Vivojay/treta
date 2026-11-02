from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from treta.domain.models import (
    Drone,
    DroneState,
    FailureType,
    GpsQuality,
    Mission,
    PolicyDecision,
    Position,
    SafetyAction,
    Telemetry,
)
from treta.domain.state_machines import transition_drone
from treta.safety.policies import LocalLandingReservePolicy


@dataclass(slots=True)
class SimulationClock:
    now: datetime = field(default_factory=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    elapsed_seconds: int = 0

    def advance(self, seconds: int = 1) -> datetime:
        if seconds <= 0:
            raise ValueError("simulation step must be a positive number of seconds")
        self.elapsed_seconds += seconds
        self.now += timedelta(seconds=seconds)
        return self.now


@dataclass(frozen=True, slots=True)
class Failure:
    drone_id: str
    failure_type: FailureType
    severity: str
    multiplier: float
    injected_at: datetime


@dataclass(frozen=True, slots=True)
class LocalSafetyTrigger:
    drone_id: str
    mission_id: str
    action: SafetyAction
    decision: PolicyDecision


@dataclass(frozen=True, slots=True)
class SimulationTickResult:
    telemetry: tuple[Telemetry, ...]
    safety_triggers: tuple[LocalSafetyTrigger, ...]
    landed_drone_ids: tuple[str, ...]


class DeterministicFleetSimulator:
    def __init__(self, *, seed: int) -> None:
        self.seed = seed
        self.clock = SimulationClock()
        self.running = False
        self._failures: dict[str, Failure] = {}
        self._missions: dict[str, Mission] = {}
        self._latest_telemetry: dict[str, Telemetry] = {}
        self._local_policy = LocalLandingReservePolicy()
        self._random_by_drone: dict[str, random.Random] = {}

    def register_drones(self, drones: list[Drone]) -> None:
        for drone in drones:
            digest = hashlib.sha256(f"{self.seed}:{drone.drone_id}".encode()).digest()
            # Operational simulation noise is deterministic and is never used for security.
            self._random_by_drone[drone.drone_id] = random.Random(  # noqa: S311  # nosec B311
                int.from_bytes(digest[:8])
            )
            self._latest_telemetry[drone.drone_id] = self._telemetry_for(drone)

    def start(self) -> None:
        self.running = True

    def pause(self) -> None:
        self.running = False

    def attach_mission(self, mission: Mission) -> None:
        self._missions[mission.mission_id] = mission

    def inject_failure(
        self,
        *,
        drone_id: str,
        failure_type: FailureType,
        severity: str,
        multiplier: float,
    ) -> Failure:
        if multiplier <= 0 or not math.isfinite(multiplier):
            raise ValueError("failure multiplier must be finite and positive")
        failure = Failure(
            drone_id=drone_id,
            failure_type=failure_type,
            severity=severity,
            multiplier=multiplier,
            injected_at=self.clock.now,
        )
        self._failures[drone_id] = failure
        return failure

    def latest_telemetry(self, drone_id: str) -> Telemetry:
        return self._latest_telemetry[drone_id]

    def step(self, drones: list[Drone], seconds: int = 1) -> SimulationTickResult:
        if not self.running:
            raise RuntimeError("simulation must be started before stepping")
        telemetry_items: list[Telemetry] = []
        triggers: list[LocalSafetyTrigger] = []
        landed: list[str] = []
        for _ in range(seconds):
            self.clock.advance()
            for drone in sorted(drones, key=lambda item: item.drone_id):
                was_landed = drone.state is DroneState.LANDED
                self._advance_drone(drone)
                telemetry = self._telemetry_for(drone)
                self._latest_telemetry[drone.drone_id] = telemetry
                telemetry_items.append(telemetry)
                trigger = self._evaluate_local_safety(drone)
                if trigger is not None:
                    triggers.append(trigger)
                if not was_landed and drone.state is DroneState.LANDED:
                    landed.append(drone.drone_id)
        return SimulationTickResult(tuple(telemetry_items), tuple(triggers), tuple(landed))

    def _advance_drone(self, drone: Drone) -> None:
        mission = self._missions.get(drone.current_mission_id or "")
        failure = self._failures.get(drone.drone_id)
        if failure and failure.failure_type is FailureType.GPS_DEGRADATION:
            drone.gps_quality = GpsQuality.DEGRADED
        if failure and failure.failure_type is FailureType.TOTAL_LINK_LOSS:
            drone.link_quality_percent = 0.0

        airborne = drone.state in {
            DroneState.IN_MISSION,
            DroneState.HOLDING,
            DroneState.RETURNING_HOME,
            DroneState.LANDING,
        }
        if airborne:
            drain = 0.6
            if mission is not None:
                drain += 0.2 * (mission.payload_kg / drone.profile.maximum_payload_kg)
            if failure and failure.failure_type is FailureType.RAPID_BATTERY_DRAIN:
                drain *= failure.multiplier
            drone.battery_percent = max(0.0, drone.battery_percent - drain)

        if drone.state is DroneState.IN_MISSION and mission is not None:
            drone.position = self._move_towards(drone.position, mission.destination, drone)
        elif drone.state is DroneState.RETURNING_HOME:
            drone.position = self._move_towards(drone.position, drone.home, drone)
        elif drone.state is DroneState.LANDING:
            next_altitude = max(0.0, drone.position.altitude_m - 10.0)
            drone.position = Position(
                drone.position.latitude_deg, drone.position.longitude_deg, next_altitude
            )
            if next_altitude == 0.0:
                drone.state = transition_drone(drone.state, DroneState.LANDED)
                drone.current_mission_id = None

    def _move_towards(self, current: Position, target: Position, drone: Drone) -> Position:
        latitude_delta = target.latitude_deg - current.latitude_deg
        longitude_delta = target.longitude_deg - current.longitude_deg
        degree_distance = math.hypot(latitude_delta, longitude_delta)
        if degree_distance == 0:
            return Position(target.latitude_deg, target.longitude_deg, max(30.0, target.altitude_m))
        meters = degree_distance * 111_320.0
        fraction = min(1.0, drone.profile.cruise_speed_mps / meters)
        return Position(
            current.latitude_deg + latitude_delta * fraction,
            current.longitude_deg + longitude_delta * fraction,
            max(30.0, target.altitude_m),
        )

    def _telemetry_for(self, drone: Drone) -> Telemetry:
        drone.last_telemetry_sequence += 1
        drone.last_observed_at = self.clock.now
        rng = self._random_by_drone.get(drone.drone_id)
        noise = 0.0 if rng is None else rng.uniform(-0.02, 0.02)
        return Telemetry(
            schema_version=1,
            drone_id=drone.drone_id,
            sequence=drone.last_telemetry_sequence,
            vehicle_event_time=self.clock.now,
            platform_ingest_time=self.clock.now,
            position=drone.position,
            ground_speed_mps=(
                max(0.0, drone.profile.cruise_speed_mps + noise)
                if drone.state in {DroneState.IN_MISSION, DroneState.RETURNING_HOME}
                else 0.0
            ),
            battery_percent=round(drone.battery_percent, 3),
            gps_quality=drone.gps_quality,
            link_quality_percent=drone.link_quality_percent,
            flight_mode=drone.state.value,
        )

    def _evaluate_local_safety(self, drone: Drone) -> LocalSafetyTrigger | None:
        mission = self._missions.get(drone.current_mission_id or "")
        if mission is None or drone.state not in {
            DroneState.IN_MISSION,
            DroneState.HOLDING,
            DroneState.RETURNING_HOME,
        }:
            return None
        action, decision = self._local_policy.evaluate(
            battery_percent=drone.battery_percent,
            landing_reserve_percent=mission.minimum_landing_reserve_percent,
            supports_return_to_home=drone.profile.supports_return_to_home,
            supports_controlled_landing=drone.profile.supports_controlled_landing,
            now=self.clock.now,
        )
        if action is SafetyAction.NONE or decision is None:
            return None
        if action is SafetyAction.RETURN_TO_HOME and drone.state is not DroneState.RETURNING_HOME:
            drone.state = transition_drone(drone.state, DroneState.RETURNING_HOME)
            return LocalSafetyTrigger(drone.drone_id, mission.mission_id, action, decision)
        if action is SafetyAction.CONTROLLED_LANDING and drone.state is not DroneState.LANDING:
            drone.state = transition_drone(drone.state, DroneState.LANDING)
            return LocalSafetyTrigger(drone.drone_id, mission.mission_id, action, decision)
        return None
