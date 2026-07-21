# Treta agent instructions

All coding agents must read these files before making changes:

1. `DESIGN.md`
2. `PROJECT_STATE.md`, if it exists
3. `ARCHITECTURE.md`, if it exists
4. relevant ADRs under `docs/adr/`, if they exist
5. documentation for the subsystem being modified, if it exists

If `PROJECT_STATE.md`, `ARCHITECTURE.md`, or `docs/handoff/current.yaml`
does not yet exist during repository bootstrap, create it as part of Phase 0
before substantial implementation begins.

## Source of truth

`DESIGN.md` is the authoritative product and engineering specification.

Do not modify it merely to make an incomplete implementation appear compliant.

When code, configuration, documentation, or infrastructure conflicts with
`DESIGN.md`:

1. stop expanding the conflicting implementation,
2. identify the conflicting requirement IDs where defined, or otherwise the exact `DESIGN.md` sections and acceptance criteria,
3. report the conflict,
4. propose compliant alternatives,
5. continue with unaffected work where possible.

A material requirement may be changed only through an explicit design-change
proposal approved by the repository owner.

## Requirement traceability

Use explicit `TRETA-*` requirement IDs wherever they exist. If a requirement has
not yet been assigned an ID, cite the exact `DESIGN.md` numbered section,
subsection, and applicable acceptance criterion. Do not invent requirement IDs.

Status reports must distinguish between:

* implemented,
* partially implemented,
* blocked,
* deferred by an approved design change, and
* not yet addressed.

## Working-document responsibilities

* `DESIGN.md`: authoritative intended design and constraints.
* `ARCHITECTURE.md`: architecture that currently exists.
* `PROJECT_STATE.md`: current progress, verification results, limitations, and next work.
* `ROADMAP.md`: future implementation sequence.
* `docs/adr/`: accepted architectural decisions and their consequences.
* `docs/handoff/current.yaml`: machine-readable handoff state.

Do not duplicate the complete design specification into other files.

## Before implementation

1. Inspect the repository.
2. Read the relevant requirements and record their explicit IDs where defined; otherwise record the exact `DESIGN.md` sections, subsections, and acceptance criteria.
3. Read current project state.
4. Identify affected modules and trust boundaries.
5. Define acceptance criteria.
6. Define tests before or alongside implementation.
7. Check whether an ADR is required.

## Engineering rules

* Prefer a working vertical slice over empty scaffolding.
* Keep domain logic independent of infrastructure providers.
* Preserve provider-replaceable ports and adapters.
* Keep physical-flight safety local to the vehicle or trusted edge.
* Do not add a mandatory cloud dependency to the flight-control loop.
* Do not introduce a new language, broker, database, cloud service, or framework without a documented justification.
* Do not add Kafka, Kubernetes, Redis, Elasticsearch, or another heavy component merely to appear enterprise-ready.
* Never silently swallow failures.
* Never represent a transmitted command as successfully executed without acknowledgement or observed confirmation.
* Use explicit state machines.
* Use UTC internally.
* Use explicit physical units.
* Treat all external input as untrusted.
* Do not commit secrets.
* Do not make the repository public.
* Do not weaken tests merely to obtain a green pipeline.

## Verification

For each implementation batch, run all applicable checks through the
repository-owned command interface rather than reproducing CI logic manually.

At minimum, report:

* commands executed,
* exact test results,
* scans executed,
* files changed,
* requirement IDs, numbered design sections, and acceptance criteria addressed,
* current runnable flow,
* known limitations,
* next highest-value task.

Do not claim that something works unless it was executed or otherwise
independently verified.

## Documentation

Documentation is part of the Definition of Done.

After each coherent batch, update:

* `PROJECT_STATE.md`,
* `ARCHITECTURE.md` when implemented architecture changed,
* relevant ADRs,
* subsystem documentation,
* `docs/handoff/current.yaml`,
* tests and schemas,
* `CHANGELOG.md` where appropriate.

## Design changes

When the current design appears incorrect, obsolete, unsafe, prohibitively
expensive, or internally contradictory, create a proposal under:

```text
docs/design-changes/
```

A proposal must contain:

* title,
* status,
* affected requirement IDs or exact `DESIGN.md` section references,
* current requirement,
* proposed change,
* motivation,
* alternatives,
* security impact,
* safety impact,
* migration impact,
* cost impact,
* compatibility impact,
* required documentation updates.

Do not implement a material divergence until it is approved.

## Prohibited conduct

Agents must not:

* expose repository content to an unapproved external service,
* install or authorize third-party GitHub applications without approval,
* change repository visibility,
* push directly to protected or release branches where protections exist,
* bypass failing safety or security tests,
* remove findings without explaining their disposition,
* enable physical-drone control by default,
* introduce weapon, targeting, or harmful-surveillance functionality,
* describe free staging as mission-critical production,
* modify the design specification merely to conceal incomplete work.
