# Isolated executor boundary (step 2)

This is a root-only synthetic executor harness, not the GitHub check publisher. It has no socket, App key, merge endpoint, caller-provided prompt, test command, source path or verdict. Root chooses `reviewer` or `qa-security` and one fixed lane: `codex-canary`, `test-canary`, `auth-smoke`.

Install as root inside LXC 916 using `install-executor.sh`. It creates nologin system users `leaselab-review-exec` and `leaselab-qa-exec`, neither sharing a primary or supplementary group with the normal roles. The supervisor uses a root-owned Python venv with Pydantic 2.12.5; it must never use the Hermes-owned venv. Native Codex 0.154.0 is SHA-256 pinned at installation. The installer creates a static canary unit template but does not enable or start it.

The root supervisor creates immutable synthetic source, private per-role work and root-only evidence. A nonblocking per-role lock serializes jobs and auth bootstrap. Captured combined output is limited to 1 MiB and 180 seconds; timeout/output excess kills the invocation. Completed capture and metadata are mode 0400. A zero process exit code is **not** a QA or review PASS.

The Codex lane uses a minimal outer bubblewrap namespace with only system executables, CA/DNS files, read-only source, private scratch and its own auth home. Managed policy denies tool access to the entire auth home, disables tool networking and MCP servers, and allows only `never` approval/read-only sandbox. User config/rules, apps and plugins are disabled. Private PID and mount namespaces exclude normal role processes and service sockets. The generated `.codex/tmp/arg0` helper directory is masked read-only: the exact installed release otherwise adds an automatic read grant conflicting with full-home deny. Codex's native fallback works; its expected helper warning is retained in protected capture.

The test lane has no auth home, CA/DNS mounts or network namespace access, and only read-only synthetic source plus writable scratch. It does not currently run product tests or browser workloads.

## Same-role OAuth custody

**These are expiring smoke-test credentials, not unattended production authorization.** Long-lived service refresh/custody remains unimplemented; any future same-role refresh-capable migration must stop concurrent role refresh first.

`executor_auth.py ROLE` is root-only and reads only that role's existing `.codex/auth.json`, with size/owner/mode/link checks. It writes a protected independent snapshot using the installed release's official `chatgptAuthTokens` mode, containing the access token and an **empty refresh token**. It never writes the original role auth, copies across roles, exposes tokens in stdout or supplies a refresh provider. Original interactive role sessions remain the only refresh owners. Expiry/401 must block and require a fresh same-role snapshot; do not silently convert this to ordinary `chatgpt` mode or copy the original refresh token.

The source implementation is pinned to [Codex 0.154.0 auth manager](https://github.com/openai/codex/blob/36eab01061df3cde5f95ec20a526777b430091ba/codex-rs/login/src/auth/manager.rs) (`from_external_access_token`, loader and proactive-refresh logic) and [auth protocol mode](https://github.com/openai/codex/blob/36eab01061df3cde5f95ec20a526777b430091ba/codex-rs/protocol/src/auth.rs). These snapshots are credentials and must stay out of Git, logs and role prompts.

## Process/output nuance

Sandboxed tools can see their own nested Codex wrapper as PID 1. Its memory and auth-root alias are denied. In `codex exec`, wrapper stdout is the **same pipe as the tool's stdout** and writable as normal tool output; it is not the supervisor's JSON stream. A deliberate synthetic write appeared escaped inside `command_execution.aggregated_output`. Never trust such text, apparent JSON or a model's claimed PASS as an attestation. The synthetic canary accepts only denial or an identical tool output pipe/PTY. Separate normal role UIDs could neither signal the executor nor read its environment/private paths.

## Remaining work

No repository checkout/fetch protocol, controlled product-test recipe, trusted finding ledger, semantic verdict parser, cancellation endpoint, check publication, merge gate integration or preview-network policy is implemented here. The current immutable source is intentionally one synthetic fixture. Evidence must be bound to exact H/B/policy and evaluated by the separate trusted publisher before future checks can be posted. The normal mutable GitHub issue list is not an independent security boundary.

Rollback: stop only the `leaselab-publisher-canary@...` or explicitly created executor probe units, verify no executor-UID processes remain, then remove this unit template/code/runtime and the two executor users if no future publisher depends on them. Preserve needed root-only evidence separately. Never remove the original normal role homes or auth files. No original Hermes gateway/profile/SSH policy needs restoration.
