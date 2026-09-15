# Privileged policy observer — prepared, disabled

This service is an offline implementation proposal. The GitHub App has not been authorized or provisioned by this module. `config.example.json` has `enabled:false` and null App/installation IDs; the unit has no install target. Existing merge authority is unchanged. Do not enable or install the service until the separate Administration-write grant and deployment have been explicitly authorized.

## Why this credential is privileged

GitHub returns `bypass_actors` only to a requester with ruleset write access. The proposed separate **LeaseLab Policy Observer** App therefore requests exactly repository **Administration: write** and **Metadata: read**, installed only on `yangjeep/leaselab`. It has no Contents or Pull requests permission. [GitHub rules API](https://docs.github.com/en/rest/repos/rules?apiVersion=2026-03-10#get-a-repository-ruleset).

This is not a read-only credential. Compromise of its private key or service UID could permit administrative repository changes outside the exposed service protocol. The code's GET allowlist constrains callers, not an attacker already controlling the credential-bearing process. That custody risk is the new authorization being proposed; it is not covered by the existing role grants.

## Exact service surface

An authenticated Unix client half-closes after sending JSON `{"nonce":"<64 lowercase hex characters>"}` (maximum 256 bytes). There is no caller-supplied URL, repository, ruleset ID, path, role, verdict, command, SQL or permission field. The production handler authenticates Linux `SO_PEERCRED` against the configured machine's `leaselab-merge` account before parsing or minting. Wrong peers may receive an error or an immediate connection reset; neither reaches the reader.

For every accepted request, the service mints its own short-lived installation token and performs fresh reads from `api.github.com`:

- `GET /repos/yangjeep/leaselab/rulesets?includes_parents=true&per_page=100&page=N` for bounded pages 1–4.
- `GET /repos/yangjeep/leaselab/rulesets/ID?includes_parents=true` for positive IDs ≤2147483647 obtained only from that inventory.

It never follows arbitrary links. Pagination destinations must match the next constructed fixed-origin page exactly. Malformed links, duplicates, more than 200 rulesets, a full page without next metadata, excess pages, hidden/missing bypass data, unknown required schema values, redirects, non-200 reads, compressed responses and oversized evidence fail closed. A 120-second total deadline bounds each request; individual network reads have 10-second timeouts. The complete response is capped at 2 MB.

The only non-GET network operation is the existing broker primitive's fixed App installation-token mint. The reused primitive restricts the repository and verifies exact returned token permissions. Its only subprocess is fixed OpenSSL JWT signing, not execution of product code. No private key, JWT or installation token is returned or logged. No generic proxy or cloud operation exists.

Response: nonce, repository, observation time, and complete ruleset detail objects, retaining additional GitHub semantic fields. It is **observed policy**, not an approval verdict or signed capability. Missing bypass actors never become an empty list.

## Custody and deployment contract

Future installation must create `leaselab-policy-observer` as a separate noninteractive system UID with `/usr/sbin/nologin`, distinct from root and every role, including `leaselab-merge`. Install code/interpreter/dependencies in root-owned directories not writable by any role. The shared installed `github-broker/{policy,upstream}.py` dependency must be the reviewed root-owned version, service-readable; no writable workspace/import fallback is supported. The existing standard-library TLS transport is retained to preserve its no-proxy/no-redirect boundary and avoid an unrelated networking dependency.

- Configuration: `/etc/leaselab-company/policy-observer/config.json`, root-owned, mode 0640, single regular file; observer group read only.
- Key: `/etc/leaselab-company/policy-observer/observer.pem`, owned by the observer UID, mode 0600, single regular file; parent directories root-owned and non-writable by agent roles. The shared minter checks file ownership/mode/link count and uses `O_NOFOLLOW`.
- Socket: `/run/leaselab-policy-observer/observer.sock`, observer-owned, mode 0660. The runtime directory is observer-owned mode 0750. Only the trusted merge service gets supplementary membership in the observer socket group; agents do not. Group membership gives no access to the 0600 key.
- The merge-side client, still unimplemented, must connect only to that protected path, verify the server's kernel UID, check response framing/size/schema, and compare the echoed nonce to a freshly generated request nonce. It must then validate actual policy contents and exact expected IDs; the observer does not decide merge eligibility.

No installation script, privileged account, key, App grant, socket or live daemon was created as part of this proposal. The unit file is reviewable configuration only.

## Limits that remain

Reads across pages/details are not an atomic GitHub snapshot. Detail identity and baseline fields are checked against inventory, but configuration can still change during/after observation. No timestamp inference or duplicate reads remove the observation-to-mutation race. GitHub's strict platform rules and the merge service's complete policy validation remain indispensable. Parent/org rulesets whose bypass fields this App cannot see cause denial; repository Administration write must not be claimed to confer organization administration.

The observer does not implement merge-client integration, token revocation, deployment provisioning, remote App setup or durable audit storage. Fresh successful responses may be used only as immediate evidence, never cached as permanent bypass authorization. No live credential or GitHub observation test was performed.
