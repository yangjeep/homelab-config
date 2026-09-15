# Reviewer merge authority

Implemented but **not deployed or live-authorized**. This narrow service retains the Reviewer App installation token and performs only squash merges into `yangjeep/leaselab` main. The ordinary Reviewer GitHub broker grant remains read-only for contents. No agent receives the merge token or App private key.

## Protocol and prerequisites

Linux Unix socket `/run/leaselab-merge/merge.sock`, mode 0660. A single JSON request followed by write EOF, maximum 256 bytes:

```json
{"pr":123,"head":"0123456789012345678901234567890123456789"}
```

Only `leaselab-reviewer` UID passes `SO_PEERCRED`. Client cannot specify role, repository, endpoint, token scope, merge method, or base. Root and the service UID are denied. The service resolves the dedicated `leaselab-merge` user and refuses to run under another UID. Single process lock plus serial socket loop; 120-second overall deadline, bounded reads, no redirects/proxy settings, no write retries. `leaselab-merge-pr` reads the JSON on stdin and supports `--help`.

Before enabling, provision all of:

1. Reviewer App **4948588**, installation **161807039**, repository `yangjeep/leaselab`, with Contents write accepted. Its private key is a **separate service-owned copy** at `/etc/leaselab-company/merge/reviewer.pem`, owner `leaselab-merge`, mode 0600, regular file, one link. No role access. Reuse the existing broker exchange code, not its key path or UID.
2. Root-owned `/etc/leaselab-company/merge/policy.json`, mode 0640, group `leaselab-merge`, configured from `policy.example.json`. Set the actual immutable repository ID, two reviewed ruleset IDs, and SHA-256 of the independently reviewed CI workflow bytes. Default disabled. Parent directory root-owned 0750, service group; traverse ACL on `/etc/leaselab-company` only.
3. Main quality ruleset: active, exact `refs/heads/main`, no exclusions, **no bypass actors**; PR required, stale-review dismissal, conversation resolution, deletion/force-push protection, linear history, strict checks, and the three existing Preview deployments. Main actor ruleset: update restriction with only Reviewer App Integration **4948588**, `pull_request` bypass. No quality bypass. Service re-reads both before merge.
4. Exactly these required check names/source Apps: `Workers Builds: leaselab-worker-preview` / **85455**; `Worker Regression Tests` / **15368**; `leaselab/qa-exact-sha` / **4948555**; `leaselab/independent-review` / **4948588**. Each must have exactly one successful completed check on the current head. Duplicate/ambiguous checks fail closed, including older reruns.
5. Trusted QA and independent-review publishers, inaccessible to coding workers. Both check `external_id` fields must be exactly `leaselab:v1:pr:<PR>:head:<40hex H>:base:<40hex B>`. This binds reviewed base as well as head. Each of these two check outputs must additionally have `output.summary` containing strictly this JSON schema (no Markdown wrapper):

   ```json
   {"pr":123,"head":"<40hex H>","base":"<40hex B>","resolved_issues":[779]}
   ```

   Use an empty list when none are resolved. A closing-linked security issue is exempt from the open-finding blocker only when **both** trusted publishers list it for current H and B. Other issues remain blocked. Old-SHA or old-base dispositions cannot carry forward. Publishers must independently validate actual execution/evidence and coding-family separation; this merge service does not manufacture or accept user-supplied PASS. Reviewer App also submits a native `APPROVED` review on H. No current changes-requested review can remain. Reviewer cannot be PR author or author/committer of any candidate commit.
6. Existing CI workflow **211331547**, `.github/workflows/deploy-preview-pr.yml`, must be independently audited then pinned by hash. Exactly one successful `pull_request` run at head H and attempt 1; regression check suite must match that run. Workflow bytes on both B and H must match the pinned trusted hash. No untrusted workflow change passes by keeping the same check name.
7. PR body contains 1–20 unique standalone `Closes #N`, `Fixes #N`, or `Resolves #N` lines and each referenced open issue has a body. Open P0/P1 or `security` issues block unless the issue is the current PR’s closing-linked contract and both trusted QA and review dispositions declare it resolved for this exact head/base. Founder-blocked/decision labels always block, even for an otherwise resolved issue. Lists at the 100-item boundary or paginated responses deny rather than silently ignoring evidence.

Current main base must be an ancestor of H, PR mergeability must be `clean`, and the final re-read must preserve H and B. GitHub's merge request includes the `sha` precondition and native strict rules are the last gate against base movement. Success response records H → squash commit SHA, then the PR mapping is checked. A timeout/disconnect after the PUT is **indeterminate**, not a proven failure; inspect the PR before retrying. No automatic retry.

## Install, recovery, validation

`install.sh` installs root-owned code and a separate Pydantic v2 venv, a dedicated service account/group, a client wrapper, and the systemd unit. Requires `uv`, `setfacl`, and installed broker code `/usr/local/libexec/leaselab-company/github-broker`. It does not fetch secrets, create policy, start or enable the service. Only Reviewer is a supplementary socket-group member. Secret files remain service-owned 0600 even though Reviewer can traverse the service config directory; policy is non-secret.

After independent parent review and provisioning, start explicitly with `systemctl enable --now leaselab-merge.service`. Rollback is `systemctl disable --now leaselab-merge.service`; preserve non-secret mapping logs, revoke service authority if abandoning rollout, and do not weaken GitHub rules. No rollback can unmerge a commit automatically.

Offline tests: `uv run --with pydantic --with pytest pytest leaselab-company/tests/test_merge_gate.py`. Linux tests executed only in `/tmp/leaselab-merge-offline-tests` on LXC 916. No service deployed, no credential read, no GitHub mutation performed. Local type check: `uv run --with basedpyright --with pydantic basedpyright -p leaselab-company/authority/merge/pyrightconfig.json`. Flat installed executable modules intentionally disable only implicit-relative-import diagnostics; typeCheckingMode remains all. Existing broker stdlib TLS/OpenSSL transport is reused to preserve its fixed-origin/no-redirect security contract.

Live positive/negative role tests, publishers, effective ruleset review, current production workflow risk remediation and merge evidence are still prerequisites. The controller alone cannot establish that upstream QA is genuine or that production promotion is safe.

## Primary API contracts checked

- [GitHub merge API: SHA precondition and merge result](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request)
- [Check runs API: source App, head SHA and conclusions](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference)
- [Rulesets API](https://docs.github.com/en/rest/repos/rules)
