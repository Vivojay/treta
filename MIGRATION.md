# Provider migration map

Treta domain and safety code depends on ports rather than provider SDKs. Planned substitutions are: Cloudflare Pages to S3/CloudFront or another static host; Render to ECS/EKS/another container runtime; Firebase Auth to Cognito/Keycloak/OIDC; Firestore to DynamoDB/PostgreSQL/another repository; R2/MinIO to S3-compatible storage; Mosquitto to AWS IoT Core or another MQTT broker; in-memory/NATS event buses to another implementation; NATS to Kafka only for measured durable analytics needs; GitHub Actions to Jenkins through the same command interface; and Compose to Kubernetes only in an approved production-reference phase.

Every migration requires behavioural contract tests, data export/import validation, rollback criteria, security review, cost review, and updated ADR/architecture/handoff documents. No Phase 7 infrastructure is deployed by this repository state.
