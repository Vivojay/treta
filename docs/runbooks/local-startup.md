# Runbook: local startup

1. Run `python -m tools.treta doctor` and resolve missing Python/uv/Node tooling.
2. Run `python -m tools.treta bootstrap`.
3. Run `python -m tools.treta dev core`.
4. Verify `http://127.0.0.1:8000/api/v1/health/ready` reports simulation-only readiness.
5. Open `http://127.0.0.1:5173` and run the scenario.
6. Stop with Ctrl+C. Local mission/entity projections are lost; canonical audit events remain under `.treta/events/`. Use deterministic replay or rerun the scenario to rebuild active state.

In constrained tool environments where the pinned pnpm executable is not on
`PATH`, set `TRETA_PNPM` to its absolute path. If a command shim cannot locate
Node, set `TRETA_NODE` to the Node executable and `TRETA_PNPM_CLI` to pnpm's
`pnpm.cjs` entry point instead.

If port 8000 or 5173 is occupied, stop the conflicting local process; the CLI does not kill unrelated processes. Do not expose the development identity adapter to an untrusted network.
