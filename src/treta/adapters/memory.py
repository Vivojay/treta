from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from treta.domain.models import (
    Command,
    DomainEvent,
    Drone,
    EventDraft,
    Incident,
    Mission,
    to_primitive,
)
from treta.ports.interfaces import AuthenticationError, AuthorizationError, Principal


class EntityNotFoundError(LookupError):
    """Requested tenant-scoped entity does not exist."""


class InMemoryControlPlaneRepository:
    def __init__(self) -> None:
        self.drones: dict[str, Drone] = {}
        self.missions: dict[str, Mission] = {}
        self.commands: dict[str, Command] = {}
        self.incidents: dict[str, Incident] = {}
        self.idempotency: dict[tuple[str, str], str] = {}

    def list_drones(self, tenant_id: str) -> list[Drone]:
        return sorted(
            (drone for drone in self.drones.values() if drone.tenant_id == tenant_id),
            key=lambda item: item.drone_id,
        )

    def get_drone(self, tenant_id: str, drone_id: str) -> Drone:
        drone = self.drones.get(drone_id)
        if drone is None or drone.tenant_id != tenant_id:
            raise EntityNotFoundError(f"drone {drone_id!r} was not found")
        return drone

    def save_drone(self, drone: Drone) -> None:
        self.drones[drone.drone_id] = drone

    def list_missions(self, tenant_id: str) -> list[Mission]:
        return sorted(
            (mission for mission in self.missions.values() if mission.tenant_id == tenant_id),
            key=lambda item: item.mission_id,
        )

    def get_mission(self, tenant_id: str, mission_id: str) -> Mission:
        mission = self.missions.get(mission_id)
        if mission is None or mission.tenant_id != tenant_id:
            raise EntityNotFoundError(f"mission {mission_id!r} was not found")
        return mission

    def save_mission(self, mission: Mission) -> None:
        self.missions[mission.mission_id] = mission

    def save_command(self, command: Command) -> None:
        self.commands[command.command_id] = command

    def get_command(self, command_id: str) -> Command:
        try:
            return self.commands[command_id]
        except KeyError as error:
            raise EntityNotFoundError(f"command {command_id!r} was not found") from error

    def list_incidents(self, tenant_id: str) -> list[Incident]:
        return sorted(
            (incident for incident in self.incidents.values() if incident.tenant_id == tenant_id),
            key=lambda item: item.incident_id,
        )

    def get_incident(self, tenant_id: str, incident_id: str) -> Incident:
        incident = self.incidents.get(incident_id)
        if incident is None or incident.tenant_id != tenant_id:
            raise EntityNotFoundError(f"incident {incident_id!r} was not found")
        return incident

    def save_incident(self, incident: Incident) -> None:
        self.incidents[incident.incident_id] = incident

    def remember_idempotency(self, tenant_id: str, key: str, result_id: str) -> None:
        self.idempotency[(tenant_id, key)] = result_id

    def resolve_idempotency(self, tenant_id: str, key: str) -> str | None:
        return self.idempotency.get((tenant_id, key))


class InMemoryEventStore:
    """Process-lifetime, canonical, hash-chained event storage."""

    def __init__(self) -> None:
        self._events: list[DomainEvent] = []
        self._aggregate_versions: defaultdict[str, int] = defaultdict(int)

    def append(self, draft: EventDraft) -> DomainEvent:
        event_number = len(self._events) + 1
        event_id = f"evt-{event_number:06d}"
        self._aggregate_versions[draft.aggregate_id] += 1
        previous_hash = self._events[-1].integrity["event_hash"] if self._events else None
        content = {
            "event_id": event_id,
            "event_type": draft.event_type,
            "schema_version": 1,
            "aggregate_id": draft.aggregate_id,
            "aggregate_version": self._aggregate_versions[draft.aggregate_id],
            "tenant_id": draft.tenant_id,
            "correlation_id": draft.correlation_id,
            "causation_id": draft.causation_id,
            "trace_id": draft.trace_id,
            "occurred_at": to_primitive(draft.occurred_at),
            "observed_at": to_primitive(draft.observed_at),
            "producer": draft.producer,
            "payload": to_primitive(draft.payload),
            "previous_event_hash": previous_hash,
        }
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        event = DomainEvent(
            event_id=event_id,
            event_type=draft.event_type,
            schema_version=1,
            aggregate_id=draft.aggregate_id,
            aggregate_version=self._aggregate_versions[draft.aggregate_id],
            tenant_id=draft.tenant_id,
            correlation_id=draft.correlation_id,
            causation_id=draft.causation_id,
            trace_id=draft.trace_id,
            occurred_at=draft.occurred_at,
            observed_at=draft.observed_at,
            producer=draft.producer,
            payload=to_primitive(draft.payload),
            integrity={
                "algorithm": "sha256",
                "canonicalization": "treta-json-v1",
                "previous_event_hash": previous_hash,
                "event_hash": event_hash,
            },
        )
        self._events.append(event)
        return event

    def list_events(
        self, tenant_id: str, *, after_event_id: str | None = None, limit: int = 100
    ) -> list[DomainEvent]:
        tenant_events = [event for event in self._events if event.tenant_id == tenant_id]
        if after_event_id is not None:
            indexes = [
                index
                for index, event in enumerate(tenant_events)
                if event.event_id == after_event_id
            ]
            if not indexes:
                raise EntityNotFoundError(f"event cursor {after_event_id!r} was not found")
            tenant_events = tenant_events[indexes[0] + 1 :]
        return tenant_events[:limit]

    def event_hashes(self, tenant_id: str) -> tuple[str, ...]:
        return tuple(
            str(event.integrity["event_hash"])
            for event in self._events
            if event.tenant_id == tenant_id
        )


class LocalHeaderIdentityProvider:
    """Development-only identity adapter; never enable this in free-staging."""

    allowed_roles = frozenset(
        {
            "viewer",
            "operator",
            "mission_planner",
            "simulator_engineer",
            "safety_officer",
            "tenant_administrator",
        }
    )

    def authenticate(
        self, actor_id: str | None, tenant_id: str | None, role: str | None
    ) -> Principal:
        if not actor_id or not tenant_id or not role:
            raise AuthenticationError("explicit local actor, tenant, and role headers are required")
        if role not in self.allowed_roles:
            raise AuthorizationError("unknown or disabled role")
        return Principal(
            actor_id=actor_id,
            tenant_id=tenant_id,
            roles=frozenset({role}),
            authentication_method="local-development-header",
        )


PERMISSIONS: dict[str, frozenset[str]] = {
    "read": LocalHeaderIdentityProvider.allowed_roles,
    "mission:create": frozenset({"mission_planner", "tenant_administrator"}),
    "mission:evaluate": frozenset(
        {"operator", "mission_planner", "safety_officer", "tenant_administrator"}
    ),
    "mission:assign": frozenset({"operator", "mission_planner", "tenant_administrator"}),
    "mission:start": frozenset({"operator", "tenant_administrator"}),
    "simulation:control": frozenset({"simulator_engineer", "tenant_administrator"}),
}


def authorize(principal: Principal, permission: str, tenant_id: str) -> None:
    if principal.tenant_id != tenant_id:
        raise AuthorizationError("cross-tenant operation denied")
    allowed = PERMISSIONS.get(permission, frozenset())
    if principal.roles.isdisjoint(allowed):
        raise AuthorizationError(f"missing permission: {permission}")
