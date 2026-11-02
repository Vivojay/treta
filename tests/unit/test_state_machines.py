from __future__ import annotations

import pytest

from treta.domain.models import CommandState, DroneState, MissionState
from treta.domain.state_machines import (
    COMMAND_TRANSITIONS,
    DRONE_TRANSITIONS,
    MISSION_TRANSITIONS,
    InvalidTransition,
    transition_command,
    transition_drone,
    transition_mission,
)


@pytest.mark.parametrize(
    ("transitions", "transition_function"),
    [
        (DRONE_TRANSITIONS, transition_drone),
        (MISSION_TRANSITIONS, transition_mission),
        (COMMAND_TRANSITIONS, transition_command),
    ],
)
def test_every_declared_transition_is_accepted(transitions, transition_function) -> None:
    for current, targets in transitions.items():
        for target in targets:
            assert transition_function(current, target) is target


@pytest.mark.parametrize(
    ("current", "target", "transition_function"),
    [
        (DroneState.IDLE, DroneState.IN_MISSION, transition_drone),
        (MissionState.DRAFT, MissionState.ACTIVE, transition_mission),
        (CommandState.CREATED, CommandState.SUCCEEDED, transition_command),
    ],
)
def test_invalid_transition_fails_explicitly(current, target, transition_function) -> None:
    with pytest.raises(InvalidTransition, match=f"{current.value} -> {target.value}"):
        transition_function(current, target)
