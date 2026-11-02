# Operations

The only target in the first milestone is a local synthetic simulation. Free-staging has no acceptable mission-critical SLA, and production-reference/physical-pilot are disabled. Mission/entity projections are process-lifetime; their current RPO is the entire process session and RTO is a fresh deterministic replay. Canonical audit events are flushed and fsynced to a per-session JSONL file, but backup, restore, projection rehydration, signed checkpoints, and immutable retention are not yet implemented.

Use `/api/v1/health/live` for process liveness and `/api/v1/health/ready` for local readiness. Stop the direct development stack with Ctrl+C. Preserve `.treta/events/*.jsonl` as test evidence where needed. Provider outage runbooks will be added with those adapters; do not represent the current local slice as recoverable production infrastructure.
