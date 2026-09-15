#!/bin/bash
# Install reviewed local files only; identity provisioning and timer activation are separate.
set -euo pipefail
umask 077
test "$(id -u)" -eq 0
cd -- "$(dirname -- "$0")"
install -d -m 700 /etc/leaselab-backup/templates /var/lib/leaselab-backup/staging /var/lib/leaselab-backup/keys
# Traversable parent; each native staging child is 0700 owned by Hermes.
install -d -m 711 /var/lib/leaselab-backup-staging
install -m 600 excludes gitleaks.toml ssh_config verify.py /etc/leaselab-backup/
install -m 600 templates/README.md templates/.gitignore /etc/leaselab-backup/templates/
install -m 700 candidate.sh /etc/leaselab-backup/candidate.sh
install -m 700 knowledge.sh /usr/local/sbin/leaselab-knowledge-backup
install -m 700 full.sh /usr/local/sbin/leaselab-full-backup
install -m 644 leaselab-*-backup.service leaselab-*-backup.timer /etc/systemd/system/
systemctl daemon-reload
