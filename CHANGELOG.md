# Changelog

## Unreleased

- Added an injectable simulation-backend port (simulation only), seed consistency
  validation, fail-closed external dispatch/replay, and contract smoke tests.
- Established Phase 0 architecture, state, ADR, handoff, security, safety, test, and portability documents.
- Added provider-neutral CI entry points and thin GitHub/Jenkins orchestration.
- Added ignore policies, including `first_prompt.txt` in `.gitignore` and `.dockerignore`.
- Implemented the typed domain, explicit state machines, deterministic simulator,
  explainable safety policy, authorization, command acknowledgements, incident
  audit, replay, versioned FastAPI, and responsive SvelteKit operator flow.
- Added write-through per-session JSONL audit persistence with canonical SHA-256
  hash chaining and explicit write-failure rollback.
- Added 46 Python tests, 5 frontend tests, a 90% aggregate coverage gate,
  dependency audits, secret scanning, Bandit, and production builds.
