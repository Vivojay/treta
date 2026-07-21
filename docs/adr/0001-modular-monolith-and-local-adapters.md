# ADR 0001: Modular monolith with deterministic local adapters

- Status: Accepted
- Date: 2026-07-21
- Decision owners: repository owner and principal implementation agent
- Design references: `DESIGN.md` §§4.1-4.4, 6, 9, 22-25, 31, 35-36, and 41-43; `TRETA-SAF-001`, `TRETA-CI-001`, `TRETA-DATA-001`

## Context

The repository has no existing implementation. The first milestone must exercise simulation, control-plane, safety, audit, API, and UI behaviour while preserving provider replaceability and avoiding a mandatory cloud or broker dependency.

## Decision

Build the first slice as a Python 3.12 modular monolith with clean module boundaries and explicit repository, event, identity, and future device-messaging ports. Use deterministic in-memory adapters in local and unit-test modes. Use a SvelteKit static frontend. Keep simulated vehicle-local safety inside the simulation/vehicle boundary and treat the application as supervisory.

The first slice records canonical hash-chained events. This is tamper-evident ordering, not immutable storage. Deterministic tests use the in-memory adapter. The default local API adds the write-through adapter selected in ADR 0002.

## Consequences

- The complete workflow can run without Firebase, MinIO, MQTT, NATS, or cloud credentials.
- Provider integrations can be added behind contracts and contract tests.
- Local runs are deterministic and cheap. Audit files survive process exit, but entity restart recovery is not yet implemented.
- SvelteKit and FastAPI are the selected MVP frameworks because they are specified by `DESIGN.md`; no new framework choice is introduced.
- Physical adapters remain absent and disabled.

## Alternatives considered

- Microservices were rejected for the initial slice because they add operational coupling before module boundaries are proven.
- Direct Firestore/Firebase dependencies were rejected for the domain because they violate provider-neutral boundaries and deterministic tests.
- A browser-only simulator was rejected because authorization, audit, and safety decisions must remain server-owned and testable.
