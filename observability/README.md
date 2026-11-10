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

```
00 · 总览          Homelab · 总览 (homelab-home, org home dashboard, one screen)
10 · 子系统        网络 · 计算 · 家庭 (merged) · 入口 · 存储 · 供电 · 媒体 · 无线电 · 自动化
90 · Meta 与日志   Meta · 监控链健康与覆盖 (merged) · AI · 日志
99 · 归档          Old boards, unchanged except title prefix [旧] and tag archived
```

The new overview uses one status tile per triage component and does not hard-code signal counts.
A signal that existed in the last 24h but is gone now shows as **未知 / 过期**.
Severity order: 严重 > 未知 > 警告 > 正常.

Merged boards are built from their sources. Each source becomes a row, and text panels are dropped.
Kept boards keep their uid, so links from Homepage and Hermes still work.

## Apply

Both scripts are idempotent. They default to a **dry run** that prints every write without making it.

1. Open Grafana as admin, open the DevTools console and paste `grafana/revamp.js`. Read the plan.
   Then run `globalThis.REVAMP_APPLY = true` and paste the script again.
2. Open Kuma, then do the same with `kuma/revamp.js`.

Order matters. The Grafana script adds `P2 · Service HTTP probe down`. That rule takes over paging before Kuma notifications are removed.

## Rollback

- **Dashboards:** originals are in `99 · 归档`, and every save also lands in Grafana version history. To roll back, move a board out of the archive folder, or restore an earlier version.
- **Home dashboard:** Administration → Default preferences.
- **Alert rule:** delete `hl-service-probe-down`.
- **Kuma:** restore notifications on a monitor's edit page. Take a Kuma backup first (Settings → Backup).

## Tests

```bash
node --test observability/grafana/revamp.test.js observability/kuma/revamp.test.js
```

## Known gaps

- Dashboards are still stored in Grafana's DB, not file-provisioned. Nobody has shell access to `.228` from here. Next step: export to `grafana/dashboards/*.json` and switch to file provisioning.
- The `homelab-triage` recording rules on `.216` are unchanged. The overview works around missing signals in queries.
- The Kuma status page `homelab` is not rebuilt yet. Regroup it in the UI after the script runs.
