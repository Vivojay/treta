# Security finding dispositions

## 2026-07-21 local Bandit scan

Seven low-severity, high-confidence findings were reviewed before targeted suppression:

- `B311` in `simulation/engine.py`: accepted for deterministic synthetic telemetry noise. The pseudo-random generator is seeded from scenario data and is never used for identity, credentials, tokens, signatures, authorization, or other security decisions.
- `B404` and `B603` in the repository CLI and secret scanner: accepted for the provider-neutral command wrapper. Executables are resolved from the local environment, arguments are assembled from fixed command definitions and closed argparse choices, `shell=False` is retained, and no request, scenario, repository text, or network input becomes a shell command.

Each disposition is attached to the exact line with a rule-specific `nosec` marker. The markers do not suppress other Bandit rules. Reassess if these functions begin accepting untrusted command text or if simulation randomness gains a security purpose.

## 2026-07-21 dependency and credential scans

- The repository secret scanner found no credential patterns.
- Bandit reported zero active findings after the seven narrow dispositions above.
- pip-audit strict mode reported no known vulnerabilities in `uv.lock`'s environment.
- pnpm audit at low severity reported no known vulnerabilities in `pnpm-lock.yaml`.

Remote GitHub visibility is still an open verification item because neither
GitHub CLI nor an authenticated repository API is available on this workstation.
