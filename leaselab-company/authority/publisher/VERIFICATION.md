# Integrated verification command — bounded Step 4

This is an executable source/test and isolated Reviewer integration, not an attestation publisher. It never creates a `passed` manifest, GitHub check or merge. Existing Codex auth and App credentials are unchanged.

## Command

After Steps 2/3, root runs `install-verification.sh` from the configuration checkout. Root creates `/var/lib/leaselab-publisher/verification-requests/<64-hex-id>` containing only `{"pr":759,"head":"3abe9b2a4851aa20ea03051fe039a8b0b8c1308f"}`, owner root, mode 0400, parent 0700. Then:

```sh
systemctl start leaselab-verification@<64-hex-id>.service
```

No service is enabled, no socket is installed, and roles cannot invoke this root entry. The unit caps memory at 1 GiB, CPU at one core, tasks at 96 and total start time at 300 seconds. Individual observation, materialization and test commands also have bounded time/output capture. Exit 2 means failed verification; exit 3 means blocked/stale, including successful mechanical tests and semantic review awaiting trusted publication. Consequently systemd reports these nonzero results as failed units; the immutable manifest/evidence provides the precise state.

The entry observes fixed-repository PR head/base through the dedicated source-fetch UID, begins the existing manifest, invokes/reuses verified source materialization, selects a root-owned recipe, runs the auth-free executor, invokes the isolated Reviewer for supported successful tests, and re-observes H/B before completion. Closed historical PRs are accepted for diagnostic verification only; a future publishing gate must require an open eligible PR.

## Supported recipe

`docs-text-v1` accepts at most 100 changed, non-executable Markdown files under `docs/` or `.agent/WORKLOG/`. Deletions, unchanged candidates, application files, package/workflow/configuration changes and agent instruction changes are unsupported. Exact Git tree identities determine changes. The fixed stdlib runner checks bounded UTF-8 text, final newline, absence of NUL/conflict markers. It does not assess documentation correctness, security or issue-contract satisfaction.

The test namespace has immutable head/base source, writable scratch and only the fixed root-owned script/policy. It has no repository Git configuration/hooks, no OAuth/App credentials, no broker socket and no external network. It does not install or execute repository dependencies. The runner itself verifies UID, secret/socket path absence, external network denial and source write denial before inspecting documents. Tool stdout is untrusted evidence; capture status is supervisor-owned, and successful exit still produces BLOCKED.

## Durability and binding

A digest of the fixed supervisor, observer, recipe, test and Reviewer policy artifacts selects the private manifest-store namespace. Evidence identity binds the existing job ID plus that policy digest. Immutable `verification.json` records initial identity, final observation, policy/runner digests, supervisor exit and output digest. A final changed H/B becomes STALE through the existing Jobs transition. Materialization/observation/execution errors after start become FAILED. On the next root invocation, a previously RUNNING job is finalized FAILED as interrupted; it is not silently rerun. Terminal jobs deduplicate. If the machine dies, a RUNNING record remains until that next invocation; there is no watchdog yet. Disk failure can also prevent durable finalization and must be treated as infrastructure failure.

Policy changes create a new namespace and preserve old evidence. The underlying Identity still has `policy_version=1`: a future publisher MUST validate the current namespace/digest or extend Identity with the policy digest. It must never inspect an old store by H/B alone. These diagnostic manifests cannot authorize publication.

## Remaining integration

1. The isolated Codex read executor is integrated with a service-owned prompt/schema and exact provenance; see REVIEW.md. Next, connect a trusted QA disposition and policy checks before any check publication. A semantic clear record alone does not authorize approval.
2. Add trusted QA recipes for application changes. Repository inspection found pnpm 10.29.3, Node >=22, native `better-sqlite3`/`esbuild` build allowances, Vitest/Playwright and potentially mutating deployment/migration scripts. Marketing builds remain unsupported until a separately verified dependency materialization/cache, hook policy and offline test recipe are implemented. Never run install/build scripts with source-fetch or OAuth credentials present.
3. Bind current policy into future check provenance, add trusted finding disposition and required-policy observations, then publish only from the service identity. Model judgment need not be infallible, but caller PASS/tool text alone cannot authorize a check.
4. Add bounded automatic queue/recovery/retention and supported long-lived same-role Codex credential custody. Expiring Step 2 smoke auth is not unattended production auth.

No App checks, merge, release, GitHub writes or auth migration occur in Step 4.
