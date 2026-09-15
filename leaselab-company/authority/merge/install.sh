#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || exit 1
getent passwd leaselab-reviewer >/dev/null
command -v uv >/dev/null
command -v setfacl >/dev/null
[ -f /usr/local/libexec/leaselab-company/github-broker/upstream.py ]
getent group leaselab-merge >/dev/null || groupadd --system leaselab-merge
getent passwd leaselab-merge >/dev/null || useradd --system --gid leaselab-merge --no-create-home --shell /usr/sbin/nologin leaselab-merge
[ "$(id -u leaselab-merge)" != 0 ]
[ "$(id -u leaselab-merge)" != "$(id -u leaselab-reviewer)" ]
gpasswd -M leaselab-reviewer leaselab-merge >/dev/null
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -d -o root -g root -m 0755 /usr/local/lib/leaselab-merge
for file in merge_models.py merge_policy.py merge_transport.py merge_server.py merge_client.py; do
    install -o root -g root -m 0644 "$src/$file" /usr/local/lib/leaselab-merge/
done
uv venv /usr/local/lib/leaselab-merge/venv
uv pip install --python /usr/local/lib/leaselab-merge/venv/bin/python 'pydantic>=2.10,<3'
install -d -o root -g leaselab-merge -m 0750 /etc/leaselab-company/merge
setfacl -m u:leaselab-merge:--x /etc/leaselab-company
install -o root -g root -m 0644 "$src/leaselab-merge.service" /etc/systemd/system/
cat > /usr/local/bin/leaselab-merge-pr <<'WRAPPER'
#!/bin/sh
exec /usr/local/lib/leaselab-merge/venv/bin/python -I /usr/local/lib/leaselab-merge/merge_client.py "$@"
WRAPPER
chown root:root /usr/local/bin/leaselab-merge-pr
chmod 0755 /usr/local/bin/leaselab-merge-pr
systemctl daemon-reload
printf '%s\n' 'Installed, not enabled. Provision reviewed policy and service-owned PEM separately.'
