from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from treta.domain.models import DroneState, Position, to_primitive


@pytest.mark.parametrize(
    ("latitude", "longitude", "altitude", "message"),
    [
        (float("nan"), 0, 0, "finite"),
        (91, 0, 0, "latitude"),
        (0, 181, 0, "longitude"),
        (0, 0, -1, "altitude"),
    ],
)
def test_position_rejects_invalid_units(latitude, longitude, altitude, message) -> None:
    with pytest.raises(ValueError, match=message):
        Position(latitude, longitude, altitude)


def test_to_primitive_preserves_explicit_types_and_utc() -> None:
    @dataclass
    class Sample:
        state: DroneState
        at: datetime
        values: frozenset[str]

    result = to_primitive(
        Sample(DroneState.IDLE, datetime(2026, 1, 1, tzinfo=UTC), frozenset({"b", "a"}))
    )
    assert result == {"state": "IDLE", "at": "2026-01-01T00:00:00Z", "values": ["a", "b"]}


def test_to_primitive_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        to_primitive(datetime(2026, 1, 1))
