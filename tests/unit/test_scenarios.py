from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from treta.simulation.scenarios import load_scenario, parse_scenario_text

SCENARIO = Path("simulators/scenarios/rapid-battery-drain.yaml")


def test_demo_scenario_is_valid_and_synthetic() -> None:
    scenario = load_scenario(SCENARIO)
    assert scenario.schema_version == 1
    assert scenario.data_classification == "synthetic"
    assert len(scenario.fleet) == 3


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("[]", "root must be a mapping"),
        ("schema_version: 2\n", "schema_version"),
        (
            "\n".join(
                (
                    "schema_version: 1",
                    "name: x",
                    "seed: 1",
                    "simulation_rate: 1",
                    "data_classification: real",
                    "fleet: []",
                    "mission: {}",
                    "failures: []",
                    "expected: []",
                )
            ),
            "synthetic",
        ),
    ],
)
def test_invalid_scenario_fails_clearly(replacement, message) -> None:
    with pytest.raises((ValueError, ValidationError), match=message):
        parse_scenario_text(replacement)
