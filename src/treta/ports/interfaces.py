from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from treta.domain.models import Command, DomainEvent, Drone, EventDraft, Incident, Mission


@dataclass(frozen=True, slots=True)
class Principal:
    actor_id: str
    tenant_id: str
    roles: frozenset[str]
    authentication_method: str


class AuthorizationError(PermissionError):
    """The authenticated principal is not allowed to perform an operation."""


class AuthenticationError(AuthorizationError):
    """No valid external identity was supplied."""


class IdentityProviderPort(Protocol):
    def authenticate(
        self, actor_id: str | None, tenant_id: str | None, role: str | None
    ) -> Principal:
        """Validate an external identity representation."""


class ControlPlaneRepositoryPort(Protocol):
    def list_drones(self, tenant_id: str) -> list[Drone]: ...

    def get_drone(self, tenant_id: str, drone_id: str) -> Drone: ...

    def save_drone(self, drone: Drone) -> None: ...

    def list_missions(self, tenant_id: str) -> list[Mission]: ...

    def get_mission(self, tenant_id: str, mission_id: str) -> Mission: ...

    def save_mission(self, mission: Mission) -> None: ...

    def save_command(self, command: Command) -> None: ...

    def get_command(self, command_id: str) -> Command: ...

    def list_incidents(self, tenant_id: str) -> list[Incident]: ...

    def get_incident(self, tenant_id: str, incident_id: str) -> Incident: ...

    def save_incident(self, incident: Incident) -> None: ...

    def remember_idempotency(self, tenant_id: str, key: str, result_id: str) -> None: ...

    def resolve_idempotency(self, tenant_id: str, key: str) -> str | None: ...


class EventStorePort(Protocol):
    def append(self, draft: EventDraft) -> DomainEvent: ...

    def list_events(
        self, tenant_id: str, *, after_event_id: str | None = None, limit: int = 100
    ) -> list[DomainEvent]: ...

    def event_hashes(self, tenant_id: str) -> tuple[str, ...]: ...
