from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from treta.adapters.memory import InMemoryControlPlaneRepository, InMemoryEventStore, authorize
from treta.domain.models import (
    CapabilityProfile,
    Command,
    CommandState,
    DomainEvent,
    Drone,
    DroneState,
    EligibilityResult,
    EventDraft,
    FailureType,
    GpsQuality,
    HealthState,
    Incident,
    Mission,
    MissionState,
    Position,
    SafetyAction,
    to_primitive,
)
from treta.domain.state_machines import (
    transition_command,
    transition_drone,
    transition_mission,
)
from treta.ports.interfaces import ControlPlaneRepositoryPort, EventStorePort, Principal
from treta.safety.policies import EligibilityPolicy
from treta.simulation.engine import DeterministicFleetSimulator, LocalSafetyTrigger
from treta.simulation.scenarios import Scenario

DEFAULT_TENANT_ID = "tenant-synthetic"
DEFAULT_FLEET_ID = "fleet-demo"


class ApplicationConflictError(RuntimeError):
    """A requested operation conflicts with current domain state."""


@dataclass(frozen=True, slots=True)
class ReplayResult:
    deterministic: bool
    original_event_count: int
    replay_event_count: int
    original_final_hash: str | None
    replay_final_hash: str | None


class ControlPlaneService:
    def __init__(
        self,
        *,
        seed: int = 42,
        repository: ControlPlaneRepositoryPort | None = None,
        event_store: EventStorePort | None = None,
    ) -> None:
        self.seed = seed
        self.repository = repository or InMemoryControlPlaneRepository()
        self.event_store = event_store or InMemoryEventStore()
        self.simulator = DeterministicFleetSimulator(seed=seed)
        self.eligibility_policy = EligibilityPolicy()
        self._eligibility: dict[str, EligibilityResult] = {}
        self._active_safety_command: dict[str, str] = {}
        self._incident_by_mission: dict[str, str] = {}
        self._actions: list[tuple[str, tuple[Any, ...]]] = []
        self._mission_counter = 0
        self._command_counter = 0
        self._incident_counter = 0
        self._bootstrap_default_fleet()

    def _bootstrap_default_fleet(self) -> None:
        now = self.simulator.clock.now
        profiles = {
            "light-delivery-quad": CapabilityProfile(
                "light-delivery-quad",
                "Light delivery quad",
                2.0,
                15.0,
                8_000.0,
                25.0,
                frozenset({"DELIVERY_SIMULATION"}),
                True,
                True,
                10.0,
            ),
            "medium-delivery-hex": CapabilityProfile(
                "medium-delivery-hex",
                "Medium delivery hex",
                5.0,
                12.0,
                12_000.0,
                25.0,
                frozenset({"DELIVERY_SIMULATION"}),
                True,
                True,
                16.0,
            ),
            "legacy-degraded-quad": CapabilityProfile(
                "legacy-degraded-quad",
                "Legacy degraded quad",
                0.8,
                9.0,
                4_000.0,
                30.0,
                frozenset({"SURVEY_SIMULATION"}),
                True,
                True,
                2.0,
            ),
        }
        home = Position(0.0100, 0.0100, 0.0)
        drones = [
            Drone(
                "TRETA-001",
                DEFAULT_TENANT_ID,
                DEFAULT_FLEET_ID,
                "Aster",
                "Synthetic",
                "Q-Lite",
                profiles["light-delivery-quad"],
                DroneState.IDLE,
                HealthState.NORMAL,
                home,
                home,
                92.0,
                GpsQuality.GOOD,
                98.0,
                0,
                now,
            ),
            Drone(
                "TRETA-002",
                DEFAULT_TENANT_ID,
                DEFAULT_FLEET_ID,
                "Beryl",
                "Synthetic",
                "H-Medium",
                profiles["medium-delivery-hex"],
                DroneState.IDLE,
                HealthState.NORMAL,
                home,
                home,
                76.0,
                GpsQuality.GOOD,
                96.0,
                0,
                now,
            ),
            Drone(
                "TRETA-003",
                DEFAULT_TENANT_ID,
                DEFAULT_FLEET_ID,
                "Cinder",
                "Synthetic",
                "Q-Legacy",
                profiles["legacy-degraded-quad"],
                DroneState.IDLE,
                HealthState.WARNING,
                home,
                home,
                61.0,
                GpsQuality.DEGRADED,
                72.0,
                0,
                now,
            ),
        ]
        self.simulator.register_drones(drones)
        for drone in drones:
            self.repository.save_drone(drone)
            self._record(
                "drone.registered",
                drone.drone_id,
                "bootstrap",
                {
                    "drone": to_primitive(drone),
                    "data_classification": "synthetic",
                    "authorization_decision": "SYSTEM_BOOTSTRAP",
                },
                producer="treta.bootstrap",
            )

    def start_simulation(
        self, principal: Principal, *, record_action: bool = True
    ) -> dict[str, Any]:
        authorize(principal, "simulation:control", DEFAULT_TENANT_ID)
        self.simulator.start()
        self._record_audit(
            "simulation.started",
            "simulation-demo",
            principal,
            "simulation:start",
            {},
            "STOPPED",
            "RUNNING",
        )
        if record_action:
            self._actions.append(("start_simulation", (principal,)))
        return self.status()

    def pause_simulation(
        self, principal: Principal, *, record_action: bool = True
    ) -> dict[str, Any]:
        authorize(principal, "simulation:control", DEFAULT_TENANT_ID)
        self.simulator.pause()
        self._record_audit(
            "simulation.paused",
            "simulation-demo",
            principal,
            "simulation:pause",
            {},
            "RUNNING",
            "PAUSED",
        )
        if record_action:
            self._actions.append(("pause_simulation", (principal,)))
        return self.status()

    def create_mission(
        self,
        principal: Principal,
        *,
        origin: Position,
        destination: Position,
        payload_kg: float,
        minimum_landing_reserve_percent: float,
        idempotency_key: str,
        record_action: bool = True,
    ) -> Mission:
        authorize(principal, "mission:create", DEFAULT_TENANT_ID)
        previous_id = self.repository.resolve_idempotency(
            DEFAULT_TENANT_ID, f"mission:create:{idempotency_key}"
        )
        if previous_id:
            return self.repository.get_mission(DEFAULT_TENANT_ID, previous_id)
        if payload_kg <= 0 or payload_kg > 100:
            raise ValueError("payload_kg must be greater than 0 and no more than 100")
        if not 0 <= minimum_landing_reserve_percent <= 100:
            raise ValueError("minimum_landing_reserve_percent must be between 0 and 100")
        self._mission_counter += 1
        mission = Mission(
            mission_id=f"mission-{self._mission_counter:03d}",
            tenant_id=DEFAULT_TENANT_ID,
            fleet_id=DEFAULT_FLEET_ID,
            mission_type="DELIVERY_SIMULATION",
            origin=origin,
            destination=destination,
            payload_kg=payload_kg,
            minimum_landing_reserve_percent=minimum_landing_reserve_percent,
            state=MissionState.DRAFT,
            created_by=principal.actor_id,
            created_at=self.simulator.clock.now,
        )
        self.repository.save_mission(mission)
        self.repository.remember_idempotency(
            DEFAULT_TENANT_ID, f"mission:create:{idempotency_key}", mission.mission_id
        )
        self._record_audit(
            "mission.created",
            mission.mission_id,
            principal,
            "mission:create",
            {"mission": to_primitive(mission), "idempotency_key": idempotency_key},
            None,
            MissionState.DRAFT.value,
        )
        if record_action:
            self._actions.append(
                (
                    "create_mission",
                    (
                        principal,
                        origin,
                        destination,
                        payload_kg,
                        minimum_landing_reserve_percent,
                        idempotency_key,
                    ),
                )
            )
        return mission

    def evaluate_mission(
        self, principal: Principal, mission_id: str, *, record_action: bool = True
    ) -> EligibilityResult:
        authorize(principal, "mission:evaluate", DEFAULT_TENANT_ID)
        if mission_id in self._eligibility:
            return self._eligibility[mission_id]
        mission = self.repository.get_mission(DEFAULT_TENANT_ID, mission_id)
        previous = mission.state
        mission.state = transition_mission(mission.state, MissionState.VALIDATING)
        result = self.eligibility_policy.evaluate(
            mission, self.repository.list_drones(DEFAULT_TENANT_ID), self.simulator.clock.now
        )
        mission.state = transition_mission(
            mission.state,
            MissionState.APPROVED if result.selected_drone_id else MissionState.REJECTED,
        )
        mission.policy_version = result.policy_version
        mission.version += 1
        self.repository.save_mission(mission)
        self._eligibility[mission_id] = result
        self._record_audit(
            "safety.eligibility_evaluated",
            mission_id,
            principal,
            "mission:evaluate",
            {"eligibility": to_primitive(result)},
            previous.value,
            mission.state.value,
        )
        if record_action:
            self._actions.append(("evaluate_mission", (principal, mission_id)))
        return result

    def assign_mission(
        self,
        principal: Principal,
        mission_id: str,
        idempotency_key: str,
        *,
        record_action: bool = True,
    ) -> Mission:
        authorize(principal, "mission:assign", DEFAULT_TENANT_ID)
        replay_id = self.repository.resolve_idempotency(
            DEFAULT_TENANT_ID, f"mission:assign:{idempotency_key}"
        )
        if replay_id:
            return self.repository.get_mission(DEFAULT_TENANT_ID, replay_id)
        mission = self.repository.get_mission(DEFAULT_TENANT_ID, mission_id)
        result = self._eligibility.get(mission_id)
        if result is None or result.selected_drone_id is None:
            raise ApplicationConflictError("mission must have an eligible evaluated drone")
        previous = mission.state
        mission.state = transition_mission(mission.state, MissionState.ASSIGNING)
        mission.assigned_drone_id = result.selected_drone_id
        mission.state = transition_mission(mission.state, MissionState.ASSIGNED)
        mission.version += 1
        drone = self.repository.get_drone(DEFAULT_TENANT_ID, result.selected_drone_id)
        drone.current_mission_id = mission_id
        self.repository.save_drone(drone)
        self.repository.save_mission(mission)
        self.repository.remember_idempotency(
            DEFAULT_TENANT_ID, f"mission:assign:{idempotency_key}", mission_id
        )
        self._record_audit(
            "mission.assigned",
            mission_id,
            principal,
            "mission:assign",
            {
                "selected_drone_id": drone.drone_id,
                "scoring_explanation": to_primitive(result),
                "idempotency_key": idempotency_key,
            },
            previous.value,
            mission.state.value,
        )
        if record_action:
            self._actions.append(("assign_mission", (principal, mission_id, idempotency_key)))
        return mission

    def start_mission(
        self,
        principal: Principal,
        mission_id: str,
        idempotency_key: str,
        *,
        record_action: bool = True,
    ) -> Mission:
        authorize(principal, "mission:start", DEFAULT_TENANT_ID)
        replay_id = self.repository.resolve_idempotency(
            DEFAULT_TENANT_ID, f"mission:start:{idempotency_key}"
        )
        if replay_id:
            return self.repository.get_mission(DEFAULT_TENANT_ID, replay_id)
        mission = self.repository.get_mission(DEFAULT_TENANT_ID, mission_id)
        if mission.assigned_drone_id is None:
            raise ApplicationConflictError("mission has no assigned drone")
        drone = self.repository.get_drone(DEFAULT_TENANT_ID, mission.assigned_drone_id)
        mission_previous = mission.state
        mission.state = transition_mission(mission.state, MissionState.DISPATCHING)
        command = self._new_command(
            mission,
            drone,
            "START_MISSION",
            principal.actor_id,
            idempotency_key,
            "ALLOW",
        )
        for command_state in (
            CommandState.AUTHORIZED,
            CommandState.QUEUED,
            CommandState.PUBLISHED,
            CommandState.DELIVERED,
            CommandState.ACKNOWLEDGED,
            CommandState.EXECUTING,
        ):
            self._transition_command(command, command_state, principal.actor_id)
        command.acknowledgement = "simulator-adapter-accepted"
        for drone_state in (
            DroneState.PREFLIGHT,
            DroneState.READY,
            DroneState.ARMED,
            DroneState.TAKING_OFF,
            DroneState.IN_MISSION,
        ):
            old_state = drone.state
            drone.state = transition_drone(drone.state, drone_state)
            if drone_state is DroneState.IN_MISSION:
                drone.position = Position(
                    drone.position.latitude_deg, drone.position.longitude_deg, 30.0
                )
            self._record(
                "drone.state_changed",
                drone.drone_id,
                mission_id,
                {
                    "previous_state": old_state.value,
                    "new_state": drone_state.value,
                    "command_id": command.command_id,
                },
                producer="treta.simulator-adapter",
            )
        mission.state = transition_mission(mission.state, MissionState.ACTIVE)
        mission.version += 1
        command.observed_completion = "drone state observed as IN_MISSION"
        self._transition_command(command, CommandState.SUCCEEDED, "treta.control-plane")
        self.simulator.attach_mission(mission)
        self.repository.save_drone(drone)
        self.repository.save_mission(mission)
        self.repository.save_command(command)
        self.repository.remember_idempotency(
            DEFAULT_TENANT_ID, f"mission:start:{idempotency_key}", mission_id
        )
        self._record_audit(
            "mission.started",
            mission_id,
            principal,
            "mission:start",
            {"command_id": command.command_id, "idempotency_key": idempotency_key},
            mission_previous.value,
            mission.state.value,
        )
        if record_action:
            self._actions.append(("start_mission", (principal, mission_id, idempotency_key)))
        return mission

    def inject_failure(
        self,
        principal: Principal,
        *,
        drone_id: str,
        failure_type: FailureType,
        severity: str,
        multiplier: float,
        idempotency_key: str,
        record_action: bool = True,
    ) -> dict[str, Any]:
        authorize(principal, "simulation:control", DEFAULT_TENANT_ID)
        existing = self.repository.resolve_idempotency(
            DEFAULT_TENANT_ID, f"failure:inject:{idempotency_key}"
        )
        if existing:
            return {"failure_id": existing, "idempotent_replay": True}
        self.repository.get_drone(DEFAULT_TENANT_ID, drone_id)
        failure = self.simulator.inject_failure(
            drone_id=drone_id,
            failure_type=failure_type,
            severity=severity,
            multiplier=multiplier,
        )
        failure_id = f"failure-{drone_id}-{failure_type.value.lower()}"
        self.repository.remember_idempotency(
            DEFAULT_TENANT_ID, f"failure:inject:{idempotency_key}", failure_id
        )
        self._record_audit(
            "simulation.failure_injected",
            drone_id,
            principal,
            "simulation:control",
            {"failure_id": failure_id, "failure": to_primitive(failure)},
            None,
            "ACTIVE",
        )
        if record_action:
            self._actions.append(
                (
                    "inject_failure",
                    (principal, drone_id, failure_type, severity, multiplier, idempotency_key),
                )
            )
        return {"failure_id": failure_id, "idempotent_replay": False}

    def step(
        self, principal: Principal, seconds: int = 1, *, record_action: bool = True
    ) -> dict[str, Any]:
        authorize(principal, "simulation:control", DEFAULT_TENANT_ID)
        if not 1 <= seconds <= 60:
            raise ValueError("seconds must be between 1 and 60")
        for _ in range(seconds):
            result = self.simulator.step(self.repository.list_drones(DEFAULT_TENANT_ID), 1)
            for telemetry in result.telemetry:
                self.repository.save_drone(
                    self.repository.get_drone(DEFAULT_TENANT_ID, telemetry.drone_id)
                )
                self._record(
                    "telemetry.observed",
                    telemetry.drone_id,
                    f"tick-{self.simulator.clock.elapsed_seconds:06d}",
                    {"telemetry": to_primitive(telemetry)},
                    producer="treta.simulator",
                    occurred_at=telemetry.vehicle_event_time,
                )
            for trigger in result.safety_triggers:
                self._handle_local_safety_trigger(trigger)
            for drone_id in result.landed_drone_ids:
                self._handle_observed_landing(drone_id)
        if record_action:
            self._actions.append(("step", (principal, seconds)))
        return self.snapshot()

    def replay(self) -> ReplayResult:
        original_hashes = self.event_store.event_hashes(DEFAULT_TENANT_ID)
        replayed = ControlPlaneService(seed=self.seed)
        for action, arguments in self._actions:
            if action == "start_simulation":
                replayed.start_simulation(arguments[0])
            elif action == "pause_simulation":
                replayed.pause_simulation(arguments[0])
            elif action == "create_mission":
                replayed.create_mission(
                    arguments[0],
                    origin=arguments[1],
                    destination=arguments[2],
                    payload_kg=arguments[3],
                    minimum_landing_reserve_percent=arguments[4],
                    idempotency_key=arguments[5],
                )
            elif action == "evaluate_mission":
                replayed.evaluate_mission(arguments[0], arguments[1])
            elif action == "assign_mission":
                replayed.assign_mission(arguments[0], arguments[1], arguments[2])
            elif action == "start_mission":
                replayed.start_mission(arguments[0], arguments[1], arguments[2])
            elif action == "inject_failure":
                replayed.inject_failure(
                    arguments[0],
                    drone_id=arguments[1],
                    failure_type=arguments[2],
                    severity=arguments[3],
                    multiplier=arguments[4],
                    idempotency_key=arguments[5],
                )
            elif action == "step":
                replayed.step(arguments[0], arguments[1])
            else:  # pragma: no cover - defensive guard for future action versions
                raise RuntimeError(f"unknown replay action {action!r}")
        replay_hashes = replayed.event_store.event_hashes(DEFAULT_TENANT_ID)
        return ReplayResult(
            deterministic=original_hashes == replay_hashes,
            original_event_count=len(original_hashes),
            replay_event_count=len(replay_hashes),
            original_final_hash=original_hashes[-1] if original_hashes else None,
            replay_final_hash=replay_hashes[-1] if replay_hashes else None,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "environment": "local",
            "source": "simulated",
            "simulation": self.status(),
            "drones": to_primitive(self.repository.list_drones(DEFAULT_TENANT_ID)),
            "missions": to_primitive(self.repository.list_missions(DEFAULT_TENANT_ID)),
            "incidents": to_primitive(self.repository.list_incidents(DEFAULT_TENANT_ID)),
            "latest_telemetry": {
                drone.drone_id: to_primitive(self.simulator.latest_telemetry(drone.drone_id))
                for drone in self.repository.list_drones(DEFAULT_TENANT_ID)
            },
        }

    def status(self) -> dict[str, Any]:
        return {
            "running": self.simulator.running,
            "seed": self.seed,
            "elapsed_seconds": self.simulator.clock.elapsed_seconds,
            "simulation_time": to_primitive(self.simulator.clock.now),
            "drone_count": len(self.repository.list_drones(DEFAULT_TENANT_ID)),
        }

    def events(self, after_event_id: str | None = None, limit: int = 100) -> list[DomainEvent]:
        return self.event_store.list_events(
            DEFAULT_TENANT_ID, after_event_id=after_event_id, limit=limit
        )

    def eligibility(self, mission_id: str) -> EligibilityResult | None:
        return self._eligibility.get(mission_id)

    def _handle_local_safety_trigger(self, trigger: LocalSafetyTrigger) -> None:
        mission = self.repository.get_mission(DEFAULT_TENANT_ID, trigger.mission_id)
        drone = self.repository.get_drone(DEFAULT_TENANT_ID, trigger.drone_id)
        safety_event = self._record(
            "safety.rule_triggered",
            mission.mission_id,
            f"safety-{mission.mission_id}",
            {"decision": to_primitive(trigger.decision), "drone_id": drone.drone_id},
            producer="treta.vehicle-local-safety",
        )
        old_command_id = self._active_safety_command.get(mission.mission_id)
        if old_command_id is not None:
            old_command = self.repository.get_command(old_command_id)
            if old_command.state is CommandState.EXECUTING:
                old_command.failure_reason = "superseded by lower-reserve controlled landing"
                self._transition_command(
                    old_command, CommandState.FAILED, "treta.vehicle-local-safety"
                )
        command = self._new_command(
            mission,
            drone,
            trigger.action.value,
            "vehicle-local-safety",
            f"local-{mission.mission_id}-{trigger.action.value.lower()}",
            "ALLOW_LOCAL_SAFETY_FALLBACK",
        )
        for state in (
            CommandState.AUTHORIZED,
            CommandState.QUEUED,
            CommandState.PUBLISHED,
            CommandState.DELIVERED,
            CommandState.ACKNOWLEDGED,
            CommandState.EXECUTING,
        ):
            self._transition_command(command, state, "treta.vehicle-local-safety")
        command.acknowledgement = "vehicle-local-controller-accepted"
        self.repository.save_command(command)
        self._active_safety_command[mission.mission_id] = command.command_id
        previous = mission.state
        if trigger.action is SafetyAction.RETURN_TO_HOME:
            mission.state = transition_mission(mission.state, MissionState.RETURNING)
        else:
            mission.state = transition_mission(mission.state, MissionState.LANDING)
        mission.version += 1
        self.repository.save_mission(mission)
        incident = self._incident_for_trigger(trigger, safety_event.event_id, command.command_id)
        state_event = self._record(
            "mission.safety_fallback_started",
            mission.mission_id,
            f"safety-{mission.mission_id}",
            {
                "previous_state": previous.value,
                "new_state": mission.state.value,
                "vehicle_state": drone.state.value,
                "command_id": command.command_id,
                "incident_id": incident.incident_id,
            },
            producer="treta.control-plane-observer",
        )
        incident.timeline_event_ids.append(state_event.event_id)
        self.repository.save_incident(incident)

    def _handle_observed_landing(self, drone_id: str) -> None:
        missions = [
            mission
            for mission in self.repository.list_missions(DEFAULT_TENANT_ID)
            if mission.assigned_drone_id == drone_id and mission.state is MissionState.LANDING
        ]
        for mission in missions:
            previous = mission.state
            mission.state = transition_mission(mission.state, MissionState.ABORTED)
            mission.abort_reason = "vehicle-local landing-reserve safety fallback"
            mission.version += 1
            self.repository.save_mission(mission)
            command_id = self._active_safety_command.get(mission.mission_id)
            if command_id:
                command = self.repository.get_command(command_id)
                command.observed_completion = "drone state observed as LANDED"
                self._transition_command(
                    command, CommandState.SUCCEEDED, "treta.control-plane-observer"
                )
            event = self._record(
                "mission.aborted_after_safe_landing",
                mission.mission_id,
                f"safety-{mission.mission_id}",
                {
                    "previous_state": previous.value,
                    "new_state": mission.state.value,
                    "observed_drone_state": DroneState.LANDED.value,
                },
                producer="treta.control-plane-observer",
            )
            incident_id = self._incident_by_mission.get(mission.mission_id)
            if incident_id:
                incident = self.repository.get_incident(DEFAULT_TENANT_ID, incident_id)
                incident.timeline_event_ids.append(event.event_id)
                incident.resolution = "controlled landing observed; mission aborted"
                self.repository.save_incident(incident)

    def _incident_for_trigger(
        self, trigger: LocalSafetyTrigger, event_id: str, command_id: str
    ) -> Incident:
        existing_id = self._incident_by_mission.get(trigger.mission_id)
        if existing_id:
            incident = self.repository.get_incident(DEFAULT_TENANT_ID, existing_id)
            incident.active_policy_rule_ids.append(trigger.decision.rule_id)
            incident.command_ids.append(command_id)
            incident.timeline_event_ids.append(event_id)
            return incident
        self._incident_counter += 1
        incident = Incident(
            incident_id=f"incident-{self._incident_counter:03d}",
            tenant_id=DEFAULT_TENANT_ID,
            severity=trigger.decision.severity,
            drone_id=trigger.drone_id,
            mission_id=trigger.mission_id,
            detection_source="vehicle-local-safety",
            active_policy_rule_ids=[trigger.decision.rule_id],
            command_ids=[command_id],
            timeline_event_ids=[event_id],
            opened_at=self.simulator.clock.now,
        )
        self.repository.save_incident(incident)
        self._incident_by_mission[trigger.mission_id] = incident.incident_id
        return incident

    def _new_command(
        self,
        mission: Mission,
        drone: Drone,
        command_type: str,
        issuer: str,
        idempotency_key: str,
        policy_decision: str,
    ) -> Command:
        self._command_counter += 1
        command = Command(
            command_id=f"command-{self._command_counter:03d}",
            mission_id=mission.mission_id,
            drone_id=drone.drone_id,
            command_type=command_type,
            issuer=issuer,
            issued_at=self.simulator.clock.now,
            expires_at=self.simulator.clock.now + timedelta(minutes=5),
            sequence=self._command_counter,
            idempotency_key=idempotency_key,
            policy_decision=policy_decision,
        )
        self.repository.save_command(command)
        self._record(
            "command.created",
            command.command_id,
            mission.mission_id,
            {"command": to_primitive(command)},
            producer="treta.control-plane"
            if issuer != "vehicle-local-safety"
            else "treta.vehicle-local-safety",
        )
        return command

    def _transition_command(self, command: Command, target: CommandState, actor: str) -> None:
        previous = command.state
        command.state = transition_command(command.state, target)
        self.repository.save_command(command)
        self._record(
            "command.state_changed",
            command.command_id,
            command.mission_id,
            {
                "actor_id": actor,
                "previous_state": previous.value,
                "new_state": target.value,
                "acknowledgement": command.acknowledgement,
                "observed_completion": command.observed_completion,
                "failure_reason": command.failure_reason,
            },
            producer="treta.command-lifecycle",
        )

    def _record_audit(
        self,
        event_type: str,
        aggregate_id: str,
        principal: Principal,
        permission: str,
        inputs: dict[str, Any],
        previous_state: str | None,
        new_state: str,
    ) -> DomainEvent:
        return self._record(
            event_type,
            aggregate_id,
            f"request-{len(self.event_store.event_hashes(DEFAULT_TENANT_ID)) + 1:06d}",
            {
                "actor_id": principal.actor_id,
                "authentication_method": principal.authentication_method,
                "authorization_decision": "ALLOW",
                "permission": permission,
                "input_facts": inputs,
                "previous_state": previous_state,
                "new_state": new_state,
            },
            producer="treta.application",
        )

    def _record(
        self,
        event_type: str,
        aggregate_id: str,
        correlation_id: str,
        payload: dict[str, Any],
        *,
        producer: str,
        occurred_at: datetime | None = None,
    ) -> DomainEvent:
        timestamp = occurred_at or self.simulator.clock.now
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return self.event_store.append(
            EventDraft(
                event_type=event_type,
                aggregate_id=aggregate_id,
                tenant_id=DEFAULT_TENANT_ID,
                correlation_id=correlation_id,
                causation_id=None,
                trace_id=f"trace-{correlation_id}",
                occurred_at=timestamp,
                observed_at=self.simulator.clock.now,
                producer=producer,
                payload=payload,
            )
        )


def run_demo_scenario(scenario: Scenario) -> tuple[ControlPlaneService, ReplayResult]:
    if len(scenario.fleet) != 3:
        raise ValueError("the first vertical slice requires exactly three drones")
    service = ControlPlaneService(seed=scenario.seed)
    mission_planner = Principal(
        "planner-demo",
        DEFAULT_TENANT_ID,
        frozenset({"mission_planner"}),
        "local-development-header",
    )
    operator = Principal(
        "operator-demo",
        DEFAULT_TENANT_ID,
        frozenset({"operator"}),
        "local-development-header",
    )
    simulator_engineer = Principal(
        "simulator-demo",
        DEFAULT_TENANT_ID,
        frozenset({"simulator_engineer"}),
        "local-development-header",
    )
    service.start_simulation(simulator_engineer)
    mission = service.create_mission(
        mission_planner,
        origin=Position(
            scenario.mission.origin.latitude_deg, scenario.mission.origin.longitude_deg
        ),
        destination=Position(
            scenario.mission.destination.latitude_deg,
            scenario.mission.destination.longitude_deg,
        ),
        payload_kg=scenario.mission.payload_kg,
        minimum_landing_reserve_percent=scenario.mission.minimum_landing_reserve_percent,
        idempotency_key="demo-create",
    )
    result = service.evaluate_mission(mission_planner, mission.mission_id)
    if result.selected_drone_id is None:
        raise ApplicationConflictError("demo scenario has no eligible drone")
    service.assign_mission(mission_planner, mission.mission_id, "demo-assign")
    service.start_mission(operator, mission.mission_id, "demo-start")
    failure = scenario.failures[0]
    service.inject_failure(
        simulator_engineer,
        drone_id=result.selected_drone_id,
        failure_type=failure.type,
        severity=failure.severity,
        multiplier=failure.parameters.multiplier,
        idempotency_key="demo-failure",
    )
    service.step(simulator_engineer, 8)
    return service, service.replay()
