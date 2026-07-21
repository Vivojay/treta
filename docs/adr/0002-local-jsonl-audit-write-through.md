# ADR 0002: Local JSONL audit write-through

- Status: Accepted
- Date: 2026-07-21
- Decision owners: repository owner and principal implementation agent
- Design references: `DESIGN.md §20`; `DESIGN.md §43 — events are persisted`

## Context

The first slice's canonical hash chain originally existed only in process
memory. That was deterministic and queryable but did not satisfy the first
milestone's explicit event-persistence acceptance criterion. Introducing a
cloud database or broker would violate the local-first vertical-slice boundary.

## Decision

Keep the provider-neutral event-store port and in-memory query projection. For
the default local API, synchronously append each completed canonical event to a
new per-session UTF-8 JSONL file under `.treta/events/`. Flush and `fsync` every
append. If the file write fails, roll back the in-memory append and propagate
the failure; never report the action as durably recorded. Refuse to open an
existing session path so prior evidence cannot be overwritten accidentally.

In the read-only API container, write the same session files under
`/tmp/treta/events`. Free-staging must replace this adapter rather than depend on
ephemeral container storage.

## Consequences

- Local audit evidence survives API process exit and can be inspected directly.
- Simulation/replay hashes remain deterministic because the JSONL sink does not
  alter canonical event contents.
- Mission/entity projections still reset on restart; current sessions are not
  rehydrated from earlier JSONL files.
- Files are append-only by application convention, not mathematically immutable
  or protected from a machine administrator.
- The free-staging migration still requires an outbox, durable object/event
  storage, retention, signed checkpoints, and restoration tests.

## Alternatives considered

- Keeping process-only events was rejected because it contradicted the exact
  `DESIGN.md §43` acceptance criterion.
- Loading and continuing a previous session was deferred because projection
  recovery, schema migration, and partially written tail handling require a
  separately tested recovery milestone.
- Adding Firestore, MinIO, NATS, or another mandatory service was rejected for
  the direct local slice because the event port must remain replaceable and the
  one-command profile must work without Docker or cloud credentials.
