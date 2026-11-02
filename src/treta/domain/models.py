from __future__ import annotations

import dataclasses
import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class DroneState(StrEnum):
    IDLE = "IDLE"
    PREFLIGHT = "PREFLIGHT"
    READY = "READY"
    ARMED = "ARMED"
    TAKING_OFF = "TAKING_OFF"
    IN_MISSION = "IN_MISSION"
    HOLDING = "HOLDING"
    RETURNING_HOME = "RETURNING_HOME"
    LANDING = "LANDING"
    LANDED = "LANDED"
    MAINTENANCE_REQUIRED = "MAINTENANCE_REQUIRED"
    FAULTED = "FAULTED"
    EMERGENCY = "EMERGENCY"


class MissionState(StrEnum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    ASSIGNING = "ASSIGNING"
    ASSIGNED = "ASSIGNED"
    DISPATCHING = "DISPATCHING"
    ACTIVE = "ACTIVE"
    RETURNING = "RETURNING"
    LANDING = "LANDING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CommandState(StrEnum):
    CREATED = "CREATED"
    POLICY_REJECTED = "POLICY_REJECTED"
    AUTHORIZED = "AUTHORIZED"
    QUEUED = "QUEUED"
    PUBLISHED = "PUBLISHED"
    DELIVERED = "DELIVERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class HealthState(StrEnum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    DISCONNECTED = "DISCONNECTED"


class GpsQuality(StrEnum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"


class FailureType(StrEnum):
    RAPID_BATTERY_DRAIN = "RAPID_BATTERY_DRAIN"
    GPS_DEGRADATION = "GPS_DEGRADATION"
    TOTAL_LINK_LOSS = "TOTAL_LINK_LOSS"


class SafetyAction(StrEnum):
    NONE = "NONE"
    RETURN_TO_HOME = "RETURN_TO_HOME"
    CONTROLLED_LANDING = "CONTROLLED_LANDING"


@dataclasses.dataclass(frozen=True, slots=True)
class Position:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0

    def __post_init__(self) -> None:
        values = (self.latitude_deg, self.longitude_deg, self.altitude_m)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("position values must be finite")
        if not -90 <= self.latitude_deg <= 90:
            raise ValueError("latitude_deg must be between -90 and 90")
        if not -180 <= self.longitude_deg <= 180:
            raise ValueError("longitude_deg must be between -180 and 180")
        if self.altitude_m < 0:
            raise ValueError("altitude_m cannot be negative")


@dataclasses.dataclass(frozen=True, slots=True)
class CapabilityProfile:
    profile_id: str
    name: str
    maximum_payload_kg: float
    cruise_speed_mps: float
    nominal_range_m: float
    minimum_reserve_percent: float
    supported_mission_types: frozenset[str]
    supports_return_to_home: bool
    supports_controlled_landing: bool
    redundancy_score: float


@dataclasses.dataclass(slots=True)
class Telemetry:
    schema_version: int
    drone_id: str
    sequence: int
    vehicle_event_time: datetime
    platform_ingest_time: datetime
    position: Position
    ground_speed_mps: float
    battery_percent: float
    gps_quality: GpsQuality
    link_quality_percent: float
    flight_mode: str
    simulated: bool = True


@dataclasses.dataclass(slots=True)
class Drone:
    drone_id: str
    tenant_id: str
    fleet_id: str
    name: str
    vendor: str
    model: str
    profile: CapabilityProfile
    state: DroneState
    health: HealthState
    home: Position
    position: Position
    battery_percent: float
    gps_quality: GpsQuality
    link_quality_percent: float
    last_telemetry_sequence: int
    last_observed_at: datetime
    current_mission_id: str | None = None


@dataclasses.dataclass(slots=True)
class Mission:
    mission_id: str
    tenant_id: str
    fleet_id: str
    mission_type: str
    origin: Position
    destination: Position
    payload_kg: float
    minimum_landing_reserve_percent: float
    state: MissionState
    created_by: str
    created_at: datetime
    version: int = 1
    assigned_drone_id: str | None = None
    policy_version: str | None = None
    abort_reason: str | None = None


@dataclasses.dataclass(slots=True)
class Command:
    command_id: str
    mission_id: str
    drone_id: str
    command_type: str
    issuer: str
    issued_at: datetime
    expires_at: datetime
    sequence: int
    idempotency_key: str
    policy_decision: str
    state: CommandState = CommandState.CREATED
    acknowledgement: str | None = None
    observed_completion: str | None = None
    failure_reason: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision: str
    rule_id: str
    rule_version: str
    severity: str
    input_facts: dict[str, Any]
    reason: str
    recommended_action: str
    human_approval_required: bool
    evaluated_at: datetime


@dataclasses.dataclass(frozen=True, slots=True)
class DroneEligibility:
    drone_id: str
    eligible: bool
    score: float | None
    estimated_arrival_battery_percent: float | None
    reasons: tuple[PolicyDecision, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class EligibilityResult:
    mission_id: str
    policy_version: str
    drones: tuple[DroneEligibility, ...]
    selected_drone_id: str | None


@dataclasses.dataclass(slots=True)
class Incident:
    incident_id: str
    tenant_id: str
    severity: str
    drone_id: str
    mission_id: str
    detection_source: str
    active_policy_rule_ids: list[str]
    command_ids: list[str]
    timeline_event_ids: list[str]
    opened_at: datetime
    resolution: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class EventDraft:
    event_type: str
    aggregate_id: str
    tenant_id: str
    correlation_id: str
    causation_id: str | None
    trace_id: str
    occurred_at: datetime
    observed_at: datetime
    producer: str
    payload: dict[str, Any]


@dataclasses.dataclass(frozen=True, slots=True)
class DomainEvent:
    event_id: str
    event_type: str
    schema_version: int
    aggregate_id: str
    aggregate_version: int
    tenant_id: str
    correlation_id: str
    causation_id: str | None
    trace_id: str
    occurred_at: datetime
    observed_at: datetime
    producer: str
    payload: dict[str, Any]
    integrity: dict[str, str | None]


def to_primitive(value: Any) -> Any:
    """Convert domain values into canonical JSON-compatible values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_primitive(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("all datetimes must be timezone-aware UTC values")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        values = [to_primitive(item) for item in value]
        return sorted(values) if isinstance(value, set | frozenset) else values
    return value
