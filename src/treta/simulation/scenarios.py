from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from treta.domain.models import FailureType


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScenarioPosition(StrictModel):
    latitude_deg: float = Field(ge=-90, le=90)
    longitude_deg: float = Field(ge=-180, le=180)


class ScenarioDrone(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    profile: str = Field(min_length=1, max_length=64)
    initial_battery_percent: float = Field(ge=0, le=100)


class ScenarioMission(StrictModel):
    type: str = Field(min_length=1, max_length=64)
    origin: ScenarioPosition
    destination: ScenarioPosition
    payload_kg: float = Field(gt=0, le=100)
    minimum_landing_reserve_percent: float = Field(ge=0, le=100)


class FailureParameters(StrictModel):
    multiplier: float = Field(gt=0, le=100)


class ScenarioFailure(StrictModel):
    at_simulation_seconds: int = Field(ge=0, le=86_400)
    target: str
    type: FailureType
    severity: str
    parameters: FailureParameters

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        if value not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise ValueError("unsupported failure severity")
        return value


class ScenarioExpected(StrictModel):
    event: str | None = None
    rule_id: str | None = None
    command: str | None = None
    final_mission_state: str | None = None


class Scenario(StrictModel):
    schema_version: int
    name: str
    seed: int
    simulation_rate: float = Field(gt=0, le=100)
    data_classification: str
    fleet: tuple[ScenarioDrone, ...]
    mission: ScenarioMission
    failures: tuple[ScenarioFailure, ...]
    expected: tuple[ScenarioExpected, ...]

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported scenario schema_version")
        return value

    @field_validator("data_classification")
    @classmethod
    def validate_classification(cls, value: str) -> str:
        if value != "synthetic":
            raise ValueError("MVP scenarios must declare synthetic data")
        return value

    @field_validator("fleet")
    @classmethod
    def validate_fleet(cls, value: tuple[ScenarioDrone, ...]) -> tuple[ScenarioDrone, ...]:
        ids = [drone.id for drone in value]
        if len(ids) != len(set(ids)):
            raise ValueError("scenario drone IDs must be unique")
        known_profiles = {
            "light-delivery-quad",
            "medium-delivery-hex",
            "legacy-degraded-quad",
        }
        unknown = sorted({drone.profile for drone in value} - known_profiles)
        if unknown:
            raise ValueError(f"unknown vehicle profiles: {', '.join(unknown)}")
        return value


def load_scenario(path: Path) -> Scenario:
    return parse_scenario_text(path.read_text(encoding="utf-8"))


def parse_scenario_text(text: str) -> Scenario:
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError("scenario root must be a mapping")
    return Scenario.model_validate(raw)
