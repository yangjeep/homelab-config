#!/bin/bash
set -euo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
exec 9>/var/lib/leaselab-backup/full.lock
flock -n 9 || exit 0
source_home=/var/lib/leaselab-company
test -d "$source_home/profiles"
test ! -L "$source_home"
for profile in chief-of-staff engineer qa-security reviewer sre support growth; do
 test -f "$source_home/profiles/$profile/state.db"
 test -f "$source_home/profiles/$profile/config.yaml"
 test ! -L "$source_home/profiles/$profile"
done
test -f "$source_home/kanban.db"
test -f "$source_home/shared-state.db"
# Native snapshots .db only. Refuse new .sqlite stores until an online-copy step is defined.
if find "$source_home" -type f -name '*.sqlite*' -print -quit | grep -q .; then
 echo 'Additional SQLite store requires an explicit online snapshot rule.' >&2
 exit 1
fi
stamp=$(date -u +%Y-%m-%d-%H%M%SZ)
native=$(mktemp -d /var/lib/leaselab-backup-staging/native.XXXXXX)
bundle=$(mktemp -d /var/lib/leaselab-backup/staging/full.XXXXXX)
trap 'rm -rf -- "$native" "$bundle"' EXIT
chown hermes:hermes "$native"
# Native backup resolves a custom profile home to its company root, including all profiles.
runuser -u hermes -- env HERMES_HOME="$source_home" HERMES_PROFILE=chief-of-staff \
 /home/hermes/.local/bin/hermes backup --output "$native/hermes.zip" --keep 0 > "$bundle/native.log" 2>&1
grep -q 'Backup complete:' "$bundle/native.log"
test -s "$native/hermes.zip"
mv "$native/hermes.zip" "$bundle/hermes.zip"
chown root:root "$bundle/hermes.zip"
python3 /etc/leaselab-backup/verify.py "$bundle/hermes.zip"
# Explicit host wiring only: never archive role homes, /etc/leaselab-company/ssh, or backup keys.
paths=(etc/leaselab-backup usr/local/sbin/leaselab-knowledge-backup usr/local/sbin/leaselab-full-backup usr/local/libexec/leaselab-company)
for path in /etc/systemd/system/leaselab-* /etc/sudoers.d/*leaselab* /etc/leaselab-company/guard; do
 test -e "$path" && paths+=("${path#/}")
done
tar -C / -czf "$bundle/host-config.tar.gz" --exclude=__pycache__ "${paths[@]}"
runuser -u hermes -- /home/hermes/.local/bin/hermes --version > "$bundle/hermes-version.txt"
runuser -u hermes -- git -C /home/hermes/.hermes/hermes-agent rev-parse HEAD > "$bundle/hermes-code-commit.txt"
runuser -u hermes -- git -C /home/hermes/.hermes/hermes-agent diff HEAD --binary > "$bundle/hermes-code.patch"
(cd "$bundle" && sha256sum hermes.zip host-config.tar.gz hermes-version.txt hermes-code-commit.txt hermes-code.patch > SHA256SUMS)
archive=/var/lib/leaselab-backup/staging/hermes-leaselab-full-$stamp.tar.gz
tar -C "$bundle" -czf "$archive.partial" .
mv "$archive.partial" "$archive"
rsync -t --chmod=F600 --timeout=300 -e 'ssh -F /etc/leaselab-backup/ssh_config' "$archive" leaselab-truenas:./
sha256sum "$archive"
rm -f -- "$archive"
echo "Full backup complete: archives/hermes-leaselab-full-$stamp.tar.gz"
