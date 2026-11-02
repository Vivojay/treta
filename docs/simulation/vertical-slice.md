# Deterministic vertical slice

The scenario `simulators/scenarios/rapid-battery-drain.yaml` uses only fictional synthetic coordinates. Seed 42 creates three profiles: a light delivery quad, a medium delivery hex, and a degraded legacy quad. Eligibility checks freshness, connectivity, state, mission compatibility, payload, GPS, and predicted reserve; the scoring explanation selects the safest eligible vehicle.

The mission command passes through created, authorized, queued, published, delivered, acknowledged, executing, and succeeded states. Success is recorded only after the simulator adapter reports `IN_MISSION`. Rapid drain then crosses the 25% reserve boundary. The simulated vehicle-local controller initiates return-to-home without a cloud round trip, escalates to controlled landing as energy falls, and the control plane records the observed landing, abort, safety decision, command, and incident timeline.

Replay constructs a fresh service with the same seed and re-applies the recorded external actions. Equality means the complete canonical event-hash sequence matches, including times and ordered aggregate versions.

The default API writes each canonical event through to a unique local JSONL
session file. This preserves evidence beyond process exit without making the
event format depend on a cloud provider. The simulator CLI and unit tests use
the in-memory event adapter so replay comparisons remain isolated and exact.

```text
python -m tools.treta simulate demo
```

This evidence is simulation-only and does not establish airworthiness.
