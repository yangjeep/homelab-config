#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) = 0 && $(hostname) = hermes-leaselab ]] || exit 1
source_dir=$(cd "$(dirname "$0")/.." && pwd)
install -d -m 755 /usr/local/libexec/leaselab-company
install -m 755 "$source_dir/bootstrap/company-worker.sh" /usr/local/libexec/leaselab-company/company-worker.sh
install -m 755 "$source_dir/bootstrap/gateway-preflight.sh" /usr/local/libexec/leaselab-company/gateway-preflight.sh
install -m 644 "$source_dir/systemd/leaselab-company-gateway.service" /etc/systemd/system/leaselab-company-gateway.service
cd /home/hermes
runuser -u hermes -- env HOME=/home/hermes /home/hermes/.hermes/bin/uv pip install \
  --python /home/hermes/.hermes/hermes-agent/venv/bin/python 'python-telegram-bot[webhooks]==22.8'
loginctl enable-linger hermes
systemctl start user@1000.service
systemctl daemon-reload
printf '%s\n' 'Gateway installed. Provision private credentials and verify founder allowlist before enabling Telegram and starting the service.'
