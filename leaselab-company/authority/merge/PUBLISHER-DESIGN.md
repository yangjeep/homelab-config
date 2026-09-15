# Trusted QA and independent-review publishers

Read-only assessment, 2026-09-15. Only this document was changed in this assessment. No credentials were read, no inference/job was launched, and no service/App/ruleset was changed. This is an implementation design, not an attestation of deployment.

## Decision

Use two instances of one small trusted job supervisor/publisher implementation: QA and independent review. Each accepts a request to **run** verification, never a caller-provided decision or evidence path. Each owns its execution, captures results outside agent-writable storage, validates deterministic requirements, then publishes through its existing App. Keep existing Codex role authorization, but move automatic gate execution into dedicated noninteractive execution UIDs. Separate execution from App credential custody.

Routine flow is automatic: CoS assigns QA in Kanban; QA requests a QA run; successful QA handoff permits Reviewer to request independent review; successful independent review permits the existing merge request. Founder does not sign PASS or manually copy evidence. Missing permissions, OAuth refresh, unsupported sandboxing or scenario coverage produces BLOCKED, not assumed success.

## Observed inputs and gaps

- LXC 916 has `codex-cli 0.154.0`, root-owned `/bin/codex` launcher pointing to the globally installed package. `codex exec` supports JSON events, output schema, ephemeral runs, ignore-user-config/rules, explicit cwd and sandbox mode. `codex exec review --base` exists. These flags were read from this installed binary, not assumed from older docs.
- Reviewer and QA/Security OAuth files exist with their respective role ownership and mode 0600. No contents were read. Earlier runtime evidence records successful independent role logins and actual read-only tool calls. This is reusable authorization, not proof of a publisher boundary.
- Actual role homes currently have mode 0770 with their respective named groups; group listings show no supplementary members. `.codex` directories are 0755 inside those homes. The current role owns its OAuth file and workspace. A role can alter files it owns even if a particular Codex invocation uses read-only mode.
- `guard/__init__.py` permits Reviewer/QA `terminal`, `read_file`, `write_file`, `patch`, `search_files` through that role's SSH UID. This enforces cross-role identity, not a trusted verifier execution environment. It does not authorize treating that UID's output file as immutable evidence.
- `bwrap`, `systemd-run`, and `unshare` are installed. Nested namespace operation under this unprivileged LXC, network deny behavior and canary credential-read denials were **not tested** in this assessment.
- Active company services observed include gateway, GitHub broker and backups. No QA/review publisher service exists.
- Existing broker grants export only Checks read and Contents read to normal QA/Reviewer shells. Parent reports service-level App permission upgrades accepted; privileged keys still belong in services.
- Current merge controller already requires App-bound checks, exact H/B/PR external IDs, native current-SHA Reviewer approval, pinned CI and no-bypass policy evidence. Those dependencies have no live automatic producer yet.

Sources inspected: `bootstrap/company-worker.sh`, `guard/__init__.py`, role SOULs, `github-broker/{policy,upstream}.py`, `authority/merge/{merge_models,merge_policy,merge_server}.py`, `outputs/leaselab-company/{runtime-evidence,authority-research}.md`, and live command help/file metadata above.

## Minimal request and durable job identity

Two fixed Unix sockets, separate peer allowlists:

- QA socket: only `leaselab-qa-security` UID may submit.
- Review socket: only `leaselab-reviewer` UID may submit.
- Engineer, CoS, SRE, other roles, root-as-client and executor UIDs cannot submit. CoS dispatches through Kanban rather than impersonating either specialist.

Input is bounded JSON `{ "pr": N, "head": "40 lowercase hex" }` plus EOF. No PASS/FAIL, model, command, URL, path, check ID, resolved issue list or template input is accepted. Repository is always `yangjeep/leaselab`. Server resolves actual H, B, author, linked issue contract and target preview itself. Stale head rejects before execution.

Server creates a random job ID and a manifest keyed by role/repository-ID/PR/H/B/policy-version. Manifest includes immutable contract digest, source tree digest, executable/version/digest, scenario-registry version, run start/finish, exit states, test invocation IDs, artifact digests and final decision. One active job per role/PR. Deduplicate retries; a repeated socket submission never fabricates a second successful run.

Store manifest and captured evidence in publisher-owned directories, not `/srv/leaselab/roles/*/workspaces`. A tiny local SQLite state table or atomic manifest files suffice; no new board or orchestration platform. The supervisor holds output file descriptors and copies only bounded structured non-secret results to an immutable completed job directory. A checksum of a caller-writable file is not trusted evidence.

## Execution boundary

Use two dedicated UIDs such as `leaselab-qa-exec` and `leaselab-review-exec`, with no interactive SSH, no company socket groups, no GitHub/Slack/OpenRouter/production credentials and no sudo. The caller's role UID must not be able to signal, ptrace, edit configuration for, replace binaries of, or write evidence consumed from these processes. A trusted fixed unit launcher selects only one of these two templates and a supervisor-created job ID. Do not grant generic `systemd-run`, sudo command strings or arbitrary unit properties to roles.

Privileged launcher/supervisor constructs fresh H and B checkouts from a fixed remote using its read-only fetch credential. It does not reuse Engineer's `.git`, worktree, hooks, Git config, alternates, filters or untracked files. Disable hooks/submodules/automatic LFS commands; reject unsupported checkout constructs rather than executing them with authority. Source is immutable/read-only to verifier; test/build output goes to a separate disposable scratch tree. Build/package lifecycle scripts run in an unprivileged execution sandbox with no credential-bearing environment, and cannot mutate the immutable source or supervisor evidence.

Preserve the already authorized role-specific Codex identity. Use a one-time protected service copy of each role's existing OAuth into its own dedicated executor `CODEX_HOME`, with restrictive owner permissions; never share Reviewer and QA copies. Copy only the authorization material through trusted bootstrap, not role/project config, plugins or sessions. Treat the service copy as authoritative thereafter and serialize its refresh. Stop old automatic invocations from refreshing the original simultaneously; do not continuously sync user-writable `auth.json` into trusted runs. If independent refresh of an older original invalidates the service copy, fail BLOCKED and renew via the normal official flow. This is the same role authorization; additional interactive reauthorization is needed only when the provider demands it. No OAuth value belongs in launcher args, prompts or artifacts.

Codex's orchestrator needs its own auth, but model tools must be denied reads of `CODEX_HOME`, auth, `/proc` handles for privileged processes, service keys, supervisor job state and all Unix broker/publisher sockets. Read-only sandbox alone does **not** mean unreadable credentials. Root-managed permissions must be proven to impose deny-read rules and disallow weaker configs; avoid loading role/project hooks, MCP servers, plugins or writable config. Use an explicit audited config, clean environment, fixed cwd, no session resume, fixed opposite-family policy, structured output and bounded execution. Current CLI supports the relevant basic flags; exact managed permission support must be canary-tested on 0.154.0 before enabling publication.

For sandboxed commands, permit only necessary preview/dependency endpoints and block production/LAN control APIs and arbitrary Unix sockets. Network domain rules require an active enforcing proxy; writing an allowlist table alone is not enforcement. Model/provider traffic and tool subprocess traffic have distinct controls. Do not mount bot/GitHub/Google/production secrets for browser tests. A dedicated synthetic preview account may be supplied only to its narrow test driver.

If native managed denies cannot protect credentials/tool processes in this LXC, stop publication and use a separate disposable execution environment with a narrowly authenticated inference path. Do not substitute `danger-full-access` under the claim that read-only source is sufficient.

## QA execution and decision

Supervisor selects a trusted scenario set from a small root-owned registry, based on repository path/contract class. Initially support the actual marketing analytics change and explicit harmless validation fixtures; unsupported work types are BLOCKED. Avoid a nominal universal PASS from only `pnpm test`.

1. Fetch contract, current source and current preview deployment mapping independently. Record deployment ID, origin and build SHA. A green URL without immutable SHA mapping cannot prove preview testing H.
2. Run required repo checks in the disposable test sandbox and preserve exit status/output digest. Also run independent, supervisor-controlled functional/security probes; PR-controlled package scripts can return zero without testing anything.
3. Codex QA independently inspects source, contract and test evidence, proposes findings and evaluates coverage with a fixed structured schema. Required fields include exact H/B, per-scenario outcome/evidence references, findings, severity/boundary, disposition candidates and missing coverage.
4. Supervisor requires every mandatory deterministic scenario to pass, normal successful worker completion, complete schema, exact identity binding and no unresolved blockers. A model's final word PASS, zero CLI exit code, JSON schema conformity, role label or screenshot alone is insufficient.
5. Confirmed security findings are recorded as P0/P1 bugs through GitHub and retained in the service-owned finding ledger. Store GitHub issue ID as its external authoritative work-item link. Changing/closing/relabeling an issue through a normal Issues-write role must not erase an unresolved confirmed finding.
6. A resolved security finding requires its registered regression probe at H plus Codex disposition references. The independent review stage confirms it separately. Missing safe regression capability remains BLOCKED.

## Independent review execution

Start a fresh Codex run under the other executor/auth identity, after consuming the supervisor-owned successful QA job for the same H/B. Reviewer receives immutable source/diff, contract, QA manifest and evidence references; never Engineer-controlled session state. The author family remains Claude Code, verifier family Codex. A service-run implementation provenance record is needed for technical family enforcement; a SOUL statement or Git author string alone cannot establish which worker produced code.

Require structured current-H/B findings, contract verification, test/QA coverage review and independent security dispositions. Bind each evidence reference to a captured job artifact, not an arbitrary path/URL supplied by the model. No unresolved blockers means the supervisor may publish the review check and a native `APPROVED` review with `commit_id=H`. Failure publishes failure and an actual review/bug, returns a Kanban handoff to Engineer and never merges. A new H or B invalidates both jobs.

This provides authenticated execution and independent judgment, not mathematical proof of model correctness or immunity to prompt injection. Deterministic security scenarios, isolation, opposite author family and actual adversarial tests remain necessary.

## Publication protocol and retry semantics

Each publisher holds only its own existing App key in a separate UID-owned directory. QA App 4948555/installation 161806533 mints repository-scoped Checks write plus needed reads/issues write; Reviewer App 4948588/installation 161807039 mints Checks write, PR write and needed reads, **no Contents write**. Ordinary role broker tokens stay unchanged. Review publisher and merge service may share the App registration but must not share writable key directories or export broad tokens.

Publisher itself re-reads PR H/B immediately before publishing. It emits the exact current merge-controller schema:

- check names `leaselab/qa-exact-sha` and `leaselab/independent-review`;
- `head_sha=H`, completed/success only after its own gated job;
- `external_id=leaselab:v1:pr:N:head:H:base:B`;
- `output.summary` is strict JSON `{ "pr": N, "head": H, "base": B, "resolved_issues": [IDs] }`;
- a separate immutable evidence URL/digest links the supervisor manifest; never expose raw credentials or unredacted tool transcripts.

Only closing-linked issues that both publishers independently resolve qualify for the existing merge-controller exemption. Keep the richer finding/disposition record in immutable supervisor evidence. Do not accept `resolved_issues` from the socket caller.

The current merge controller rejects duplicate check names even if one is newer. Therefore persist the check ID created by the publisher and PATCH that same App-owned check through queued/in-progress/completed on a retried job; never create a second check for the same role/head. Reset stale success to in-progress before rerunning. Serialize shared-head requests across PRs because the check is commit-scoped while external_id is PR-scoped. API timeout requires reconciliation with stored check ID before retry. Existing ambiguous checks remain BLOCKED rather than being silently ignored or deleted.

## Critical GitHub rules visibility gap

Parent captured `main-ruleset-role-read.json` and `prod-ruleset-role-read.json`; both omit `bypass_actors`. Current real IDs remain 10502244 and 13297070. The browser still shows administrator Always bypass. Missing property cannot mean no bypass.

GitHub explicitly restricts this field to callers with write access to the ruleset; ruleset mutation requires Administration write. Existing merge-token Contents write is not documented as sufficient. Current `Ruleset.bypass_actors` model is required with no default, so it already fails closed when omitted. Do not add `[]` as a default to unblock rollout.

For fully automatic continuous no-bypass verification, choose a separately trusted policy observer with narrowly exposed fixed GET operations and a credential able to see the full ruleset. Keep that credential outside all agents, publishers and merge processes. The observer signs a short-lived complete policy snapshot/nonce tied to repository and ruleset IDs, never a caller-supplied policy. The merge service needs an explicit reviewed integration for that observation. This observer still possesses inherently powerful GitHub authority in custody and needs its own isolation/security review. Do not silently install the founder token or grant Administrator write to normal Reviewer tokens. A one-time founder screenshot is not an automatic drift detector and cannot fulfill the current controller's live check.

## Small implementation sequence

1. Add a bounded run-request parser and job manifest store beside this controller; lock the fixed repository/role/H/B and reject any result/path/command fields. Unit-test stale/duplicate/foreign-UID input before enabling execution.
2. Add root-owned QA and review unit templates with dedicated execution UIDs and a fixed launcher; bootstrap separate protected role OAuth copies. Keep App publishers under different UIDs. Test filesystem/process/socket canaries before giving a source tree to either executor.
3. Implement trusted fetch/export and two distinct execution lanes: Codex reads immutable source under managed deny-read policy; tests run a disposable candidate copy with **no OAuth at all**, only narrowly scoped synthetic preview context when required. The supervisor captures each lane independently. A readonly Codex sandbox is not a sandbox for arbitrary `pnpm` lifecycle scripts.
4. Register the initial marketing consent/security scenarios and harmless governance fixture as root-owned suites. Bind preview deployment ID to H. Run failure and correction fixtures; store actual transcripts/exit states privately with sanitized immutable manifest references.
5. Implement two publishers over existing App token exchange, with server-owned check IDs and exact controller schema. Produce native Reviewer review only from its completed independent job. Add the persistent confirmed-finding/disposition ledger to both PASS decisions; GitHub Issues remains the external task contract, not the sole tamper-resistant blocker state.
6. Exercise caller/evidence tampering and rerun/stale-head tests. Keep actual merge blocked until complete ruleset observation is possible and actor/quality settings are applied. Then run the harmless automatic PR through real Kanban handoff and guarded merge.

No founder PASS entry is a step in this sequence. No production deployment belongs to it.

## Concrete acceptance before first trusted PASS

1. Author role cannot submit either job; QA cannot request review; verifier cannot call merge socket or read App keys.
2. A role-supplied PASS file, forged JSON events, symlink evidence path, altered role config or concurrent same-role process cannot influence captured evidence.
3. Canary files representing OAuth/App secrets are unreadable through model tools and test scripts; blocked network/control sockets stay blocked; provider inference still works.
4. H checkout bytes and base mapping survive a concurrent Engineer push; old job publishes stale/failure and cannot satisfy new head.
5. Required functional/security probe actually fails a seeded safe defect, creates P1 bug, then passes after a corrected H; no fake security issue remains after validation.
6. Native test stdout that prints PASS or forged event JSON cannot override supervisor exit status/schema/evidence provenance.
7. Review uses a fresh Codex process and rejects an Engineer-authored blocker; both exact-H dispositions are necessary to resolve the security issue. Relabeling/closing that issue alone cannot erase the ledger blocker.
8. GitHub checks show correct App IDs, H/B binding and immutable evidence; retries update one check; native review maps to H; current CI and no-bypass policy observation pass.
9. Actual harmless PR completes CoS → QA → Reviewer → guarded merge without founder PASS entry. Production promotion remains a separate SRE gate.

Implementation can proceed without another human authorization for ordinary code/accounts/isolation. Human involvement remains only for genuinely unavailable OAuth renewal, privileged policy-observer credential authorization or GitHub setting capability. Until these boundaries are implemented and exercised, existing Codex successes and manually collected QA artifacts remain useful diagnostic evidence, not publishable trusted gates.

## Primary references

Installed CLI help supplies the command-specific observations above. Official [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive) documents saved authentication, structured final output and JSON events; these features do not authenticate a caller-owned result file. Official [configuration reference](https://developers.openai.com/codex/config-reference) documents managed deny-read requirements and the need to activate a network proxy for domain enforcement. Official [GitHub check runs API](https://docs.github.com/en/rest/checks/runs) defines create/update of App-owned check runs. Official [ruleset API](https://docs.github.com/en/rest/repos/rules#get-a-repository-ruleset) documents bypass-field visibility and Administration-write mutation permission.
