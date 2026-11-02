# Contributing to Treta

Read `DESIGN.md`, `AGENTS.md`, `PROJECT_STATE.md`, `ARCHITECTURE.md`, relevant ADRs, and subsystem documentation before changing code. Cite stable `TRETA-*` requirements or exact numbered design sections. Use UTC and explicit physical units, treat input as untrusted, preserve provider ports, keep safety local, and never add physical control by default.

Bootstrap with `python -m tools.treta bootstrap`, then run `python -m tools.treta ci` and `python -m tools.treta security`. Do not weaken a test or design requirement to obtain a green result. Update state, architecture/ADR where applicable, changelog, tests, docs, and `docs/handoff/current.yaml` with every coherent batch.
