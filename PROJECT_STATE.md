# Treta project state

Last updated: 2026-07-21

## Current milestone

The Phase 0 foundation and first complete local, deterministic, simulation-only
vertical slice are implemented. `DESIGN.md` remains the authoritative intended
design; this file records only verified implemented reality.

## Status by requirement and design section

| Requirement or section | Status | Evidence or limitation |
| --- | --- | --- |
| `TRETA-SEC-001` | Partially implemented | Source, secret, and ignore policy are implemented and scans are clean. The configured Git remote exists, but private visibility was not independently verified because GitHub CLI/authenticated API tooling is unavailable. |
| `TRETA-SAF-001` | Partially implemented | The deterministic vehicle-local reserve controller performs RTH and controlled landing without API/cloud availability. No physical adapter, HIL evidence, certification, or trusted-edge deployment exists. |
| `TRETA-CI-001` | Partially implemented | Format, lint, type, test, security, simulation, and build logic execute through `python -m tools.treta`; GitHub Actions and Jenkins are thin wrappers. Release/publish logic is not yet implemented. |
| `TRETA-DATA-001` | Implemented | Raw high-rate telemetry remains in the simulator/event path and is never written continuously to Firestore. Firestore rules default deny. |
| `DESIGN.md §20` | Partially implemented | Events use canonical serialization, ordered aggregate versions, and a previous-hash SHA-256 chain, with per-session JSONL write-through. Signed checkpoint manifests and immutable remote evidence storage remain future work. |
| `DESIGN.md §41 — Phase 0` | Partially implemented | Required repository, CLI, environments, frontend, Compose, emulator, CI, security, ADR, and handoff artifacts exist. Direct local startup is verified; container startup is blocked from verification because Docker is unavailable. |
| `DESIGN.md §41 — Phase 1` | Implemented | Seeded clock, three profiles, telemetry, movement, energy use, mission execution, three failure types, recording, and replay are tested. |
| `DESIGN.md §41 — Phase 2` | Implemented for the first slice | Fleet/mission repositories, registration, safety evaluation, assignment, command lifecycle, projection, timeline, and incidents are present. |
| `DESIGN.md §41 — Phase 3` | Partially implemented | Fleet, freshness, eligibility, active mission, failure flow, incident timeline, replay, and disclaimers are visible. Map, detailed vehicle view, and general mission form are not yet addressed. |
| `DESIGN.md §42` | Implemented | The complete authorized synthetic delivery flow, rapid-drain failure, local fallback, audit, incident, and deterministic replay run through API and browser. |
| `DESIGN.md §43` | Implemented | Every listed first-milestone acceptance criterion has executed or has automated evidence, including one-command startup, durable local event output, UI flow, tests, security scans, and documentation. |
| `DESIGN.md §41 — Phases 4–7` | Not yet addressed as functional milestones | Compose/configuration examples exist for later adapters, but messaging, observability, external SITL, and production-reference implementations have not begun. |

No requirement is deferred by an approved design change. No design-change
proposal was required for this batch.

## Implemented runnable flow

1. `python -m tools.treta dev core` launches FastAPI and SvelteKit.
2. Three heterogeneous synthetic drones and fresh telemetry appear.
3. An authorized planner creates and evaluates a delivery mission; deterministic
   reasons explain eligible and rejected drones.
4. The safest eligible drone is assigned and an operator starts the mission.
5. The command records created, authorized, queued, published, delivered,
   acknowledged, executing, and observed-success states.
6. Rapid battery drain triggers vehicle-local RTH, then controlled landing.
7. The control plane observes the safe landing, aborts the mission, records an
   incident, and persists the hash-chained audit to `.treta/events/*.jsonl`.
8. Replay with seed 42 produces the same 67-event hash sequence.

## Verification record

- `python -m tools.treta bootstrap`: passed with locked uv and frozen pnpm locks.
- `python -m tools.treta ci`: passed repository-owned format, Ruff, ESLint,
  strict mypy, Svelte diagnostics, Python/frontend tests, scenario, secret scan,
  Bandit, compile, and production frontend build.
- Python: 46 passed; aggregate branch coverage 96.83% (90% gate).
- Frontend: 5 passed; statements/branches/functions/lines 100%.
- Scenario: final mission `ABORTED`, 1 incident, 2 safety triggers, 67 events;
  original and replay SHA-256 final hash
  `98be4d96430fcfd197b4341b7e249fa220a17e9623662313c7123f8b0f547369`.
- `python -m tools.treta security`: secret scan clean; Bandit 0 findings;
  pip-audit and pnpm audit reported no known vulnerabilities.
- Browser: desktop flow passed with a clean console; 390×844 viewport has no
  document-level overflow; final UI showed `Stopped`, `Aborted`, 1 incident,
  and `Deterministic` replay.
- One-command smoke: API reported ready and the web server listened on 5173;
  only the test process/ports were stopped afterward.
- Local JSONL audit: write-through, no-overwrite, and write-failure rollback are
  tested; the one-command smoke emitted three persisted registration events.
- Last verified base commit: `00d738408dcdb9eac315be23b3b077f31d78adb0` on
  `main`; all milestone changes are currently uncommitted.

## Known failures and limitations

- Docker is not installed, so Compose build/config/runtime, Firebase emulator,
  MinIO, Mosquitto, NATS, and observability containers were not executed.
- GitHub repository visibility was not independently verified; `gh` is absent.
- Mission/control-plane recovery across restart is not implemented. JSONL files
  preserve audit evidence, but the service does not rebuild projections from
  prior sessions.
- The local header identity adapter must never be exposed to an untrusted network.
- The simulator is not aerodynamic SITL, HIL, certified, or physical evidence.
- Free-staging is not deployed and has no production SLA claim.

## Pending migrations

- Local header identity to verified Firebase/OIDC tokens in free-staging.
- In-memory entity projections to a Firestore-compatible repository adapter.
- Local JSONL audit to durable outbox, immutable object segments, and signed
  checkpoint manifests.
- Synthetic vehicle adapter to external SITL contract tests before any physical
  pilot discussion.

## Next highest-value tasks

1. Add Firebase identity/repository adapters and emulator contract tests.
2. Add durable replay/projection restoration and signed event checkpoints.
3. Implement the map, detailed vehicle view, and general mission form.
4. Run Compose/container/IaC checks on a workstation with Docker.
