# Observability (cloud): Grafana Cloud + UptimeRobot

Cloud watches the homelab from outside and holds a copy of the key metrics. Local
Grafana stays the pager for in-house services. Each failure should page once.

## Roles

| Layer | Owns | Does not |
|---|---|---|
| Grafana Cloud (`yangjeep.grafana.net`, stack 1138088, ca-east-0) | "Home unreachable" paging, dead-man on federated metrics, LeaseLab alerts, external-view dashboard | Paging for services local Grafana already probes |
| UptimeRobot (Free) | Second-opinion HTTP checks on public endpoints, email + app push | Webhooks (Free has none), heartbeat |
| Alloy (new LXC on PVE) | Federate an allowlist from Prometheus `.216` and remote_write to cloud | Scraping exporters directly |

## Inventory (2026-11-11, read-only)

- Cloud `Homelab · 总览` (`homelab-overview-cloud`) queries local Prometheus live through PDC
  (`homelab-prometheus-pdc`). It goes dark when home is down.
- Cloud Prometheus holds only 32 series: nothing from home is remote-written yet.
- All cloud routes end at `hermes-alerts.yangjeep.net`. Hermes is `192.168.253.236` at home,
  behind Cloudflare. A whole-home outage cannot reach it, so home-down alerts need an
  out-of-band receiver.
- Out-of-band receiver: Grafana native **Telegram** contact point `homelab-oob-telegram`
  (decided 2026-11-11). The user enters the bot token and chat id in the Grafana UI, and scripts
  never carry them. Only critical "home unreachable" and dead-man alerts route there.
- Synthetics: no checks. Remote-write endpoint user `1993226`; push URL
  `https://prometheus-prod-32-prod-ca-east-0.grafana.net/api/prom/push`.
- UptimeRobot: Kuma HTTPS ingress, LeaseLab www / storefront / ops / production app,
  `manage.rentwithalda` paused.
- Local Grafana `.228` (13.3): Prometheus, Loki and InfluxDB only. No Infinity plugin, no LeaseLab.

## Applied (2026-11-11)

- Synthetics: job `homelab-ingress`, checks `https://kuma-home.yangjeep.net/` (200/302) and
  `https://hermes-alerts.yangjeep.net/health` (200). Probes Montreal and NorthVirginia, every 2 min
  (about 86k executions a month, under the Free 100k).
- [`grafana-cloud.js`](grafana-cloud.js) (paste into the console on the cloud origin; it is idempotent):
  - Rules `hl-cloud-federate-deadman` and `hl-cloud-home-unreachable` in folder `homelab-cloud`, all
    labelled `oob=true`.
  - A first-position policy route `oob=true` sends those alerts to `homelab-oob-telegram`
    (Telegram bot `@yangjeep_uptime_kuma_bot`, created 2026-11-11; the user entered the token in the UI).
  - Dashboard `homelab-external-cloud` reads only `grafanacloud-prom`.
- Alloy LXC 918 `alloy` (192.168.253.206) runs with token `alloy-lxc-918` (policy `homelab-alloy-write`).
  The token lives in 1Password as "Grafana Cloud API key - Alloy" and is piped into
  `/etc/default/alloy` as `GC_PROM_TOKEN` with `op read`. Cloud receives 133 series; `up{job="prometheus"}` is 1.

Finding (deferred: Hermes has its own patrol; its Synthetics check is disabled, not deleted): from the internet, `hermes-alerts.yangjeep.net` times out after TLS, and
`immich.yangjeep.net` returns 530. Local blackbox probes stay green because they use LAN
addresses. Cloud alerts routed to Hermes may not be delivered until the tunnel ingress is fixed.

Tests: `node --test observability/cloud/grafana-cloud.test.js`

## LeaseLab on local Grafana

Applied 2026-11-11 from [`../leaselab-local/`](../leaselab-local/). Four boards are exported from cloud with
uids unchanged (`leaselab-cloudflare-workers`, `leaselab-production`, `leaselab-preview`,
`leaselab-prod`) and file-provisioned into folder `LeaseLab` on `.228`. The Infinity plugin is
installed with `grafana cli`. The single datasource `leaselab-cloudflare-newacct` reads its bearer
token from `/etc/grafana/secrets/leaselab-cf-token`. That token is the leaselab account token
`grafana-local-leaselab-analytics-ro` (Account Analytics Read plus zone Analytics Read), piped in
from 1Password. Search Console (`leaselab-gsc`, `leaselab-seo`) stays cloud-only. Cloud keeps the
LeaseLab alerts; local is dashboards only.

Deploy: copy `provisioning/*/leaselab.yml` into `/etc/grafana/provisioning/` and `dashboards/*.json`
into `/var/lib/grafana/dashboards/leaselab/` on LXC 910, then restart `grafana-server`.

Hermes reads cloud Grafana through `endpoints.grafana_cloud` in `/etc/homelab-mcp/settings.json`.
It uses the token of service account `homelab-hermes-cloud-reader` (Viewer), which lives in
1Password as "Grafana Cloud hermes-cloud-reader". It was replaced on 2026-11-11 because the old
token returned 401.

## Alloy LXC

No Alloy script exists in community-scripts/ProxmoxVE. Use `ct/debian.sh`, then install `alloy`
from the Grafana apt repo, so the community `update-lxcs` tool upgrades it with everything else.
Config: [`alloy/config.alloy`](alloy/config.alloy).
