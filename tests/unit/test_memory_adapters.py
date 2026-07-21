from __future__ import annotations

from datetime import UTC, datetime

import pytest

from treta.adapters.memory import (
    EntityNotFoundError,
    InMemoryControlPlaneRepository,
    InMemoryEventStore,
    LocalHeaderIdentityProvider,
    authorize,
)
from treta.domain.models import EventDraft
from treta.ports.interfaces import AuthenticationError, AuthorizationError, Principal


def draft(aggregate: str = "aggregate-1") -> EventDraft:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return EventDraft(
        "test.event",
        aggregate,
        "tenant-synthetic",
        "correlation-1",
        None,
        "trace-1",
        now,
        now,
        "test",
        {"value": 1},
    )


def test_event_store_hash_chain_versions_and_cursor() -> None:
    store = InMemoryEventStore()
    first = store.append(draft())
    second = store.append(draft())
    third = store.append(draft("aggregate-2"))
    assert first.aggregate_version == 1
    assert second.aggregate_version == 2
    assert third.aggregate_version == 1
    assert second.integrity["previous_event_hash"] == first.integrity["event_hash"]
    assert store.list_events("tenant-synthetic", after_event_id=first.event_id, limit=1) == [second]
    assert len(store.event_hashes("tenant-synthetic")) == 3
    with pytest.raises(EntityNotFoundError, match="cursor"):
        store.list_events("tenant-synthetic", after_event_id="missing")


def test_repository_not_found_paths_and_idempotency() -> None:
    repository = InMemoryControlPlaneRepository()
    with pytest.raises(EntityNotFoundError, match="drone"):
        repository.get_drone("tenant", "missing")
    with pytest.raises(EntityNotFoundError, match="mission"):
        repository.get_mission("tenant", "missing")
    with pytest.raises(EntityNotFoundError, match="command"):
        repository.get_command("missing")
    assert repository.resolve_idempotency("tenant", "key") is None
    repository.remember_idempotency("tenant", "key", "result")
    assert repository.resolve_idempotency("tenant", "key") == "result"
    assert repository.list_drones("tenant") == []
    assert repository.list_missions("tenant") == []
    assert repository.list_incidents("tenant") == []


def test_local_identity_is_explicit_and_default_deny() -> None:
    identity = LocalHeaderIdentityProvider()
    with pytest.raises(AuthenticationError):
        identity.authenticate(None, None, None)
    with pytest.raises(AuthorizationError, match="unknown"):
        identity.authenticate("actor", "tenant-synthetic", "root")
    viewer = identity.authenticate("actor", "tenant-synthetic", "viewer")
    authorize(viewer, "read", "tenant-synthetic")
    with pytest.raises(AuthorizationError, match="missing permission"):
        authorize(viewer, "mission:start", "tenant-synthetic")
    with pytest.raises(AuthorizationError, match="cross-tenant"):
        authorize(viewer, "read", "another-tenant")
    administrator = Principal(
        "admin", "tenant-synthetic", frozenset({"tenant_administrator"}), "test"
    )
    authorize(administrator, "simulation:control", "tenant-synthetic")
