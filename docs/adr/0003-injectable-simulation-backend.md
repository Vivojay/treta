# ADR 0003: Injectable simulation backend boundary

- Status: Proposed (owner approval required before merging)
- Date: 2026-11-02
- Design references: `DESIGN.md` sections 4.2, 24-26, 41 (Phases 1 and 6), and 46; `TRETA-SAF-001`

## Context

`ControlPlaneService` directly instantiated `DeterministicFleetSimulator`. That
precluded substitution in integration tests and would tightly couple future
simulator integrations to the application service. The existing simulator and
synthetic replay must remain stable. An external PX4/ArduPilot adapter has not
been tested or implemented.

## Decision

Introduce a structural `FleetSimulatorPort` with read-only clock, telemetry,
mission attachment, deterministic stepping, and failure-injection operations.
Permit injection through `ControlPlaneService(simulator=...)`, retaining the
built-in deterministic simulator by default. Reject an incompatible seed.
Keep replay restricted to the exact built-in deterministic implementation;
replay of other backends needs a separate reproducibility/evidence design.

This is a **simulation-only** seam, not the asynchronous `DroneAdapter`
interface required by `DESIGN.md` section 24. It does not model MAVLink command
receipts, vendor capabilities, timeouts, or physical safety certification.
Those require separately designed adapter contracts and external SITL evidence.

## Consequences

- The original local demo keeps its default simulator and event schema.
- Alternate simulated backends can be injected without changing basic service
  construction, allowing contract tests before PX4/Gazebo integration. Mission
  dispatch remains restricted to the built-in simulator until real adapter
  command receipts and observed-state transitions have been validated.
- A replacement must provide the simulator contract and cannot be passed off as
  a replayable built-in backend without an explicit deterministic replay design.
- Existing synthetic command-acknowledgement shortcuts remain **synthetic**;
  they must be replaced by explicit protocol receipts and observed telemetry
  for external SITL. No physical pilot is enabled by this ADR.
- Deployment, trust boundaries and the `TRETA-SAF-001` local-safety requirement
  are unchanged.

## Deferred work

1. Durable projection and command/outbox recovery after restart.
2. Real `DroneAdapter` protocol, capability matrix, command receipts and adapter
   contract tests (`DESIGN.md` section 24).
3. PX4/Gazebo and ArduPilot SITL integration with real acknowledgements and
   observed state (`DESIGN.md` section 26 and Phase 6).
4. Independent safety review and hardware validation before physical use.
