#!/bin/sh
set -eu
[ "$(id -u)" = 0 ]
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target=/usr/local/libexec/leaselab-company/publisher
[ -x /opt/leaselab-publisher-executor/venv/bin/python ]
for source in "$base"/verification*.py "$base"/review*.py "$base"/review-schema.json "$base"/publisher_files.py "$base"/publisher_jobs.py; do
  install -o root -g root -m 644 "$source" "$target/$(basename "$source")"
done
install -o root -g root -m 644 "$base/leaselab-verification@.service" /etc/systemd/system/
install -d -o root -g root -m 700 /var/lib/leaselab-publisher/verification-requests
systemctl daemon-reload
# No enable/start, App keys, role auth, sockets or merge capability.
