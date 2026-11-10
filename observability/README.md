# Observability (local): Grafana + Uptime Kuma

Source of truth for how the local monitoring stack is organized. Cloud monitoring is a later phase.

## Roles

| Layer | Owns | Does not |
|---|---|---|
| Prometheus + blackbox (`192.168.253.216`) | All metrics and HTTP/DNS/ICMP probes | — |
| Grafana (`192.168.253.228:3000`) | Dashboards and **the only pager** (Hermes on-call webhook) | — |
| Uptime Kuma (`pi4`, `kuma-home.yangjeep.net`) | Human-facing status, plus a **watchdog on the monitoring chain** (Prometheus, Grafana, Loki, InfluxDB) | Paging for anything Prometheus already probes |

Each failure should page once. Before this change Kuma and Grafana both paged for the same media, edge, HA, PVE and TrueNAS outages.

## Grafana layout

Live state after the 2026-11-10 run:

```
00 · Overview          Homelab · Overview (homelab-home, org home dashboard, one screen)
Homelab · 基础设施      file-provisioned boards (unchanged, names owned by files) + UniFi UDM cooling
Homelab · 家庭与服务    file-provisioned boards (unchanged, names owned by files) + HA automation runs, Home · Temperature & Air
```

17 boards are owned by **classic file provisioning** on the Grafana host, under
`/var/lib/grafana/dashboards/homelab/<NN - 分类>/*.json`. Grafana re-applies their title and folder
every 60s, so API moves and retitles revert. The script detects these through the
`grafana.app/managedBy` annotation and skips them, including any merge that has a file-managed source.

Target layout (`MERGES` / `KEEP` in `grafana/revamp.js`) is applied in the provisioning files:

```
00 · Overview        Homelab · Overview
10 · Subsystems      Network (WAN+UniFi+UDM) · Compute (PVE+IPMI) · Home (HA+automation+environment) · Edge · Storage · Power · Media · Radio · Automation
90 · Meta & Logs     Meta (Health+Coverage) · AI · Logs
99 · Archive         NOC, Availability, old overview
```

The new overview uses one status tile per triage component and does not hard-code signal counts.
A signal that existed in the last 24h but is gone now shows as **Unknown / stale**.
Severity order: Critical > Unknown > Warning > OK.

Merged boards are built from their sources. Each source becomes a row, and text panels are dropped.
Kept boards keep their uid, so links from Homepage and Hermes still work.

## Apply

Both scripts are idempotent. They default to a **dry run** that prints every write without making it.

1. Open Grafana as admin, open the DevTools console and paste `grafana/revamp.js`. Read the plan.
   Then run `globalThis.REVAMP_APPLY = true` and paste the script again.
2. Open Kuma, then do the same with `kuma/revamp.js`.

Order matters. The Grafana script adds `P2 · Service HTTP probe down`. That rule takes over paging before Kuma notifications are removed.

## Rollback

- **Dashboards:** the archived old overview (`homelab-overview-local`) and the archive folder were deleted on 2026-11-10. Restore them from Dashboards → Recently deleted while Grafana still retains them. Every other save is in Grafana version history.
- **Home dashboard:** Administration → Default preferences.
- **Alert rule:** delete `hl-service-probe-down`.
- **Kuma:** Kuma 2 has no backup feature. `kuma/snapshot-before-2026-11-10.json` records the previous names, parents, retries and notifications. Restore from it on each monitor's edit page.

## Tests

```bash
node --test observability/grafana/revamp.test.js observability/kuma/revamp.test.js
```

## Known gaps

- UI text is English. Exceptions: the 17 file-provisioned boards and their two folder names (owned by files on `.228`), and the triage `component` / `signal` label values (owned by the Prometheus rules on `.216`), which still show Chinese in the abnormal-signals table.

- Folder restructure and merges for the 17 file-provisioned boards are not applied. They need shell access to the Grafana host (`.228`). Steps there:
  1. Move and merge the JSON files under `/var/lib/grafana/dashboards/homelab/`.
  2. Remove NOC and Availability from the provisioned set.
  3. Copy the provisioning tree into this repo so it becomes the source of truth.
- The `homelab-triage` recording rules on `.216` are unchanged. The overview works around missing signals in queries.
- The Kuma status page `homelab` is not rebuilt yet. Regroup it in the UI after the script runs.
