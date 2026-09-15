# Release eligibility contract

`evaluate(Request, Evidence, (Peer, Policy))` is a pure eligibility decision, not a production release controller. Only `yangjeep/leaselab` / `production` is supported. There is no command, SQL, database selector, role claim, credential, subprocess, network adapter, or execution endpoint.

The request is untrusted and must be parsed using `Request.model_validate_json`. Peer and policy must be injected independently: peer UID from the OS-authenticated transport, SRE UID/repository ID/workflow digest from administrator-owned configuration. Never accept any of these from the agent request. The production transport and authenticated evidence adapters are **not implemented**.

`Evidence` is an explicit trusted adapter contract. Pydantic proves shape, not provenance or SQL safety. A future controller must independently fetch and authenticate complete evidence for the fixed repository and exact candidate; it must never deserialize request-provided evidence and call that trusted. This includes:

- Reviewer-only merge provenance, PR head/base-to-merged-SHA association, current main/prod refs and ancestry.
- QA (App 4948555), independent review (App 4948588), CI (App 15368) evidence bound to the whole immutable candidate. CI run identity, completion and reviewed workflow digest must be verified at source. Existing head-only PR attestations cannot be silently treated as merged-build attestations.
- A content-addressed, available build candidate whose actual source and bytes match the merged SHA and build digest. The current product promotion workflow rebuilds from prod via Git integrations; it does not yet supply this complete build contract.
- A complete, ordered migration diff/inventory for `infra/d1/migrations/` at the candidate SHA, artifact bytes matching each digest, and the review of exactly that inventory. Changes to existing migrations, deleted migrations and unsupported classifications fail closed.
- Reviewer-established reversible additive semantics, reviewed rollback artifact digest, completed rollback tests, and release rollback evidence tied to current prod. A string classification or a hash supplied by an agent is not that evidence. No SQL keyword scanning occurs. Unknown/destructive/irreversible semantics require escalation outside this gate.
- Current release blockers and complete pagination, with ambiguous/missing evidence rejected by adapters.

An `Eligible` result is not a signed capability, credential, deployment receipt, or durable permission. Future execution must re-fetch evidence, serialize release operations, enforce the returned expected-prod-SHA precondition atomically, retain credentials outside all agent roles, revalidate artifact bytes, and reconcile partial migration/promotion failures. Those execution, replay, rollback, audit and cloud-controller responsibilities remain unimplemented. No services are enabled by this module.

The inspected product workflow is `.github/workflows/promote-prod.yml`: main validation followed by fast-forwarding prod and cutting a release, with cloud Git integrations triggered by prod. This module does not change that workflow or claim it now enforces SRE-only releases.
