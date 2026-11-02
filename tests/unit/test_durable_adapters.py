from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from treta.adapters.durable import JsonlEventStore
from treta.domain.models import EventDraft


def event_draft() -> EventDraft:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return EventDraft(
        event_type="audit.persisted",
        aggregate_id="mission-001",
        tenant_id="tenant-synthetic",
        correlation_id="request-001",
        causation_id=None,
        trace_id="trace-001",
        occurred_at=now,
        observed_at=now,
        producer="treta.test",
        payload={"result": "recorded"},
    )


def _test_artifact_path() -> Path:
    root = Path(".treta") / "test-artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"events-{uuid4().hex}.jsonl"


def test_jsonl_event_store_persists_canonical_hash_chained_event() -> None:
    path = _test_artifact_path()
    try:
        store = JsonlEventStore(path)

        event = store.append(event_draft())
        persisted = json.loads(path.read_text(encoding="utf-8"))

        assert persisted["event_id"] == event.event_id
        assert persisted["integrity"]["event_hash"] == event.integrity["event_hash"]
        assert persisted["payload"] == {"result": "recorded"}
    finally:
        path.unlink(missing_ok=True)


def test_jsonl_event_store_refuses_to_overwrite_an_existing_session() -> None:
    path = _test_artifact_path()
    try:
        path.write_text("existing audit\n", encoding="utf-8")

        with pytest.raises(FileExistsError):
            JsonlEventStore(path)
    finally:
        path.unlink(missing_ok=True)


def test_jsonl_event_store_does_not_report_a_failed_write_as_appended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _test_artifact_path()
    try:
        store = JsonlEventStore(path)
        original_open = Path.open

        def fail_event_write(self: Path, *args: object, **kwargs: object) -> object:
            if self == path.resolve():
                raise OSError("simulated durable storage failure")
            return original_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", fail_event_write)
        with pytest.raises(OSError, match="simulated durable storage failure"):
            store.append(event_draft())

        assert store.event_hashes("tenant-synthetic") == ()
    finally:
        path.unlink(missing_ok=True)
