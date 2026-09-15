# Native management implementation validation

2026-09-15, Hermes 0.21.3 at b8bf4843518c4dc1319d4476adda0cc9cc169045, LXC 916.

## Implemented boundary

- One native Kanban database. `create_task` does not support a metadata argument; typed records live in native task bodies and CoS-authored comments/results.
- Native `initial_status="running"` creates dispatchable `ready` tasks; `ready` is not an accepted creation argument in this installed version.
- Weekly anchor is blocked; six independent role interviews are ready; only the summary depends on all six. Containment uses body identity and creator origin, not dependency edges to an unfinished parent.
- CoS reads `team_status`, chooses six role-specific questions, then starts the cycle. The question plan is persisted and reused on retry. New cycles cannot be started through the management tool without that plan.
- Native dispatcher launch directories use `dir` and `/var/lib/leaselab-company/workspaces/<role>`. SSH terminal/file execution retains private `/srv/leaselab/roles/<role>/workspaces`; the two paths serve different trust boundaries.
- Each worker has three native retries and a 900-second runtime bound. A separate checkpoint job in the same native scheduler records partial results and real incomplete/retry state after one hour; it does not bypass final dependencies.
- Incident state checkpoints require a CoS native comment author and preserve original identity, participants, owner and severity. Closure requires every expected participant and explicit verification; an empty/missing participant set cannot pass vacuously.
- Intake author is the invoking specialist, assignment is always CoS. Source identity comes from task-local native Slack context or the invoking role's running Kanban task. Caller text cannot pick an arbitrary origin. Slack scope, Founder, channel and timestamps are validated. Native priority is 2 for P0, 1 for P1/intake, 0 for weekly interviews.
- Slack routing directory is a fixed root-owned non-writable non-symlink file. Only public bot IDs/channels/incident channel are serialized; unknown fields are discarded.

## Verification performed

- Real installed native database, isolated temporary boards: **15 tests passed** in 1.68 seconds. No production board mutation.
- Tests cover idempotency, acyclic dependencies, partial evidence, dependency release, premature closure denial, native checkpoint recovery, forged author/participant denial, persistent manager questions, weekly parent completion, role authorship, native priority ordering, nonsecret directory projection, writable directory rejection, and task-local Slack provenance/unauthorized user rejection.
- Actual native PluginManager discovery in an isolated home: CoS management tool registered; specialist coordination tool absent in CoS process.
- Actual native cron API in an isolated home: provisioning twice preserved exactly two IDs; paused job was restored to enabled; next-run timestamps used Toronto's current UTC-04:00 offset.
- Basedpyright strict: zero errors/warnings. Ruff: passed. No-excuse rules: passed (final source verification recorded by parent).
- Existing embedded SQLite 3.46.1 emitted Hermes' WAL-reset warning; upstream safely selected DELETE journaling. This task did not alter the database engine.

Native tests stage at `/tmp/leaselab-management-validation`, test-only Python dependencies at `/tmp/leaselab-management-testdeps`. They were run as `hermes`, not root. Local tests skip when the installed Hermes source is unavailable; this is not a replacement for the real native run.

## Production provisioning (parent execution)

Install all runtime `management/*.py` and `plugin.yaml` root-owned. Enable the `leaselab-management` native plugin and toolset for all seven profiles. Registration exposes management only to CoS and coordination intake only to specialists. Persist CoS `timezone: America/Toronto` before provisioning.

```sh
runuser -u hermes -- env \
  HOME=/home/hermes \
  HERMES_HOME=/var/lib/leaselab-company/profiles/chief-of-staff \
  HERMES_PROFILE=chief-of-staff \
  HERMES_KANBAN_HOME=/var/lib/leaselab-company \
  PYTHONPATH=/etc/leaselab-company:/home/hermes/.hermes/hermes-agent \
  /home/hermes/.hermes/hermes-agent/venv/bin/python -m management.scheduler
```

The provisioner updates/resumes existing named jobs; it does not create another scheduler. Native schedules are Monday 09:00 and Monday 10:00 in the persisted CoS timezone. `context_from` is deliberately unused: that field takes cron job IDs, not Kanban task IDs.

## Actual team validation still required after deployment

Send CoS: “Run the current weekly management cycle now. First read company_management team_status and linked evidence. Choose meaningful questions for each specialist, then call weekly_start with all six questions. Let real native workers complete their interviews. Use the dependent synthesis task, weekly_close and one concise Founder weekly TL;DR. Do not invent shipped work.”

Then execute the authorized harmless synthetic multi-role/P1 drill through Slack. Observe actual native worker execution, role handoffs, Slack threads, persisted state, closure and Founder delivery. The isolated integration checks above do not claim these production-surface E2E outcomes.

## Live intake UX correction

The live Support drill exposed an unnecessary caller-controlled `source_ref` argument. Six specialist SOULs instructed the model to provide it, so Support repeatedly guessed routing identifiers even though the backend already had authoritative native context.

The request model and actual registered tool schema now accept only `intent`. Unknown fields remain rejected; the validation error explicitly instructs the caller to provide only intent. No native provenance checks were relaxed. Root/thread/channel/user/workspace still come exclusively from validated task-local Hermes context or the invoking specialist's running native task.

Regression: the old schema failed the new intent-only assertion. After the fix, **17 native tests passed in 1.76 seconds**, including the actual handler against an isolated real Kanban database: intent-only call, correct derived Slack source and thread root, Support author, CoS assignment, and duplicate-call idempotency. Strict type checks and Ruff passed. Parent must update the six specialist SOUL instructions and reload gateway schemas before repeating the live drill; this subtask did not deploy or restart production.

## Actual weekly/incident creation and native handoff correction

Read-only inspection of CoS tool calls found that messages 77 and 84 passed a calendar date in `week`, correctly failing the ISO-week pattern. Their exact Pydantic error was only `week: string_pattern_mismatch`; the model's explanation about question length was not evidence. Message 95 omitted week and successfully created the eight-card weekly cycle. Message 112 successfully created the five-card incident. Both successful payloads were replayed unchanged against isolated native boards and passed; no production cards were changed.

Changes following this evidence:

- Expose the actual ISO-week pattern/description in the tool schema. Validation failures return field paths and rules only, never input values. Question size constraints remain enforced.
- Return typed `assignments` mapping each role to its task ID, so CoS cannot mislabel children by guessing list order.
- Incident children have distinct role scopes. QA depends on primary-owner evidence; Reviewer depends on QA when present. One primary diagnosis/fix path remains explicit. Existing production/merge gates are unchanged.
- Native workers write `task_runs.summary` while leaving `tasks.result` NULL. Read `native.latest_summaries` in bulk and expose `handoff_summary` explicitly, retaining raw result semantics. Actual completed Support task `t_4a6e4c28` was verified readonly: result NULL, native handoff available, 485 characters. Regression uses actual native `complete_task(summary=...)`, not a fabricated tasks.result.
- Dispatcher working directory is now central-readable nonsecret `/var/lib/leaselab-company/workspaces/<role>`, separate from the SSH role workspace. Parent owns directory provisioning and safe existing-task migration; no private role directory permissions were widened.

Final isolated native suite: **21 passed in 1.67 seconds**. Actual native Support PluginManager loading passed and exposes only the intent argument; CoS management tool remains absent. Strict types, Ruff, and no-excuse checks passed.

Deployment must include all runtime `.py` files, including `incident_roles.py` and `registration.py`, plus `plugin.yaml`; the public package `register` entrypoint remains intact. Parent must choose a safe reload boundary for already-running gateways/workers. This subtask did not restart or deploy production and did not alter existing tasks.

## Native authored notes, completion metadata and artifact descriptors

The SRE completed interview demonstrated another supported native handoff surface: the full structured note was a task comment authored by `sre`, while the closing run summary was only a short pointer. Management now exposes separate `authored_notes`, `completion_evidence` and `artifacts` fields on task views using native `list_comments`, `list_runs(include_active=False)` and `list_attachments` APIs. Each record retains its author or run profile. Only the current assignee and CoS contribute these fields; attachment file contents are never read. The existing `Board.comments` checkpoint reader remains strictly CoS-only and unchanged.

Read-only production verification:

- SRE `t_a3f0a899`: DONE; one authored SRE note, 2166 characters, now visible through the new adapter.
- Engineer `t_fe020b0e`: native closing run belongs to engineer; metadata exposes fixture, method, reproduction, repro_output, evidence, acceptance_criteria, verdict and handoff, with correlation fields retained. No metadata values or note contents were printed into validation logs.

Regression first failed, then **22 native tests passed in 1.84 seconds**, including actual `complete_task(summary=..., metadata=...)` and a separately authored native comment. The test also proves another role's comment is excluded and the CoS-only checkpoint method is unaffected. Strict types and lint passed.

Deployment delta: `models.py`, `native.py`, new `native_evidence.py` (plus source stubs/tests for reproducibility). No production deployment or restart was performed by this subtask.

### Native incident notification receipt (2026-09-15)

`incident_start` now serializes CoS gateway/dispatcher entry with a board-local
advisory lock, persists the blocked anchor, and records `notification_state=pending`
before invoking the existing native `send_message_tool`. It posts to the configured
`#incidents` channel using the root-owned role identity map, then checkpoints the
returned message timestamp as `slack:C...:1234567890.123456` with state `sent`.
Only after that receipt exists are participant cards created/released. The returned
`Cycle.slack_thread` and role instructions reuse that canonical thread; the latest
CoS checkpoint supersedes any historical task-body target. Other checkpoints cannot
erase or replace a sent receipt.

No additional Slack client, tokens, scheduler, or state database is introduced.
The adjacent `.incident.lock` file contains no state or secrets. No exactly-once
transport claim is made: a crash after Slack accepted a message but before receipt
persistence is ambiguous. Returned transport failures become `reconciliation`;
process death leaves `pending`. Either state blocks creation of new participants
and refuses blind automatic resend. An authorized CoS must inspect the existing
incident root and resume `incident_start` with its actual `slack_thread`. A retry
then checkpoints the supplied recovery target and creates/reuses the same cards.
Historical malformed targets remain readable but require the same explicit repair;
they are never converted from provenance into a destination. If no root exists,
create one through the already authorized native send surface, inspect its receipt,
and resume with that target. Do not delete the pending state to force a resend.

Tests use real isolated native boards; only directory provisioning and external
native-send transport are substituted. They cover attempt-before-send ordering,
receipt-before-dispatch, failed delivery, process interruption, no blind resend,
explicit recovery, idempotent resumed cards, concurrent entry exclusion, canonical
receipt immutability, historical record readability, and target validation.
Production deployment/restart and live recovery remain the parent executor's work.

Recovery-root verification now uses the already installed Slack SDK and native
`agent.secret_scope.get_secret` with the CoS profile's own credential. An exact
`conversations.history` query (channel plus identical oldest/latest timestamp,
inclusive, limit one, 15-second timeout, no SDK retries) must return a root authored
by the configured CoS bot. Its text must identify both the incident ID and
`Authoritative Kanban: <parent ID>`. Missing, unrelated, reply, other-bot, malformed,
or unavailable evidence fails closed. This read occurs for every supplied recovery
target and every `sent`-state resume; a CoS-authored checkpoint flag is not evidence.
No model-writable verification boolean is trusted or stored. Native successful-send
receipts establish the initial thread without another network read. Same-ID resumes
also reject changed GitHub links alongside participants, owner, severity, impact,
and synthetic status. Existing confirmed 003 root can be verified and reused without
creating another root or changing completed child IDs.

### Durable incident wake subscription

`incident_start` subscribes the verified root anchor before participant creation,
using `hermes_cli.kanban_db_notify.add_notify_sub` with `delivery_mode="wake"`.
The destination is the fixed configured incident channel and canonical thread,
workspace `T021CUR5KTP`, Founder `U0225R7NP8Q`, and notifier profile `chief-of-staff`.
Native `create_task` calls `inherit_creator_origin` inside its transaction, so new
children receive the durable subscription before becoming dispatchable. Existing
children and summary cards are repaired idempotently. A conflicting owner on the
same subscription key fails closed rather than silently adopting foreign routing.

The native notifier supports wake-only delivery, but no per-subscription event
filter. It wakes on completion, blocked, gave-up, crash, timeout and review events;
bookkeeping events remain silent. There is no passive Slack event ping. Existing
native cursor/claim/delivery handling supplies restart/retry behavior. Slack wake
sources are reconstructed from the subscription metadata, so a NULL task session ID
does not prevent this destination from waking CoS. No new scheduler or queue exists.

After rollout, repair existing 004 under the CoS native secret scope:

```python
from management.native import Board
from management.incident_wake import repair_incident_wakes
repair_incident_wakes(Board(), "t_3c0ecce6")
```

This verifies the existing Slack root before subscribing. Newly added subscriptions
start at the current event cursor; old pre-fix failures are deliberately not replayed.
Inspect the current incident once after repair. Repeating repair preserves existing
unseen events and does not duplicate subscription rows.

Bounded acceptance: create a synthetic Support canary with `creator` set to 004,
request one native `kanban_block`, then confirm a real CoS gateway wake, current-card
inspection and a canonical-thread acknowledgement. CoS may complete the synthetic
canary directly; no production access, Telegram, retry loop or engineering work is
needed. Isolated native tests prove atomic inheritance, persisted blocked events
after database reopen, and idempotent subscription repair; live wake acceptance is
separate and must be performed by the parent executor after rollout.

### Incident summary context scope

Incident `summary_context` now returns only its completed/incomplete participant
records; `current_work` and `prior_notes` are empty. Weekly context retains company
work and historical management notes unchanged. No participant evidence is truncated.
Read-only measurement of actual 004 (`t_3c0ecce6`), using unchanged live source versus
staged fixed source against SQLite `mode=ro`: total serialized JSON fell from 76,784
to 8,211 bytes. All three completed participant records remained exactly 8,115 bytes;
incomplete remained empty. Removed unrelated current work accounted for 22,212 bytes
and weekly notes for 46,365 bytes. The regression first failed on leaked unrelated
work, then passed alongside the complete 57-test isolated native suite. No production
code, service or task state was changed during measurement.

### Missing parent argument and validation hints

Actual closure calls were JSON objects containing a nested incident contract but no
`parent_id`; the default empty ID reached `Board.task("")`, whose absent native task
then raised a root-level Pydantic error. This was not evidence of a stringified tool
call. The handler now requires a nonblank top-level `parent_id` before opening the
board for summary_context, incident_update, incident_close and weekly_close. Its
safe error identifies `parent_id` and explains that it is the native Kanban task ID
returned as `Cycle.parent`, not the incident identifier or nested incident object.
Start/team-status paths remain unchanged; schema field documentation makes this
requirement visible to the model. Four regression cases fail before the fix and
pass afterward. Independently, genuinely scalar/list/JSON-string inputs remain
rejected with JSON-object-required/no-stringify guidance rather than a thread hint;
no implicit JSON parsing was added. The combined native suite passes 65 tests.
