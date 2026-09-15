#!/bin/bash
# Install code and account isolation only. Never fetch keys or start the broker.
set -euo pipefail
[[ $(id -u) == 0 ]]
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
roles=(chief-of-staff support growth qa-security reviewer sre engineer)
for role in "${roles[@]}"; do getent passwd "leaselab-$role" >/dev/null; done
getent group leaselab-github-clients >/dev/null || groupadd --system leaselab-github-clients
getent passwd leaselab-github-broker >/dev/null || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin --gid leaselab-github-clients leaselab-github-broker
[[ $(id -u leaselab-github-broker) != 0 ]]
# Replace supplementary membership; this group grants only broker socket access.
members=$(IFS=,; echo "${roles[*]/#/leaselab-}")
gpasswd -M "$members" leaselab-github-clients >/dev/null
install -d -o root -g root -m 755 /usr/local/libexec/leaselab-company/github-broker
install -o root -g root -m 644 "$source_dir/"{policy,upstream,broker,credential_helper,gh_client}.py /usr/local/libexec/leaselab-company/github-broker/
install -d -o root -g root -m 755 /usr/local/bin
cat > /usr/local/bin/leaselab-git-credential <<'WRAPPER'
#!/bin/sh
exec /usr/bin/python3 -I /usr/local/libexec/leaselab-company/github-broker/credential_helper.py "$@"
WRAPPER
chown root:root /usr/local/bin/leaselab-git-credential
chmod 755 /usr/local/bin/leaselab-git-credential
cat > /usr/local/bin/leaselab-gh <<'WRAPPER'
#!/bin/sh
exec /usr/bin/python3 -I /usr/local/libexec/leaselab-company/github-broker/gh_client.py "$@"
WRAPPER
chown root:root /usr/local/bin/leaselab-gh
chmod 755 /usr/local/bin/leaselab-gh
install -d -o leaselab-github-broker -g leaselab-github-clients -m 700 /etc/leaselab-company/github
# Existing company parent is root:hermes 0750. Grant only broker traversal.
command -v setfacl >/dev/null
setfacl -m u:leaselab-github-broker:--x /etc/leaselab-company
install -o root -g root -m 644 "$source_dir/leaselab-github-broker.service" /etc/systemd/system/
systemctl daemon-reload
