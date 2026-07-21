from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import TypeVar

from treta.domain.models import CommandState, DroneState, MissionState


class InvalidTransition(ValueError):
    """Raised when a lifecycle transition is not explicitly allowed."""


StateT = TypeVar("StateT", bound=StrEnum)


def transition(
    current: StateT, target: StateT, allowed: Mapping[StateT, frozenset[StateT]]
) -> StateT:
    if target not in allowed.get(current, frozenset()):
        raise InvalidTransition(f"invalid transition: {current.value} -> {target.value}")
    return target


DRONE_TRANSITIONS: dict[DroneState, frozenset[DroneState]] = {
    DroneState.IDLE: frozenset({DroneState.PREFLIGHT, DroneState.MAINTENANCE_REQUIRED}),
    DroneState.PREFLIGHT: frozenset({DroneState.READY, DroneState.FAULTED, DroneState.IDLE}),
    DroneState.READY: frozenset({DroneState.ARMED, DroneState.IDLE}),
    DroneState.ARMED: frozenset({DroneState.TAKING_OFF, DroneState.LANDING}),
    DroneState.TAKING_OFF: frozenset({DroneState.IN_MISSION, DroneState.LANDING}),
    DroneState.IN_MISSION: frozenset(
        {DroneState.HOLDING, DroneState.RETURNING_HOME, DroneState.LANDING, DroneState.EMERGENCY}
    ),
    DroneState.HOLDING: frozenset(
        {DroneState.IN_MISSION, DroneState.RETURNING_HOME, DroneState.LANDING}
    ),
    DroneState.RETURNING_HOME: frozenset({DroneState.LANDING, DroneState.EMERGENCY}),
    DroneState.LANDING: frozenset({DroneState.LANDED, DroneState.EMERGENCY}),
    DroneState.LANDED: frozenset({DroneState.IDLE, DroneState.MAINTENANCE_REQUIRED}),
    DroneState.MAINTENANCE_REQUIRED: frozenset({DroneState.IDLE}),
    DroneState.FAULTED: frozenset({DroneState.MAINTENANCE_REQUIRED, DroneState.EMERGENCY}),
    DroneState.EMERGENCY: frozenset({DroneState.LANDING, DroneState.LANDED}),
}

MISSION_TRANSITIONS: dict[MissionState, frozenset[MissionState]] = {
    MissionState.DRAFT: frozenset({MissionState.VALIDATING, MissionState.CANCELLED}),
    MissionState.VALIDATING: frozenset({MissionState.REJECTED, MissionState.APPROVED}),
    MissionState.REJECTED: frozenset({MissionState.DRAFT, MissionState.CANCELLED}),
    MissionState.APPROVED: frozenset({MissionState.ASSIGNING, MissionState.CANCELLED}),
    MissionState.ASSIGNING: frozenset({MissionState.ASSIGNED, MissionState.FAILED}),
    MissionState.ASSIGNED: frozenset({MissionState.DISPATCHING, MissionState.CANCELLED}),
    MissionState.DISPATCHING: frozenset({MissionState.ACTIVE, MissionState.FAILED}),
    MissionState.ACTIVE: frozenset(
        {MissionState.RETURNING, MissionState.LANDING, MissionState.COMPLETED, MissionState.ABORTED}
    ),
    MissionState.RETURNING: frozenset({MissionState.LANDING, MissionState.ABORTED}),
    MissionState.LANDING: frozenset({MissionState.COMPLETED, MissionState.ABORTED}),
}

COMMAND_TRANSITIONS: dict[CommandState, frozenset[CommandState]] = {
    CommandState.CREATED: frozenset({CommandState.AUTHORIZED, CommandState.POLICY_REJECTED}),
    CommandState.AUTHORIZED: frozenset({CommandState.QUEUED, CommandState.EXPIRED}),
    CommandState.QUEUED: frozenset({CommandState.PUBLISHED, CommandState.CANCELLED}),
    CommandState.PUBLISHED: frozenset(
        {CommandState.DELIVERED, CommandState.TIMED_OUT, CommandState.EXPIRED}
    ),
    CommandState.DELIVERED: frozenset({CommandState.ACKNOWLEDGED, CommandState.TIMED_OUT}),
    CommandState.ACKNOWLEDGED: frozenset({CommandState.EXECUTING, CommandState.FAILED}),
    CommandState.EXECUTING: frozenset({CommandState.SUCCEEDED, CommandState.FAILED}),
}


def transition_drone(current: DroneState, target: DroneState) -> DroneState:
    return transition(current, target, DRONE_TRANSITIONS)


def transition_mission(current: MissionState, target: MissionState) -> MissionState:
    return transition(current, target, MISSION_TRANSITIONS)


def transition_command(current: CommandState, target: CommandState) -> CommandState:
    return transition(current, target, COMMAND_TRANSITIONS)
