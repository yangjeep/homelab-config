# Networking

## Cloudflare Tunnel isolation model

Internet-exposed applications use a dedicated `cloudflared` sidecar per stack. Each stack separates three network roles:

- `app_egress`: normal Docker bridge used by the application for LAN/API access. It is the application's default gateway.
- `tunnel_link`: `internal: true` Docker bridge shared only by the application and its `cloudflared` sidecar. It carries origin traffic but has no host/LAN egress.
- `dmz_vlan`: external macvlan attached only to `cloudflared`. It is the `cloudflared` default gateway via `gw_priority: 1`.

This keeps Cloudflare connector egress on the DMZ instead of silently falling back to the Docker host's LAN interface, while applications such as Uptime Kuma, Beszel, and Homepage retain the internal reachability they need.

Current DMZ connector addresses:

| Stack | DMZ address |
| --- | --- |
| Uptime Kuma | `10.25.254.130` |
| Beszel | `10.25.254.131` |
| Homepage | `10.25.254.132` |

## External `dmz_vlan`

The Compose stacks reference `dmz_vlan` as an external Docker network. On the Raspberry Pi it is currently a macvlan on VLAN 254:

```text
network: dmz_vlan
driver: macvlan
parent: end0.254
subnet: 10.25.254.0/24
gateway: 10.25.254.1
```

Recreate it after a host rebuild with:

```bash
docker network create \
  --driver macvlan \
  --subnet 10.25.254.0/24 \
  --gateway 10.25.254.1 \
  --opt parent=end0.254 \
  dmz_vlan
```

The VLAN subinterface must already exist before creating the Docker network.

## Post-deploy verification

For each `cloudflared` container, verify that public egress uses the DMZ address:

```bash
PID=$(docker inspect -f '{{.State.Pid}}' cloudflared-uptimekuma)
sudo nsenter -t "$PID" -n ip route
sudo nsenter -t "$PID" -n ip route get 1.1.1.1
```

Expected route for Uptime Kuma:

```text
default via 10.25.254.1 ...
1.1.1.1 via 10.25.254.1 ... src 10.25.254.130
```

The application should retain LAN reachability through `app_egress`, while `cloudflared` traffic to LAN destinations should be subject to the UniFi DMZ firewall policy.
