from __future__ import annotations

import json
import os
from pathlib import Path

from treta.adapters.memory import InMemoryEventStore
from treta.domain.models import DomainEvent, EventDraft, to_primitive


class JsonlEventStore(InMemoryEventStore):
    """Write-through local audit store with an in-memory query projection."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=False)

    def append(self, draft: EventDraft) -> DomainEvent:
        event = super().append(draft)
        serialized = json.dumps(
            to_primitive(event), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        try:
            with self.path.open("a", encoding="utf-8", newline="\n") as event_file:
                event_file.write(serialized + "\n")
                event_file.flush()
                os.fsync(event_file.fileno())
        except OSError:
            self._events.pop()
            self._aggregate_versions[draft.aggregate_id] -= 1
            raise
        return event
