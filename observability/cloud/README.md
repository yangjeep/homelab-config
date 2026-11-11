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
  - A first-position policy route `oob=true` sends those alerts to `homelab-oob-telegram`. Until that
    contact point exists, it falls back to Hermes Critical.
  - Dashboard `homelab-external-cloud` reads only `grafanacloud-prom`.
- Alloy LXC 918 `alloy` (192.168.253.206) is installed but not started yet; it waits on the token.

Finding: from the internet, `hermes-alerts.yangjeep.net` times out after TLS, and
`immich.yangjeep.net` returns 530. Local blackbox probes stay green because they use LAN
addresses. Cloud alerts routed to Hermes may not be delivered until the tunnel ingress is fixed.

Tests: `node --test observability/cloud/grafana-cloud.test.js`

## LeaseLab on local Grafana

The five LeaseLab boards (`leaselab-cloudflare-workers`, `leaselab-production`, `leaselab-preview`,
`leaselab-prod`, `leaselab-seo`) use two datasources only: `leaselab-cloudflare-newacct`
(Infinity, bearer token, `api.cloudflare.com`) and `leaselab-gsc` (Infinity, OAuth2 JWT service
account, Search Console). Recreate both locally with the **same uids** so dashboard JSON imports
unchanged. Secrets are entered by the user in the local UI. Cloud keeps the LeaseLab alerts; local
is dashboards only.

## Alloy LXC

No Alloy script exists in community-scripts/ProxmoxVE. Use `ct/debian.sh`, then install `alloy`
from the Grafana apt repo, so the community `update-lxcs` tool upgrades it with everything else.
Config: [`alloy/config.alloy`](alloy/config.alloy).
