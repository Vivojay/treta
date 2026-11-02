# Treta execution roadmap

This is the delivery sequence, not a replacement for the authoritative
`DESIGN.md` specification. `PROJECT_STATE.md` records verified implementation
and `docs/handoff/current.yaml` records machine-readable verification.

## Current baseline

- Target: `dev` at `2362ffa40ed5bece0a5791399fd29925c82e13ed`.
- Completed in the previously verified slice: three synthetic vehicles,
  deterministic telemetry, eligibility, assignment, local-reserve fallback,
  incident audit and replay (`DESIGN.md` sections 41-43).
- Unverified for this patch: post-apply CI and scenario execution.
- Not implemented: restart recovery, external SITL, physical adapters,
  production-ready identity, certified flight safety.

## Milestone M0: verify the baseline

**Deliverables:** reconcile the `dev` branch with handoff metadata; run all
repository-owned local checks and inspect issues; identify stale documents and
secrets; establish a clean, reproducible base for integration.

**Gate:** `python -m tools.treta ci` and `python -m tools.treta simulate demo`
pass in the target environment, or failures are recorded with commands and
logs. Preserve the original event-hash expectations; do not weaken safety
checks or tests to pass CI.

## Milestone M1: restart recovery and trustworthy state

**Design:** `DESIGN.md` sections 20, 38-39 and ADR 0002.

**Deliverables:** read/verify prior JSONL event chains, reject invalid or
partial records, restore mission/command projections and idempotency records,
and reconcile ambiguous in-flight commands conservatively. Introduce
transactional outbox and production storage only behind provider-neutral
ports. Add signed checkpoints after the recovery path is proven.

**Gate:** forced-stop/restart tests demonstrate that audit evidence and
projection state recover without asserting an unobserved action succeeded;
repeated recovery is idempotent; corrupted data fails closed.

## Milestone M2: replaceable simulation backend and vehicle contract

**Design:** `DESIGN.md` sections 4.2, 24-26, 41 (Phase 6), ADR 0003.

**This patch is only M2a:** inject a simulation backend via
`FleetSimulatorPort`, retain the original simulator by default, test the
boundary, and reject false command-dispatch and replay claims for external
implementations.

**M2b (not implemented):** define the separate asynchronous vendor-neutral
`DroneAdapter` contract, capability matrix, typed command receipts,
unsupported-operation outcomes, timeouts, lifecycle and explicit telemetry
provenance. Preserve vehicle-local flight safety. No physical control.

**Gate:** a second synthetic adapter passes the same simulation contract
suite; unsupported operations fail explicitly; simulated command delivery is
not treated as proof of real flight execution.

## Milestone M3: actual external software-in-the-loop

**Design:** `DESIGN.md` sections 26, 41 (Phase 6).

**Deliverables:** PX4 SITL/Gazebo headless integration and MAVSDK/MAVLink
receipts; run multiple simulated vehicles and verify telemetry source,
acknowledgement vs observed state, stale data, and local fallback. Follow
with ArduPilot SITL and contract tests. Use Linux CI or a supported remote
Linux runner, rather than require Docker on every workstation.

**Gate:** repeatable multi-vehicle SITL smoke in CI with failure evidence;
synthetic-only assumptions never appear as physical flight claims.

## Milestone M4: fleet operations and reliability

**Design:** `DESIGN.md` sections 27-28, 32-34, 39.

**Deliverables:** MapLibre operator map, drone detail, mission form, incident
triage; MQTT and NATS adapters only where transport semantics require them;
traces, bounded queues, backpressure, reconnect and outage testing.

**Gate:** a simulation operator can identify stale vehicles, inspect decisions
and incidents, and recover from interrupted communications without losing
audit trails or silently duplicating commands.

## Milestone M5: commercial inspection prototype

**Design:** `PRODUCT.md` with the simulation-only safety and privacy limits.

**Deliverables:** choose a narrow civilian vertical (for example, solar asset
inspection planning), interview operators before implementation, and build
one end-to-end virtual workflow with mission planning, supervision and
inspection-task reporting using synthetic evidence.

**Gate:** external users can complete a guided demo, explain the value and
indicate willingness to pilot or pay; do not assume product-market fit.

## Milestone M6: production reference and approval-gated hardware work

**Design:** `DESIGN.md` sections 19, 31, 36, 38-40, 41 (Phase 7),
`TRETA-SAF-001`.

**Deliverables:** security hardening, regional/edge deployment reference,
observability, disaster recovery, device identity and safety assurance plan.
No physical adapter or autonomous flight is activated without independent
hardware, regulatory, insurance and operational approval.

**Gate:** reviewed documentation and test evidence; no certification or
mission-critical SLA claim based on free staging or synthetic simulation.

## Implementation protocol

For each change set: define exact scope and impacted design sections, add
acceptance tests, implement one functioning vertical slice, run repository CI,
update `PROJECT_STATE.md`, relevant ADRs, `ARCHITECTURE.md`,
`docs/handoff/current.yaml`, and `CHANGELOG.md`, then report commands,
results, risks and the next smallest safe milestone. See `AGENTS.md`.
