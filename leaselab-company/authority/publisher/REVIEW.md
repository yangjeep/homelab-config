# Trusted Reviewer invocation — semantic records only

The existing root verification command now invokes the isolated Reviewer Codex lane after a supported docs syntax check succeeds. It records an independent semantic disposition; it still never creates a `passed` job, GitHub check, QA approval or merge.

## Control and provenance

The launcher reuses `executor_launch.command`: dedicated `leaselab-review-exec` UID, root-pinned Codex binary, private executor home, managed deny-read policy, read-only source and tool network denial. Provider network access belongs to the outer Codex orchestrator. The test lane remains auth-free and separately isolated.

Root supplies the fixed prompt, strict JSON schema and a read-only context containing exact repository, PR, H, B, policy digest, verified source identity, evidence job and changed document paths. No caller supplies a command, path, role, finding or PASS. The source/contract fixture entry is separately root-only and labels provenance `synthetic-fixture`; it cannot be mistaken for a GitHub candidate.

The read view excludes root `.codex` and `.agents` directories when present, replacing them with a root-owned inert directory. The full verified source identity remains unchanged; this is an explicit exclusion from the review view, and these paths cannot be changed under the supported docs recipe. Automatic project instruction loading is disabled with `project_doc_max_bytes=0` and empty fallback filenames. User configuration/rules, apps and plugins are disabled. Repository instructions and tool output remain untrusted data.

The installed Codex 0.154.0 CLI supports `--output-schema` and JSONL `--json` events. Official configuration schema at the pinned upstream revision documents the project instruction byte budget: [Codex config schema](https://github.com/openai/codex/blob/36eab01061df3cde5f95ec20a526777b430091ba/codex-rs/core/config.schema.json). The invocation uses the already protected same-role external-token auth snapshot; it does not copy, refresh, migrate or read original role auth. This snapshot remains expiring smoke/validation authorization, not unattended production authorization.

## Validation

Before inference, root runs a fixed canary through the same managed Codex sandbox. The model must also execute the exact fixed canary command, whose completed event, exit0 and strict true-valued result are required. The canary opens credential/synthetic paths only to verify access denial and never reads secret bytes. It checks source immutability, absent source config/skills, nonroot UID, absent broker/evidence and denied tool network.

Root captures bounded process output and exit status, then validates one complete Codex turn, unique completed item IDs, exact canary command, bounded schema-conforming final message and exact expected identity. Nested JSON inside tool stdout never becomes a top-level event. Findings must reference selected documents and valid line numbers. Every finding is classified security or correctness; security P2 is rejected, and the fixed prompt requires critical/release-blocking security P0 and other confirmed security at least P1, always as bugs.

The immutable `review-disposition.json` contains root-assigned Codex family/Reviewer role plus validated semantic content. Its digest is linked from the existing immutable verification report. The policy digest covers launcher/prompt, event validator, schema/models, canary, managed config and native binary pin. Final PR observation still binds completion to current H/B. Mechanical test success, semantic `clear`, and publication authority remain separate states.

Malformed output, missing canary, identity mismatch, tool-limit/process failure or missing auth fails closed. A valid `findings` or `inconclusive` record is retained as such and cannot become approval. A service-controlled model disposition can inform a future attestation once all independent QA, provenance and repository rules pass; this does not require pretending model judgment is infallible.

## Remaining work

- A trusted QA lane/recipe and independent finding dispositions suitable for required checks; the current docs syntax recipe is not complete functional/security QA.
- Application/marketing dependency materialization and offline test recipes remain unsupported.
- Trusted check publication, exact current policy/CI/security-ledger validation, Reviewer-only merge and SRE release integration remain disabled in this command.
- Long-lived same-role auth custody and automatic queue/recovery/retention are still required for unattended operation. Current policy namespace must be validated by any future publisher; underlying Jobs Identity still has `policy_version=1`.
