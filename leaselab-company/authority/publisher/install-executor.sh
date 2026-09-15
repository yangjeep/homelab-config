#!/bin/bash
# Root-only installation of the bounded synthetic executor. Does not enable services.
set -euo pipefail
[ "$(id -u)" = 0 ] || exit 1
if [ ! -x /opt/leaselab-publisher-executor/venv/bin/pip ]; then
 apt-get install -y python3-venv
 python3 -m venv /opt/leaselab-publisher-executor/venv
fi
/opt/leaselab-publisher-executor/venv/bin/pip -q install 'pydantic==2.12.5'
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
executor_code=/usr/local/libexec/leaselab-company/publisher
native_codex=/usr/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex
[ "$("$native_codex" --version)" = 'codex-cli 0.154.0' ] || exit 1
for role in reviewer qa-security; do
 case "$role" in reviewer) identity=leaselab-review-exec;; qa-security) identity=leaselab-qa-exec;; esac
 executor_root=/var/lib/leaselab-publisher/executor/$role
 if ! id "$identity" >/dev/null 2>&1; then
  useradd --system --user-group --no-create-home --home-dir "$executor_root/home" --shell /usr/sbin/nologin "$identity"
 fi
 [ "$(getent passwd "$identity" | cut -d: -f6)" = "$executor_root/home" ] || exit 1
 [ "$(getent passwd "$identity" | cut -d: -f7)" = /usr/sbin/nologin ] || exit 1
 [ "$(id -G "$identity" | wc -w)" -eq 1 ] || exit 1
 install -d -o root -g root -m 755 /var/lib/leaselab-publisher /var/lib/leaselab-publisher/executor
 install -d -o root -g "$identity" -m 750 "$executor_root" "$executor_root/work"
 install -d -o "$identity" -g "$identity" -m 700 "$executor_root/home" "$executor_root/home/.codex"
 if [ ! -e "$executor_root/home/.codex/auth.json" ]; then
  printf '%s\n' '{"OPENAI_API_KEY":"synthetic-not-a-real-key"}' > "$executor_root/home/.codex/auth.json"
  chown "$identity:$identity" "$executor_root/home/.codex/auth.json"
  chmod 600 "$executor_root/home/.codex/auth.json"
 fi
done
install -d -o root -g root -m 700 /var/lib/leaselab-publisher/evidence
install -d -o root -g root -m 755 "$executor_code" "$executor_code/executor-config"
for file in "$source_dir"/executor*.py "$source_dir"/publisher_models.py; do
 install -o root -g root -m 644 "$file" "$executor_code/"
done
install -o root -g root -m 644 "$source_dir"/executor-config/* "$executor_code/executor-config/"
sha256sum "$native_codex" | cut -d ' ' -f 1 > "$executor_code/codex.sha256"
chmod 644 "$executor_code/codex.sha256"
install -o root -g root -m 644 "$source_dir/leaselab-publisher-canary@.service" /etc/systemd/system/
systemctl daemon-reload
