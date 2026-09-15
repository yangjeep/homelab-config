# LeaseLab company bootstrap

Deployment is **incomplete; founder-only CoS/Support bootstrap execution is active**.
This directory must not be interpreted as proof that an autonomous company is ready.

## Installed infrastructure

- Proxmox VMID `916`, hostname `hermes-leaselab`.
- DHCP address observed `192.168.253.217`, vmbr0 VLAN 253.
- Debian 13, unprivileged LXC, 4 vCPU, 8192 MiB RAM, 40 GiB on `vm-micron`.
- Community Scripts source `787dbf2420ec8217c967eb4c152cb3003446d327`;
  core source `cf804c82f9d9050d8e9e30f0c33c148bd883dc18`.
- Hermes v0.21.3, installed upstream revision
  `b8bf4843518c4dc1319d4476adda0cc9cc169045`.
- Installer-created user `hermes`, checkout `/home/hermes/.hermes/hermes-agent`.
- Seven native profiles and native board `leaselab-company` exist.

## Rebuild and state

Review `bootstrap/create-lxc.sh` on the PVE host before running it. It refuses an
existing VMID. The pinned Community wrapper still invokes the upstream Hermes
installer; record the actual resulting Hermes revision after every installation.

Copy this directory into the new LXC, run `bootstrap/isolate-roles.sh`, then
`bootstrap/configure-profiles.sh`. These are initial bootstrap operations:
configuration generation intentionally disables Telegram and must not be used as
an unattended update over an operational installation.

Run `bash bootstrap/install-gateway.sh` to install the guarded systemd launcher
and the tested Telegram dependency. This installs without enabling the gateway.
Provision credentials in private `.env` files, verify the founder allowlist,
enable Telegram only in CoS config, then deliberately enable/start
`leaselab-company-gateway.service`. Profile generation includes a 40-turn,
240-second agent budget. The gateway installation script was exercised on LXC916
without interrupting the active gateway, followed by a passing live preflight.

Profile state lives in `/var/lib/leaselab-company/profiles`, linked from
`/home/hermes/.hermes/profiles`. Board state is under
`/var/lib/leaselab-company/kanban`. Role workspaces and dedicated coding-worker auth
live under `/srv/leaselab/roles/<role>`. Secrets belong in external secure storage
and private profile `.env` files; use `.env.example` only as a template.

## Boundary and current limitations

The central Hermes runtime is trusted and runs as `hermes`. Profiles are **not**
separate OS sandboxes. Six specialist terminal/file backends execute through
loopback SSH as distinct `leaselab-<role>` users. Those users cannot read central
profile credentials, other role SSH keys, or the central Kanban database.
The native permission plugin denies unapproved tools and checks effective SSH
configuration. Chief of Staff has no terminal/file tools.

The stock dashboard is disabled. Telegram is enabled only for Chief of Staff,
restricted to the verified founder private identity. The system service
`leaselab-company-gateway.service` runs the sole native dispatcher, guarded by
preflight checks and an exact seven-role worker launch allowlist. Six Unix roles can obtain reduced GitHub tokens through the live broker; Engineer
remains denied. Growth has dedicated Google readonly access. Production deployment
credentials remain external and are not available to roles.
Do not install personal/founder GitHub credentials in this LXC.

The model alias observed in OpenRouter's catalog is
`~deepseek/deepseek-v4-flash-latest`; live inference resolved to
`deepseek/deepseek-v4-flash-0731`. Seven independent profile keys in OpenRouter workspace
`971052d6-f9b0-4bdc-baae-69c8c4a02b7f` now have API-verified aggregate USD 30
monthly hard budget. All seven native profile calls and distinct per-key usage
passed; the old shared key was disabled. Model and routing settings were retained.
The secondary USD 30 per-key limits do not raise the workspace total. See the
[credential matrix](credential-matrix.md) for vault references and rotation.
GitHub exact-SHA QA, merge/release controllers and production authority remain
incomplete.

Current founder-selected pairing: Engineer uses Claude Code; Reviewer and
QA/Security use Codex. All three official OAuth logins completed through
ego-browser, with separate auth stores under their Unix homes. Actual inference
passed for all three; Reviewer and QA also executed id/pwd in their own workspaces.
All six pairwise credential-read attempts were denied. Superseded Reviewer Claude
login was logged out. This verifies coding authentication, not GitHub/release
authority or full company acceptance.

## Backup and recovery

PVE job `leaselab-company-daily` backs up only VMID 916 to `nfs-nas`, daily at
05:15 PVE time, snapshot mode with zstd, keeping 7 daily and 4 weekly copies.
The full-container backup includes private state and eventually credentials:
apply the same restricted access policy to backup storage as to the live LXC.

For recovery, stop the existing company gateway before restoring. Restore a
selected backup to an unused VMID and isolated network first. Keep Telegram and
the dispatcher disabled during validation to prevent duplicate consumers.
Verify profile separation, board consistency, credential validity and budget
limits before deliberately switching the single company gateway to the restored
instance. The full-container PVE restore rehearsal has not yet been performed; the separate
Git and native Hermes NAS restore drills described below passed.

## Acceptance status

Observed on the live LXC: all six specialist SSH identities deny central secret,
other SSH key, guard-code write, and Kanban database access. The native plugin
blocks `execute_code` and permits `memory`.

Founder-origin Telegram task `t_ff5745ec` was created by CoS, dispatched to
Support and completed in 48 seconds. Actual terminal identity was
`leaselab-support`; the role workspace passed the write/remove check. The
completion notifier woke CoS and the gateway logged the outbound Telegram send.
Final device receipt was not independently captured. Structured handoff remains
incomplete: the worker recorded username/cwd in its summary instead of metadata.

These checks do not replace full A–G validation. Unauthorized-user testing,
full coding-agent handoff, exact-SHA QA/merge governance, preview release and the
final security review remain outstanding. Google readonly reports and six broker
repository-read tests have passed; those do not complete the remaining gates.

### Growth Google reporting (verified 2026-09-14)

Dedicated Google Cloud project: `leaselab-growth-2026`, with only the Analytics
Data API and Search Console API explicitly enabled for reporting. Service account
`growth-readonly@leaselab-growth-2026.iam.gserviceaccount.com` has no Cloud IAM
project role. Its GA4 permission is Viewer on property `554159868`; Search Console
permission is Restricted on `sc-domain:leaselab.ai`.

Restore the external 1Password document identified in the credential matrix to
`/srv/leaselab/roles/growth/.config/leaselab/google-service-account.json`, owned by
`leaselab-growth`, file mode 0600 and parent directory mode 0700. Install Debian
packages `python3-google-auth` and `python3-requests`. Run reporting through the
Growth SSH execution identity with `/usr/bin/python3` and the two readonly scopes
listed in its SOUL. Never copy the credential into the shared Hermes home.

Verification returned HTTP 200 for GA4 and Search Analytics reports. Search
Console lists only the LeaseLab domain as `siteRestrictedUser`. The new GA4
property has no data until marketing-site instrumentation is deployed. Issue #779 candidate `aa3f3e763d0e20f1a533d22c5e233a8e30132649` passed independent Codex review, current-build browser consent/network/cross-tab checks and two fresh desktop/mobile visual reviews after privacy, region semantics and contrast fixes. Instrumentation is not merged or deployed; these manual results do not substitute for trusted GitHub QA checks. Unrelated
ALDA property access and readonly-token write attempts returned HTTP 403; all
other specialist UIDs were denied file reads. The GA4 property resides under the
existing Alda Storefront account and inherits its existing human permissions;
this is not a separately isolated GA account.

Rotation: create a replacement key for this service account, store its JSON in
1Password, replace the Growth-only file atomically, rerun the read-only reports,
then delete the old key in Google Cloud. Revoke property access as well when
retiring the Growth service identity. The Google project has no billing activation
performed by this bootstrap.

## Slack collaboration and role GitHub access

The existing Slack workspace `leaselabai.slack.com` uses seven distinct Slack
app/bot identities, one per existing Hermes profile and OpenRouter credential.
Each runs a dedicated native Socket Mode gateway with deterministic Founder
mention routing; only CoS dispatches Kanban work and receives Telegram. The
restricted `leaselab-slack-send` toolset uses real bot identity without simulated
role prefixes. The [Slack configuration](slack/README.md) documents seven approved
channels including incidents, incremental rollout, credentials and rollback.
Direct Slack access does not bypass durable Kanban work or GitHub QA/merge/release
gates. Record current end-to-end transport and management-cycle evidence in the
deployment report; identity provisioning alone is not workflow completion.

The GitHub broker is installed and enabled; its real peer-UID tests and six live
role repository reads passed. Engineer has no installed App/key and is denied.
Normal tokens cannot publish trusted QA checks or merge; service-held QA App
Checks-write is not exported by the broker. Review the [App inventory](github-app-inventory.md)
before changing grants. Cloudflare and Vercel service credentials are vaulted and
read-tested only; no migration/promotion controller is ready.

Knowledge backup to private `yangjeep/hermes-leaselab` on `main` passed at commit
`c6161904c748bfa0663c7c1c56a618384a2b073e`. A fresh-clone restore matched all seven
profiles and passed secret scans; Git excludes `.env`, auth, databases and keys.
The hourly `leaselab-knowledge-backup.timer` is enabled and active.

The independent TrueNAS full backup and isolated native restore also passed.
`leaselab-full-backup.timer` is enabled and active daily at 03:30 plus jitter.
Target: `/mnt/main/homelab/backup/hermes-agent-leaselab/archives`;
verified archive `hermes-leaselab-full-2026-09-15-051048Z.tar.gz`. All seven
profiles, Kanban and shared databases restored with CRC/checksum/SQLite integrity
checks. No restored gateway was started. Exact archive hash and verification are
in [deployment evidence](backup/DEPLOYMENT-PREP.md).

The NAS archive includes native profile `.env` and `auth.json`, unencrypted under
the existing restricted-permission backup policy. It excludes backup private
keys and external role-home credentials, which remain separately recoverable
from documented external storage/authorization. Dedicated NAS UID 3004 is
upload-only to this target; shell, download and delete requests were denied.
Temporary secret-bearing restore files were removed. The temporary administrator
public key was removed and a new SSH attempt was denied; the control connection
was closed and temporary key/askpass files deleted. See [backup procedures](backup/README.md) before restore or timer changes.

CoS now uses a [structured GitHub tool](github-tools/README.md) for its fixed
repository/issue operations and PR comments. Actual native execution created and
closed synthetic issue781 as the CoS App identity. Its dedicated SSH key accepts
only the trusted JSON runner; arbitrary command execution was denied. The
[merge controller](authority/merge/README.md) has offline tests but stays disabled
until trusted publishers and effective branch rules are complete.

## Company observability

LXC916 host and selected service metrics plus seven-role OpenRouter usage and Kanban lifecycle aggregates are live in Prometheus. Eight data sources passed actual collection. The [observability runbook](observability/README.md) documents the five-minute collector and Grafana **AI - LeaseLab Company** dashboard. Grafana accepted the dashboard and all eleven queries returned data; browser visual verification is pending authentication. Metrics contain no raw task bodies or model prompts. They do not establish trusted QA, merge or release approval.

## Authority implementation status

Dedicated Reviewer and QA executor identities passed authenticated Codex boundary canaries with a root-owned supervisor and isolated credential-free test lane. Access-only authentication snapshots expire; unattended refresh and trusted check publication are not enabled. Exact head/base source materialization passed live Git object verification and immutable-source access checks; it does not establish code quality or merge eligibility. The release eligibility library is tested offline and deliberately has no production transport or credentials. See [executor evidence and runbook](authority/publisher/EXECUTOR.md), [verified source contract](authority/publisher/SOURCE.md) and [release contract](authority/release/README.md).

The company guard rejects cross-profile `session_search` selectors before native
dispatch while retaining own-profile history search and recall. The deployed
fix passed a synthetic two-profile replay through the installed Hermes runtime
and 424 policy tests. The trusted central runtime still has OS-level state access;
this tool boundary is not a claim of independent OS sandboxes for native profiles.

CoS can use `company_founder_notify` for important Founder escalations from a
Slack-origin workflow. The tool constructs the verified Telegram recipient
internally and accepts only bounded attributed text. Other roles are rejected
by both prehook and handler. One native connectivity message was accepted by
Telegram; it is not a human read receipt. Slack and Telegram text-only paths
reject case-insensitive native media directives. The combined guard suite
passed 464 tests after this deployment.

The disabled merge service now has an authenticated fixed-socket Policy Observer
client. The separate observer App still needs explicit Administration-write
authorization before it can be provisioned. Tests and source code do not grant
that authority or enable the merge service.

The root-managed [verification command](authority/publisher/VERIFICATION.md)
now connects exact GitHub source, an isolated documentation check and a real
Codex Reviewer. A historical PR returned a validated `clear` disposition;
a factual-error fixture with hostile instructions/configuration returned a
finding. Both remain non-authorizing evidence. Full QA recipes, trusted check
publication, supported unattended auth and the merge/release workflow are still
unfinished. See the [Reviewer runbook](authority/publisher/REVIEW.md).
