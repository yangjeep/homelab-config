#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) = 0 && $(hostname) = hermes-leaselab ]] || exit 1
src=$(cd "$(dirname "$0")" && pwd)
dest=/usr/local/libexec/leaselab-company/github-tools
profile=/var/lib/leaselab-company/profiles/chief-of-staff
install -d -m 755 "$dest"
install -m 644 "$src"/*.py "$src/plugin.yaml" "$dest/"
key=/etc/leaselab-company/ssh/chief-of-staff
if [[ ! -e $key ]]; then
  ssh-keygen -q -t ed25519 -N '' -C leaselab-chief-of-staff-github -f "$key"
fi
chown root:hermes "$key"
chmod 640 "$key"
keyfile=/etc/ssh/authorized_keys/leaselab-chief-of-staff
{ printf '%s ' 'restrict,from="127.0.0.1",command="/usr/bin/python3 -I /usr/local/libexec/leaselab-company/github-tools/runner.py"'; cat "$key.pub"; } > "$keyfile"
chown root:root "$keyfile"
chmod 644 "$keyfile"
printf '%s\n' 'AllowUsers leaselab-chief-of-staff' > /etc/ssh/sshd_config.d/01-leaselab-cos-github.conf
/usr/sbin/sshd -t
systemctl reload ssh
ln -sfn "$dest" "$profile/plugins/leaselab-company-github"
# Preserve all existing model, gateway, Slack and Kanban configuration.
/home/hermes/.hermes/hermes-agent/venv/bin/python - "$profile/config.yaml" <<'PY'
import os
import sys
from pathlib import Path
import yaml
path = Path(sys.argv[1])
stat = path.stat()
data = yaml.safe_load(path.read_text())
name = 'leaselab-company-github'
plugins = data.setdefault('plugins', {}).setdefault('enabled', [])
if name not in plugins:
    plugins.append(name)
for tools in data['platform_toolsets'].values():
    if name not in tools:
        tools.append(name)
temporary = path.with_suffix('.yaml.github-new')
temporary.write_text(yaml.safe_dump(data, sort_keys=False))
os.chown(temporary, stat.st_uid, stat.st_gid)
os.chmod(temporary, stat.st_mode & 0o777)
os.replace(temporary, path)
PY
printf '%s\n' 'CoS GitHub tool installed. Install reviewed guard and restart gateway separately.'
