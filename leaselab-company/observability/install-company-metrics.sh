#!/bin/sh
# Run inside LXC 916 from this directory; reuses the installed Hermes runtime.
set -eu
install -d -m 755 /usr/local/libexec/leaselab-company-metrics /var/lib/prometheus/node-exporter
install -d -m 700 /var/lib/leaselab-company-metrics
install -m 644 company_metrics.py /usr/local/libexec/leaselab-company-metrics/company_metrics.py
install -m 644 leaselab-company-metrics.service leaselab-company-metrics.timer /etc/systemd/system/
install -m 644 node-exporter.env /etc/default/prometheus-node-exporter
systemctl restart prometheus-node-exporter

systemctl daemon-reload
systemctl enable --now leaselab-company-metrics.timer
systemctl start leaselab-company-metrics.service
