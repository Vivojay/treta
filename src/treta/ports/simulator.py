from __future__ import annotations

from datetime import datetime
from typing import Protocol

from treta.domain.models import (
    Drone,
    FailureType,
    Mission,
    PolicyDecision,
    SafetyAction,
    Telemetry,
)


class SimulationClockPort(Protocol):
    """Read-only simulated time; no wall-clock assumptions in the application."""

    @property
    def now(self) -> datetime: ...

    @property
    def elapsed_seconds(self) -> int: ...


class FailureRecordPort(Protocol):
    @property
    def drone_id(self) -> str: ...

    @property
    def failure_type(self) -> FailureType: ...

    @property
    def severity(self) -> str: ...

    @property
    def multiplier(self) -> float: ...

    @property
    def injected_at(self) -> datetime: ...


class SafetyTriggerPort(Protocol):
    @property
    def drone_id(self) -> str: ...

    @property
    def mission_id(self) -> str: ...

    @property
    def action(self) -> SafetyAction: ...

    @property
    def decision(self) -> PolicyDecision: ...


class SimulationTickPort(Protocol):
    @property
    def telemetry(self) -> tuple[Telemetry, ...]: ...

    @property
    def safety_triggers(self) -> tuple[SafetyTriggerPort, ...]: ...

    @property
    def landed_drone_ids(self) -> tuple[str, ...]: ...


class FleetSimulatorPort(Protocol):
    """Simulation-only backend contract, NOT the physical DroneAdapter contract.

    Implementations must preserve local safety semantics and represent observed
    telemetry honestly. In particular, this interface must not be used to fake
    transport acknowledgement or successful flight execution.
    """

    @property
    def seed(self) -> int: ...

    @property
    def clock(self) -> SimulationClockPort: ...

    @property
    def running(self) -> bool: ...

    def register_drones(self, drones: list[Drone]) -> None: ...

    def start(self) -> None: ...

    def pause(self) -> None: ...

    def attach_mission(self, mission: Mission) -> None: ...

    def latest_telemetry(self, drone_id: str) -> Telemetry: ...

    def inject_failure(
        self,
        *,
        drone_id: str,
        failure_type: FailureType,
        severity: str,
        multiplier: float,
    ) -> FailureRecordPort: ...

    def step(self, drones: list[Drone], seconds: int = 1) -> SimulationTickPort: ...
