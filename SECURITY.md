# Security policy

Report suspected vulnerabilities privately to the repository owner. Do not open a public issue containing exploit details, credentials, customer data, or infrastructure details.

The local slice accepts development-only identity headers at the API trust boundary. It is not suitable for a public deployment. Free-staging must replace this adapter with validated Firebase ID tokens, tenant-scoped authorization, and tested Firestore rules. Mutations are default-deny, require explicit roles and idempotency keys, and are audited.

Never commit secrets. Use `.env.example` for names only. Rotate any credential believed to have entered history, preserve evidence, and follow the future secret-exposure runbook. Physical vehicle control is absent and must remain disabled by default.
