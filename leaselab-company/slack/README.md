# LeaseLab Slack team

The existing workspace `leaselabai.slack.com` (`T021CUR5KTP`) has one real Slack app/bot identity per existing Hermes profile. Founder `U0225R7NP8Q` can mention a specialist directly. Shared native integration code binds each gateway's Slack credential to its fixed profile; an LLM does not select the recipient.

| Profile | Slack display name | Gateway |
| --- | --- | --- |
| chief-of-staff | LeaseLab CoS | leaselab-company-gateway.service |
| engineer | LeaseLab Engineer | leaselab-company-specialist@engineer.service |
| reviewer | LeaseLab Reviewer | leaselab-company-specialist@reviewer.service |
| qa-security | LeaseLab QA | leaselab-company-specialist@qa-security.service |
| sre | LeaseLab SRE | leaselab-company-specialist@sre.service |
| support | LeaseLab Support | leaselab-company-specialist@support.service |
| growth | LeaseLab Growth | leaselab-company-specialist@growth.service |

Each native process has fixed `HERMES_PROFILE` and `HERMES_HOME`, distinct `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`, and its own OpenRouter credential. Multiplex is disabled because current guard/terminal authority is process scoped. Profiles are not OS sandboxes. Only CoS runs the Kanban dispatcher and Telegram gateway; specialist Telegram configuration and credentials are rejected.

## App provisioning

Use the existing workspace and official Slack App Manifest API or authorized Slack administration UI. `app-manifest.json` is the shared CoS template. For each existing specialist, change only `display_information.name` and `features.bot_user.display_name` to the table's name before creation. Retain Socket Mode, event subscriptions and minimum required bot scopes. Install each app into this workspace, generate its own `connections:write` app token, and invite each bot to the approved channels. Do not create duplicate Hermes profiles or duplicate apps on repeat runs: inventory existing app IDs first and update the existing app.

Store each bot/app credential in a dedicated 1Password item. Record symbolic item references and app/bot IDs in the credential matrix, never token values. App configuration/management credentials are bootstrap only and must not enter profiles, prompts or Git backup.

The root-owned, non-group/world-writable `/etc/leaselab-company/slack-identities.json` is nonsecret authoritative routing configuration:

```json
{
  "team_id": "T021CUR5KTP",
  "founder_user_id": "U0225R7NP8Q",
  "channels": ["C0C2Q3Y1QF2", "ACTUAL_ADDITIONAL_CHANNEL_IDS"],
  "incident_channel_id": "ACTUAL_INCIDENT_CHANNEL_ID",
  "roles": {
    "chief-of-staff": {"app_id": "ACTUAL_APP_ID", "bot_user_id": "ACTUAL_BOT_USER_ID"}
  }
}
```

This is a shape example, not runnable configuration. Supply all seven actual unique roles/apps/bot IDs and actual channel IDs. The incidents ID must occur in `channels`. The native ingress plugin verifies workspace, Founder, app identity, authenticated bot identity, exact mentions and allowed channels. Unknown users/routes and bot-originated messages fail closed. Multiple known role mentions are handled only by CoS. DMs are disabled; thread replies also require mentions.

## Incremental installation

Use `install-team.sh`; do not rerun `configure-profiles.sh` over production profiles. Provision a dedicated root-owned installer environment using a trusted root-owned `uv` executable:

```sh
uv venv /opt/leaselab-company-installer/venv --python /usr/bin/python3
uv pip install --python /opt/leaselab-company-installer/venv/bin/python -r slack/installer-requirements.txt
```

The pinned direct dependencies are PyYAML 6.0.3, pydantic 2.13.5, python-dotenv 1.2.3 and typer 0.27.2. `INSTALLER_PYTHON` may select another suitable root-owned interpreter. Do not run root configuration mutation through the Hermes-user-owned runtime interpreter. Gateway preflight runs as `hermes` with the existing native interpreter.

Provision six specialist credential JSON files outside Git in a root-owned 0700 directory, each `<profile>.json` root-owned 0600, containing `profile`, `workspace` (team ID), `app_id`, `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`. Transfer secret bytes through a protected stream, not command arguments/history. Existing CoS credentials remain unchanged. Alternatively supply already-provisioned private profile environments and omit `--credentials-dir`.

```sh
# Validation/staging only; no installed changes or service stop.
slack/install-team.sh /root/slack-identities.json \
  --credentials-dir /var/lib/leaselab-company/slack-secrets-staging

# Install after staging passes; services remain stopped for explicit verification.
slack/install-team.sh /root/slack-identities.json \
  --credentials-dir /var/lib/leaselab-company/slack-secrets-staging --apply

# Add --start to start all seven units after installation. No unit is enabled automatically.
```

The installer clones private environments and configs into temporary staging, overlays only specialist Slack keys/allowlist flags, checks distinct credentials and root-managed mapping, and preserves unrelated OpenRouter/model/terminal/Telegram settings. It incrementally enables the guard, ingress and management plugins/toolsets. It preserves `.env`, config and SOUL ownership/modes. It never prints credentials.

Before stopping running gateways, it saves private original configs/SOUL/environments, plugin files/links, mapping and unit changes under `/var/backups/leaselab-company/slack-team-<UTC>/`. An apply failure invokes the generated rollback script; a rollback failure is explicitly reported. Manual rollback uses that same root-only `rollback.sh`. It restores files and previously active gateways, disables newly enabled specialist units and restores their previous enablement. The existing CoS service and Telegram preflight remain; a drop-in adds the shared native Slack ingress preflight.

Validate actual authorized mentions for all roles, unauthorized routing, CoS coordination, incident drill and weekly cycle before enabling specialist units for boot. Retain the backup through verification. Remove external credential staging only after vault storage and successful rollout; backup archives contain secrets and must stay private.

## Work and management boundaries

Native replies use each bot's real identity, without simulated role prefixes. The guarded sender permits plain text to existing per-role channels and the root-configured shared incident channel; it rejects DMs, arbitrary targets, media directives and non-send actions. Telegram's fixed CoS notification tool retains its separate CoS prefix requirement.

Single-role questions and safe investigation can stay direct. New durable specialist intent calls `company_request_coordination(intent)`, producing an idempotent CoS triage card. The native session supplies validated provenance; the model must not invent a source reference. CoS alone uses `company_management` and native Kanban assignments. Nontrivial engineering needs a GitHub issue contract. Multi-role/P0/P1 coordination persists owner, participants, evidence and handoffs in Kanban; one Slack incident thread carries collaboration. Slack urgency never bypasses QA, Reviewer or SRE authority.

The existing CoS Hermes scheduler runs the weekly management workflow. Provision it using the management package's documented native scheduler command after plugin rollout; do not add another scheduler. Six role-specific reviews produce durable notes and evidence-based synthesis. Missing roles have explicit incomplete/retry state. Founder receives a concise weekly summary and material incident updates through the existing allowlisted Telegram control surface.

## Verification

`slack-team-preflight.py` requires the ingress plugin's native handler factory and exercises its installation into a real Bolt app before either CoS or a specialist starts. `specialist-gateway-preflight.py` additionally denies Telegram, multiplex and dispatcher/identity overrides. Failed discovery is fatal to service startup.

The configurator and permission tests cover distinct credential validation, atomic pre-write rejection, authority boundaries, dynamic incident permissions and unprefixed text. These are preparation evidence; successful deployment requires real Slack mentions, native Kanban handoffs, incident recovery and the complete management-cycle drill. Record results separately without secrets.

## Native CLI worker context compatibility

Kanban processes use central nonsecret `/var/lib/leaselab-company/workspaces/<role>` directories, while terminal/file tools retain the private SSH role workspace. The production wrapper rejects legacy private-workspace task launch before execution. Existing unclaimed tasks must be migrated through native `set_workspace_path` before changing the wrapper; preserve task IDs and never change an active worker's workspace.

Hermes 0.21.3 source `b8bf4843518c4dc1319d4476adda0cc9cc169045` still probes remote/private project files locally during CLI prompt assembly. `bootstrap/patch-context-permissions.py` applies a narrow permission-safe outer project-discovery catch, preserving independent SOUL loading and memory. It does not use `--ignore-rules` or change role permissions. Original prompt-builder SHA256 is `586ea363fa1e70bb0fdd5426af40758976a16c54f07efeb7a1b4f3fe0ad99309`; patched SHA256 is `7fa3ff1fe70fa384ae45b28974610d0562a084e2a8c58cef3e6fbcb72f8ec938`.

The installer checks this exact source before stopping services, backs up the native file with its other rollout artifacts, then applies the idempotent patch. Unknown upstream content is rejected; inspect an update and remove the compatibility patch once upstream handles the boundary correctly. A separate original backup is under `/var/backups/leaselab-company/native-context-permissions/`. The generated rollout rollback restores the native file alongside configuration and wrapper. No complete Hermes fork is maintained.
