# LeaseLab host and service telemetry

LXC 916 exposes Debian node exporter 1.9.0 on its private address 192.168.253.217:9100. Prometheus on LXC 914 scrapes it every 30 seconds under `job="observability-node",host="hermes-leaselab"`. Run `sh install.sh` inside 916 from this directory. No credentials are required.

The systemd collector explicitly includes only company gateway, GitHub broker, and the knowledge/full backup services and timers. Default node metrics cover CPU, memory, filesystem and networking. Raw Hermes journal output is not forwarded: it can contain model/user content. The company aggregate collector below adds lifecycle counts and role spend. Trusted QA and deployment evidence remain separate work.

Useful PromQL:

```promql
up{host="hermes-leaselab"}
node_systemd_unit_state{host="hermes-leaselab",state="failed"}
node_systemd_unit_state{host="hermes-leaselab",state="active",name=~".*timer|.*gateway.service|.*broker.service"}
node_systemd_service_restart_total{host="hermes-leaselab"}
node_systemd_timer_last_trigger_seconds{host="hermes-leaselab"}
```

A completed oneshot backup is normally inactive. Timer last-trigger zero means it has not yet fired; manually invoking the backup service does not advance that timestamp. These metrics expose scheduling and service failure, not independent proof of backup integrity. Restore evidence belongs to the backup runbook.

The source scrape entry is in `homelab-mcp/observability/prometheus/backend/observability-nodes-scrape.yml`. Catalog entry `guest-916` is partial coverage and carries native PVE ID `lxc/916`. Existing Grafana Prometheus datasource queries these series; the company dashboard below uses that datasource. No new alert rules were added.

Rollback: disable `prometheus-node-exporter` on 916, remove its target from Prometheus and reload. Original scrape configuration is preserved on 914 at `/root/observability-nodes.pre-leaselab.yml`; original catalog textfile is preserved on 911 at `/root/catalog.pre-leaselab.prom`. Regenerate catalog artifacts after removing `guest-916` if rolling back inventory. Network-online ordering and restart-on-failure prevent exporter failure during guest boot address assignment.

## Company aggregates

`sh install-company-metrics.sh` installs `leaselab-company-metrics.service` and enables `leaselab-company-metrics.timer`. It runs after two minutes at boot and every five minutes thereafter, with up to 15 seconds of jitter. It reuses the installed Hermes Python runtime and dependencies; it does not install a new stack.

The trusted root service reads only aggregate assignee/status/count rows from `/var/lib/leaselab-company/kanban/boards/leaselab-company/kanban.db` in SQLite read-only mode (3-second lock timeout). Seven known roles and nine lifecycle states are fixed; unexpected labels and unassigned roles become `other`. There are no task IDs, titles, bodies, users, Slack messages, issue descriptions, model prompts or result payloads in metrics.

For each role, its existing `.env` key is loaded without interpolation and used only in an in-memory Authorization header to `https://openrouter.ai/api/v1/key`. The request does not use a management credential. HTTP redirects and environment proxy settings are disabled, connect timeout is five seconds, I/O timeout ten seconds, no retries, response size limit 64 KiB, and the whole systemd job has a 120-second deadline. The existing httpx dependency is deliberately reused. Provider metadata and key labels are discarded; only finite nonnegative usage values and the non-management credential check are parsed. Keys never enter command arguments, files produced by the collector, or logs.

Output is atomically replaced at `/var/lib/prometheus/node-exporter/leaselab-company.prom` (0644). Persistent source last-success timestamps and cumulative failed-poll counts are in `/var/lib/leaselab-company-metrics/state.json` (0600). Failed sources omit their current data, publish success=0, increment failure count, and retain the previous last-success timestamp. A killed or broken collector leaves the last completed timestamp unchanged, making stale output detectable. These collection failure counts are not model request failures.

```promql
leaselab_openrouter_usage_usd{host="hermes-leaselab",period="monthly"}
leaselab_kanban_tasks{host="hermes-leaselab"}
leaselab_company_source_success{host="hermes-leaselab"}
time() - leaselab_company_source_last_success_seconds{host="hermes-leaselab"}
time() - leaselab_company_metrics_completed_seconds{host="hermes-leaselab"} > 900
increase(leaselab_company_source_failures_total{host="hermes-leaselab"}[1h])
```

Usage is a gauge because daily/monthly values reset and key rotation changes lifetime attribution. Summing monthly usage covers the seven current runtime keys, not deleted/retired historical keys or an independent measurement of workspace hard-cap enforcement. Exact SHA, issue/PR, QA, review and deployment evidence stays in GitHub/Kanban; this collector does not invent those results.

Rollback: `systemctl disable --now leaselab-company-metrics.timer`; stop the oneshot if running; remove `/var/lib/prometheus/node-exporter/leaselab-company.prom`. Credentials and Hermes state are unchanged. The exporter remains usable for host/service telemetry.

## Grafana company dashboard

`leaselab-company.json` provisions **AI - LeaseLab Company** with UID `leaselab-company` in the existing **90 - Observability** folder. It shows exporter/gateway state, collection health and age, seven-role monthly spend, Kanban lifecycle totals, collection failures and backup timer state. Copy it to `/var/lib/grafana/dashboards/homelab/90 - Observability/leaselab-company.json` on Grafana LXC910; the existing file provider reloads within 60 seconds. No datasource credential changes are needed. Remove only this new provisioned JSON to roll back the file; the provider has disableDeletion enabled, so remove the saved dashboard through Grafana if a full rollback is intended.

No data renders as UNKNOWN, never a synthetic healthy zero. Monthly spend is explicitly current-key usage; workspace budget enforcement is independent. The dashboard does not represent unfinished QA/review/release gates as healthy.
