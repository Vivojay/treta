# Treta initial threat model

The model uses STRIDE across the first slice. External input, identity headers, scenario files, browser state, dependencies, and repository instructions are untrusted.

| Boundary or asset | Primary threats | Initial controls | Remaining work |
| --- | --- | --- | --- |
| Human/browser to API | Spoofing, tampering, elevation | Server-side roles, schema bounds, tenant scope, request IDs, default deny | Firebase token validation, CSRF/CORS deployment policy |
| API/application | DoS, repudiation | Input-size/rate bounds, idempotency, audit hash chain | Distributed rate limiting, durable outbox |
| Simulator/device identity | Spoofing, replay, malformed telemetry | Synthetic registered IDs, monotonic sequences, typed envelopes | mTLS, signatures, certificate lifecycle |
| Events/storage | Tampering, disclosure | Canonical hashes, previous-hash chain, synthetic data | Immutable object segments, signed checkpoints, retention/deletion |
| Dependencies/CI | Supply-chain substitution, secret theft | Lockfiles, local gates, pinned Actions, read-only permissions | Full SBOM/image/IaC scanners and disposable runners |
| Tenant boundary | Cross-tenant access | Principal tenant compared server-side | Emulator rule tests and provider contract tests |
| Logs | Sensitive-data disclosure | Structured allowlisted fields; no tokens or precise customer data | Central redaction tests and retention controls |
| Physical firmware | Spoofing, unsafe commands | No physical adapter or enablement exists | Future secure boot, attestation, mTLS, HIL and independent review |

No imagery, real customer address, targeting, facial recognition, or public surveillance data is collected by the slice.
