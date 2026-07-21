# Treta test strategy

The initial push tier emphasizes domain and safety invariants: unit tests for finite-state transitions and each safety decision branch, integration tests for authorization/idempotency/audit/API schemas, durable-event write failure tests, a deterministic scenario test with the failure path, and frontend tests for displayed decision semantics. Branch coverage is enabled and the initial aggregate gate is 90%; safety/state-machine modules target complete branch coverage.

The repository-owned interface is authoritative:

```text
python -m tools.treta format --check
python -m tools.treta lint
python -m tools.treta typecheck
python -m tools.treta test push
python -m tools.treta security
python -m tools.treta build
```

The first milestone also received an interactive browser pass of the complete
operator flow at desktop and 390×844 viewports, including a clean browser
console and overflow check. Pull-request expansion will automate that pass and
add Firebase rule tests, API fuzzing, container/IaC scans, and more cross-tenant
negative cases. Nightly tiers will add mutation testing, longer property/fuzz
testing, network/service chaos, load/soak testing, backup restoration,
dependency freshness, SBOM comparison, and external SITL where supported.
Evidence must name exact commands and results; flaky safety tests are never
silently retried.
