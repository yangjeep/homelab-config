#!/bin/sh
# Run inside LXC 916 as root with this directory as the current directory.
set -eu
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends prometheus-node-exporter
install -m 644 node-exporter.env /etc/default/prometheus-node-exporter
install -d -m 755 /var/lib/prometheus/node-exporter /etc/systemd/system/prometheus-node-exporter.service.d
install -m 644 network.conf /etc/systemd/system/prometheus-node-exporter.service.d/network.conf
systemctl daemon-reload
systemctl enable prometheus-node-exporter
systemctl restart prometheus-node-exporter
