#!/usr/bin/env bash
set -euo pipefail
# Run on PVE; inspect the official installer and resource availability first.
ctid=${LEASELAB_CTID:-916}
[[ $ctid =~ ^[0-9]+$ ]] || exit 2
if [[ -e /etc/pve/lxc/$ctid.conf || -e /etc/pve/qemu-server/$ctid.conf ]]; then
  echo 'Requested VMID already exists; refusing to allocate another ID.' >&2
  exit 1
fi
exec env mode=default \
  COMMUNITY_SCRIPTS_URL=https://raw.githubusercontent.com/community-scripts/ProxmoxVE/787dbf2420ec8217c967eb4c152cb3003446d327 \
  COMMUNITY_SCRIPTS_CORE_URL=https://raw.githubusercontent.com/community-scripts/core/cf804c82f9d9050d8e9e30f0c33c148bd883dc18 \
  var_ctid="$ctid" var_hostname=hermes-leaselab \
  var_cpu=4 var_ram=8192 var_disk=40 var_os=debian var_version=13 \
  var_unprivileged=1 var_brg=vmbr0 var_vlan=253 var_net=dhcp \
  var_ipv6_method=none var_container_storage=vm-micron var_template_storage=local \
  var_tags='leaselab;ai;agent;company' \
  bash "$(dirname "$0")/hermesagent.sh"
