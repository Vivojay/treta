from __future__ import annotations

import pytest

from treta.application.control_plane import DEFAULT_TENANT_ID, ControlPlaneService
from treta.ports.interfaces import Principal


@pytest.fixture
def service() -> ControlPlaneService:
    return ControlPlaneService(seed=42)


@pytest.fixture
def viewer() -> Principal:
    return Principal("viewer-test", DEFAULT_TENANT_ID, frozenset({"viewer"}), "test")


@pytest.fixture
def planner() -> Principal:
    return Principal("planner-test", DEFAULT_TENANT_ID, frozenset({"mission_planner"}), "test")


@pytest.fixture
def operator() -> Principal:
    return Principal("operator-test", DEFAULT_TENANT_ID, frozenset({"operator"}), "test")


@pytest.fixture
def simulator_engineer() -> Principal:
    return Principal("simulator-test", DEFAULT_TENANT_ID, frozenset({"simulator_engineer"}), "test")
