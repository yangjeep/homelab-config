# homelab-config

Reusable Docker Compose examples and configuration files for common homelab services.

Stacks on the Raspberry Pi (`pi4`):

| Stack | Managed by | Notes |
| --- | --- | --- |
| [uptimekuma](uptimekuma/) | Portainer stack | Status page + watchdog, Cloudflare Tunnel via DMZ |
| [beszel](beszel/) | Portainer stack | Host/container metrics, Cloudflare Tunnel via DMZ |
| [homepage](homepage/) | Portainer stack | Dashboard; config mounted from this repo's checkout on the Pi |
| [portainer](portainer/) | `docker compose` in `~/homelab-config/portainer` | HTTPS UI on 9443 only |
| [grafana-pdc](grafana-pdc/) | `docker compose` in `~/homelab-config/grafana-pdc` | Grafana Cloud PDC agent; needs `.env` from `.env.example` |

See [NETWORKING.md](NETWORKING.md) for the Cloudflare Tunnel / DMZ isolation model and verification steps.

Feel free to copy, adapt, and use any stack here for your own setup. Secrets and runtime data are excluded.
