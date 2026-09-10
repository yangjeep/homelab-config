# Networking

## Cloudflare Tunnel isolation model

Internet-exposed applications use a dedicated `cloudflared` sidecar per stack. Each stack separates three network roles:

- `lab_egress`: normal Docker bridge used by the application for LAN/API access. It is the application's default gateway. Docker SNAT sends this traffic out through the Raspberry Pi's lab-facing interface; on the current host, UniFi therefore sees source `192.168.253.130` and applies the `lab` zone policy.
- `tunnel_link`: `internal: true` Docker bridge shared only by the application and its `cloudflared` sidecar. It carries origin traffic but has no host/LAN egress.
- `dmz_vlan`: external macvlan attached only to `cloudflared`. It is the `cloudflared` default gateway via `gw_priority: 1`.

The application is intentionally **not** attached directly to a lab macvlan. Docker macvlan isolates containers from the parent host by default, which would make host-local monitoring and dashboard integrations harder. Using a bridge for `lab_egress` preserves normal Pi-host reachability while still giving application traffic the Pi's `lab` network identity at the UniFi firewall.

`cloudflared` is never attached to `lab_egress`. Its only application-facing path is `tunnel_link`, and its only external path is `dmz_vlan`. This is the actual DMZ boundary.

Current DMZ connector addresses:

| Stack | DMZ address |
| --- | --- |
| Uptime Kuma | `10.25.254.130` |
| Beszel | `10.25.254.131` |
| Homepage | `10.25.254.132` |

## External `dmz_vlan`

The Compose stacks reference `dmz_vlan` as an external Docker network. The verified UniFi `lab-DMZ` and Raspberry Pi Docker network definition is:

```text
network: dmz_vlan
driver: macvlan
parent: end0.254
subnet: 10.25.254.0/24
gateway: 10.25.254.254
```

Recreate it after a host rebuild with:

```bash
docker network create \
  --driver macvlan \
  --subnet 10.25.254.0/24 \
  --gateway 10.25.254.254 \
  --opt parent=end0.254 \
  dmz_vlan
```

The VLAN subinterface must already exist before creating the Docker network.

## Post-deploy verification

### Application egress should use the lab identity

For Uptime Kuma, verify a LAN destination while capturing on the Pi:

```bash
sudo tcpdump -ni end0 'icmp and host <LAN target>'
docker exec uptime-kuma ping -c 2 <LAN target>
```

Expected on the Pi's lab interface:

```text
192.168.253.130 > <LAN target>: ICMP echo request
```

That confirms Docker SNAT is presenting application traffic as the Pi's `lab` address, so UniFi `lab -> ...` policy applies (including `lab -> IoT`).

### cloudflared egress must use the DMZ

For each `cloudflared` container, verify that public egress uses the DMZ address:

```bash
PID=$(docker inspect -f '{{.State.Pid}}' cloudflared-uptimekuma)
sudo nsenter -t "$PID" -n ip route
sudo nsenter -t "$PID" -n ip route get 1.1.1.1
sudo nsenter -t "$PID" -n ip route get 198.41.192.167
```

Verified on Uptime Kuma's connector:

```text
default via 10.25.254.254 dev eth1
10.25.254.0/24 dev eth1 proto kernel scope link src 10.25.254.130
172.31.0.0/24 dev eth0 proto kernel scope link src 172.31.0.2
1.1.1.1 via 10.25.254.254 dev eth1 src 10.25.254.130
198.41.192.167 via 10.25.254.254 dev eth1 src 10.25.254.130
```

This confirms both generic Internet traffic and Cloudflare edge traffic leave through the DMZ interface, not through the Pi's lab address.

A lab destination attempted from the `cloudflared` namespace should be blocked by the UniFi `DMZ -> lab` policy, while the application itself can reach destinations allowed by `lab` policy.
