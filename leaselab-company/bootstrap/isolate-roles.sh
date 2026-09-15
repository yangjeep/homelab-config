#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) = 0 ]] || { echo 'Run inside the dedicated company LXC as root.' >&2; exit 1; }
[[ $(hostname) = hermes-leaselab ]] || { echo 'Unexpected host; refusing.' >&2; exit 1; }
hermes=/home/hermes/.local/bin/hermes
[[ -x $hermes ]] || exit 1
install -d -m 700 -o hermes -g hermes /var/lib/leaselab-company
install -d -m 700 -o hermes -g hermes /var/lib/leaselab-company/profiles
if [[ ! -e /home/hermes/.hermes/profiles ]]; then
  ln -s /var/lib/leaselab-company/profiles /home/hermes/.hermes/profiles
fi
[[ $(readlink -f /home/hermes/.hermes/profiles) = /var/lib/leaselab-company/profiles ]] || exit 1
apt-get install -y openssh-server acl >/dev/null
install -d -m 750 -o root -g hermes /etc/leaselab-company /etc/leaselab-company/ssh
install -d -m 755 /etc/ssh/authorized_keys /srv/leaselab/roles
for role in chief-of-staff support sre engineer reviewer qa-security growth; do
  account="leaselab-$role"
  if ! id "$account" >/dev/null 2>&1; then
    useradd --create-home --home-dir "/srv/leaselab/roles/$role" --shell /bin/bash "$account"
  fi
  chmod 700 "/srv/leaselab/roles/$role"
  install -d -m 700 -o "$account" -g "$account" "/srv/leaselab/roles/$role/workspaces"
  setfacl -m u:hermes:rwx "/srv/leaselab/roles/$role" "/srv/leaselab/roles/$role/workspaces"
  setfacl -d -m u:hermes:rwx "/srv/leaselab/roles/$role/workspaces"
  if [[ ! -d /var/lib/leaselab-company/profiles/$role ]]; then
    runuser -u hermes -- env HOME=/home/hermes "$hermes" profile create "$role" --description "LeaseLab company role: $role"
  fi
  chmod 700 "/var/lib/leaselab-company/profiles/$role"
  if [[ $role != chief-of-staff ]]; then
    key="/etc/leaselab-company/ssh/$role"
    if [[ ! -f $key ]]; then
      ssh-keygen -q -t ed25519 -N '' -C "leaselab-company-$role" -f "$key"
    fi
    chown root:hermes "$key"
    chmod 640 "$key"
    { printf 'restrict,from="127.0.0.1" '; cat "$key.pub"; } > "/etc/ssh/authorized_keys/$account"
    chmod 644 "/etc/ssh/authorized_keys/$account"
  fi
done
cat > /etc/ssh/sshd_config.d/00-leaselab-company.conf <<'SSH'
ListenAddress 127.0.0.1
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers leaselab-support leaselab-sre leaselab-engineer leaselab-reviewer leaselab-qa-security leaselab-growth
AuthorizedKeysFile /etc/ssh/authorized_keys/%u
AllowTcpForwarding no
AllowAgentForwarding no
X11Forwarding no
PermitTunnel no
SSH
/usr/sbin/sshd -t
systemctl restart ssh
install -d -m 700 -o hermes -g hermes /home/hermes/.ssh
ssh-keyscan -H 127.0.0.1 2>/dev/null > /home/hermes/.ssh/known_hosts
chown hermes:hermes /home/hermes/.ssh/known_hosts
chmod 600 /home/hermes/.ssh/known_hosts
# The stock bootstrap API is unnecessary; keep all control interfaces local.
if [[ -f /home/hermes/.hermes/.env ]]; then
  sed -i -e 's/^API_SERVER_ENABLED=.*/API_SERVER_ENABLED=false/' -e 's/^API_SERVER_HOST=.*/API_SERVER_HOST=127.0.0.1/' /home/hermes/.hermes/.env
fi
systemctl disable --now hermes-dashboard
printf '%s\n' 'Role identities and native SSH execution boundary installed; gateway remains disabled pending credentials and guard verification.'
