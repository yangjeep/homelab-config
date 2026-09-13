# Apps Script execution observer

This collector reads execution metadata from the official Apps Script Processes API with the
`https://www.googleapis.com/auth/script.processes` scope. It never reads parameters, source,
document content, or user data.

The OAuth bearer is sent only to the fixed official
`https://script.googleapis.com/v1/processes:listScriptProcesses` endpoint; the production runtime
does not accept an API URL override. Each run requests at most 20 pages and 1,000 records, uses a
seven-day initial lookback, and then
re-reads a 10-minute overlap. Pending executions extend that window back to their start time for at
most seven days, preventing a long run from disappearing behind a newer cursor while keeping state
bounded. A script's cursor advances to the request time only after every requested page has been
validated. The global success timestamp advances only after all scripts succeed. HTTP responses
are capped at 2 MiB, 429 responses are retried twice, and Retry-After is capped at 10 seconds.

SQLite keeps execution detail for 30 days, which is longer than the seven-day API lookback and the
24-hour dashboard window. A transactional migration converts existing terminal rows into
fixed-cardinality lifetime aggregates before eligible detail is pruned. Lifetime execution counts,
duration sums/counts, histogram buckets, and per-script last-success timestamps therefore remain
monotonic without rescanning retained history. Delivered outbox rows and their terminal detail are
pruned together; undelivered rows are retained. At most 1,000 outbox events are emitted per run, and
new terminal batches are rolled back with collection backpressure when the pending outbox is full,
rather than silently dropping journal events. Persistent stdout/journald failure can retain up to
that cap and pause new terminal ingestion until delivery resumes.

An execution key is the SHA-256 of the configured script alias, function name, process type, and
start time. Google does not return a process ID or script ID in each Process object, so two
executions with all four fields equal are indistinguishable. The timestamp normally has sub-second
precision, which makes this collision unlikely but not impossible.

Only a terminal transition increments execution counters. A RUNNING execution can therefore be
re-read and later counted once as COMPLETED or FAILED. Journal events use the same execution key
and an at-least-once outbox: a crash after journald accepts the line but before SQLite marks it sent
can duplicate one line, while a crash before logging cannot lose it. Loki queries can deduplicate
on `execution_key` when exact event counts are needed.

## Private configuration

Install the OAuth Desktop client JSON and refresh-token JSON outside Git. Both files and their parent
directory must be readable only by the service account. Copy the environment example to
`/etc/apps-script-observer.env`, set the private paths and `alias=script_id` mapping, then set mode
0600. Script IDs never appear in metrics or logs; metrics use the stable configured alias.

No alert SLA is assumed for Gmail Cleaner. The included dashboard shows collector freshness,
24-hour executions, success rate, failures, timeouts, execution types, the slowest scripts,
bounded-histogram p50 and p95 durations, recent execution metadata, and each script's most recent
successfully completed execution. Failed polls or failed executions never advance that
execution-success timestamp. Alert thresholds should be chosen after an actual execution baseline
exists.

## Runtime layout

Create the `apps-script-observer` system user, add it to 911's existing `truenas-exporter` group,
install this package at `/opt/apps-script-observer`, and install the supplied service and timer
under `/etc/systemd/system`. The timer runs every five minutes. Metrics are atomically written to
the verified `/var/lib/prometheus/node-exporter` textfile directory, while compact terminal
metadata goes to journald for the existing Alloy/Loki pipeline.

The Alloy snippet selectively forwards only `homelab_apps_script_*` metrics and compact terminal
execution journal events to Grafana Cloud. It uses a dedicated private token file at
`/etc/alloy/grafana-cloud-write-token`; all other node-exporter metrics and journal events are
dropped before the Cloud writers. Local collection does not depend on Grafana Cloud.

The current OAuth consent grant is in Google Testing mode. It proves the live integration but its
refresh token is expected to expire after seven days. Publish the consent configuration or replace
the grant with an approved durable credential before treating this collector as unattended
long-term coverage; until then, alert on collector freshness rather than assuming permanence.

## Verification

Run the local suite with:

```sh
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run basedpyright
PYTHONPATH=src uv run pytest
```

After private OAuth authorization is complete, a deployment is accepted only after a real API run
returns at least one execution, creates a nonempty `.prom` file, and a second run proves that the
same terminal execution is not emitted again.
