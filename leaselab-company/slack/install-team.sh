#!/usr/bin/env bash
# Incremental rollout. Credentials are provisioned externally; never printed or copied into Git.
set -euo pipefail
usage() { printf '%s\n' 'Usage: install-team.sh /path/to/slack-identities.json [--credentials-dir /private/directory] [--apply] [--start]'; }
[[ ${1:-} != --help && $# -ge 1 ]] || { usage; exit 0; }
[[ $(id -u) = 0 && $(hostname) = hermes-leaselab ]] || exit 77
mapping=$(realpath "$1")
shift
apply=false
start=false
credentials_dir=
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=true; shift ;;
    --start) start=true; shift ;;
    --credentials-dir) [[ $# -ge 2 ]] || exit 64; credentials_dir=$(realpath "$2"); shift 2 ;;
    *) usage; exit 64 ;;
  esac
done
[[ $start = false || $apply = true ]] || exit 64
source_dir=$(cd "$(dirname "$0")/.." && pwd)
installer_python=${INSTALLER_PYTHON:-/opt/leaselab-company-installer/venv/bin/python}
[[ -x $installer_python && $(stat -Lc %u "$installer_python") = 0 ]] || { echo 'Root-owned installer Python is required.' >&2; exit 78; }
"$installer_python" -c 'import yaml, pydantic, dotenv, typer'
profiles=/var/lib/leaselab-company/profiles
roles=(chief-of-staff engineer reviewer qa-security sre support growth)
stage=$(mktemp -d /var/tmp/leaselab-slack-stage.XXXXXX)
chmod 700 "$stage"
trap 'rm -rf "$stage"' EXIT
for role in "${roles[@]}"; do
  [[ -d $profiles/$role && ! -L $profiles/$role ]] || exit 77
  mkdir -m 700 "$stage/$role"
  cp -p "$profiles/$role/config.yaml" "$profiles/$role/.env" "$stage/$role/"
done
if [[ -n $credentials_dir ]]; then
  "$installer_python" - "$stage" "$credentials_dir" "$mapping" <<'PYCREDENTIALS'
import sys
import stat
from pathlib import Path
from typing import ClassVar, Literal
from dotenv import set_key
from pydantic import BaseModel, ConfigDict

class Credential(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    profile: str
    workspace: Literal["T021CUR5KTP"]
    app_id: str
    SLACK_BOT_TOKEN: str
    SLACK_APP_TOKEN: str

import json
stage, directory, mapping_path = map(Path, sys.argv[1:])
info = directory.lstat()
if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
    raise SystemExit("Credential staging directory must be root-owned and private")
mapping = json.loads(mapping_path.read_text())
for role in ("engineer", "reviewer", "qa-security", "sre", "support", "growth"):
    path = directory / (role + ".json")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise SystemExit("Credential staging files must be root-owned and private")
    credential = Credential.model_validate_json(path.read_text())
    if credential.profile != role or credential.app_id != mapping['roles'][role]['app_id']:
        raise SystemExit("Credential profile/app mapping mismatch")
    if not credential.SLACK_BOT_TOKEN.startswith("xoxb-") or not credential.SLACK_APP_TOKEN.startswith("xapp-"):
        raise SystemExit("Credential token kind mismatch")
    env = stage / role / '.env'
    for key, value in (("SLACK_BOT_TOKEN", credential.SLACK_BOT_TOKEN), ("SLACK_APP_TOKEN", credential.SLACK_APP_TOKEN), ("SLACK_ALLOWED_USERS", "U0225R7NP8Q")):
        set_key(env, key, value)
    for key in ("SLACK_ALLOW_ALL_USERS", "GATEWAY_ALLOW_ALL_USERS"):
        set_key(env, key, "false")
    env.chmod(0o600)
print("Six specialist credential overlays staged without changing installed profiles.")
PYCREDENTIALS
fi
"$installer_python" "$source_dir/bootstrap/patch-context-permissions.py" --check
# All credentials and desired native configurations validate before any service stops.
"$installer_python" "$source_dir/slack/configure.py" --profiles-root "$stage" --identities-file "$mapping" --apply
"$installer_python" - "$stage" <<'PY'
import sys
from pathlib import Path
import yaml
root = Path(sys.argv[1])
for path in root.glob('*/config.yaml'):
    config = yaml.safe_load(path.read_text())
    if path.parent.name == 'chief-of-staff':
        config['timezone'] = 'America/Toronto'
    enabled = config.setdefault('plugins', {}).setdefault('enabled', [])
    for name in ('leaselab-company-guard', 'leaselab-slack-team', 'leaselab-management'):
        if name not in enabled:
            enabled.append(name)
    for names in config['platform_toolsets'].values():
        if 'leaselab-management' not in names:
            names.append('leaselab-management')
    path.write_text(yaml.safe_dump(config, sort_keys=False))
PY
"$installer_python" - "$source_dir/slack-team" "$mapping" <<'PYVALIDATE'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from policy import load_identities
load_identities(Path(sys.argv[2]))
print('Root-managed Slack identity mapping validated.')
PYVALIDATE
[[ -f $source_dir/management/plugin.yaml && -f $source_dir/slack-team/policy.py ]] || exit 78
if [[ $apply = false ]]; then
  echo 'Staged seven profile updates successfully; no services or installed files changed.'
  exit 0
fi
backup=/var/backups/leaselab-company/slack-team-$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 700 "$backup"
paths=(home/hermes/.hermes/hermes-agent/agent/prompt_builder.py usr/local/libexec/leaselab-company/patch-context-permissions.py etc/leaselab-company/guard etc/leaselab-company/slack-team etc/leaselab-company/management etc/leaselab-company/slack-identities.json usr/local/libexec/leaselab-company/company-worker.sh usr/local/libexec/leaselab-company/specialist-gateway-preflight.py usr/local/libexec/leaselab-company/slack-team-preflight.py etc/systemd/system/leaselab-company-gateway.service.d/slack-team.conf etc/systemd/system/leaselab-company-specialist@.service)
for role in "${roles[@]}"; do
  for name in config.yaml SOUL.md .env plugins/leaselab-company-guard plugins/leaselab-slack-team plugins/leaselab-management; do
    paths+=("var/lib/leaselab-company/profiles/$role/$name")
  done
done
printf '%s\n' "${paths[@]}" > "$backup/paths"
: > "$backup/existing"
for path in "${paths[@]}"; do
  [[ ! -e /$path && ! -L /$path ]] || printf '%s\n' "$path" >> "$backup/existing"
done
tar -C / -cpf "$backup/files.tar" -T "$backup/existing"
units=(leaselab-company-gateway.service)
for role in "${roles[@]:1}"; do units+=("leaselab-company-specialist@$role.service"); done
: > "$backup/active-units"
: > "$backup/enabled-specialists"
for unit in "${units[@]}"; do
  if [[ $unit == leaselab-company-specialist@* ]] && systemctl is-enabled --quiet "$unit" 2>/dev/null; then printf '%s\n' "$unit" >> "$backup/enabled-specialists"; fi
  if systemctl is-active --quiet "$unit"; then printf '%s\n' "$unit" >> "$backup/active-units"; fi
done
cat > "$backup/rollback.sh" <<'ROLLBACK'
#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) = 0 && $(hostname) = hermes-leaselab ]] || exit 77
backup=$(cd "$(dirname "$0")" && pwd)
systemctl stop leaselab-company-gateway.service 'leaselab-company-specialist@*.service'
for role in engineer reviewer qa-security sre support growth; do
  unit="leaselab-company-specialist@$role.service"
  if [[ $(systemctl show -p LoadState --value "$unit") != not-found ]]; then systemctl disable "$unit"; fi
done
while IFS= read -r path; do rm -rf -- "/$path"; done < "$backup/paths"
tar -C / -xpf "$backup/files.tar"
systemctl daemon-reload
while IFS= read -r unit; do systemctl enable "$unit"; done < "$backup/enabled-specialists"
while IFS= read -r unit; do systemctl start "$unit"; done < "$backup/active-units"
printf '%s\n' 'Previous files and active gateway services restored.'
ROLLBACK
chmod 700 "$backup/rollback.sh"
on_apply_error() {
  status=$?
  trap - ERR
  printf 'Incremental rollout failed; restoring %s\n' "$backup" >&2
  if "$backup/rollback.sh"; then
    printf '%s\n' 'Rollback completed; previous active gateways restored.' >&2
  else
    printf 'ROLLBACK FAILED. Inspect services and run %s/rollback.sh manually.\n' "$backup" >&2
  fi
  exit "$status"
}
trap on_apply_error ERR
for unit in "${units[@]}"; do
  if [[ $(systemctl show -p LoadState --value "$unit") != not-found ]]; then systemctl stop "$unit"; fi
done
for package in guard slack-team management; do
  install -d -m 755 "/etc/leaselab-company/$package"
  find "$source_dir/$package" -maxdepth 1 -type f \( -name '*.py' -o -name plugin.yaml \) -exec install -m 644 -t "/etc/leaselab-company/$package" {} +
done
install -m 644 "$mapping" /etc/leaselab-company/slack-identities.json
install -m 644 "$source_dir/bootstrap/patch-context-permissions.py" /usr/local/libexec/leaselab-company/patch-context-permissions.py
"$installer_python" /usr/local/libexec/leaselab-company/patch-context-permissions.py --apply
install -m 755 "$source_dir/bootstrap/company-worker.sh" /usr/local/libexec/leaselab-company/company-worker.sh
install -d -o hermes -g hermes -m 700 /var/lib/leaselab-company/workspaces
for role in "${roles[@]}"; do install -d -o hermes -g hermes -m 700 "/var/lib/leaselab-company/workspaces/$role"; done
install -m 644 "$source_dir/bootstrap/slack-team-preflight.py" /usr/local/libexec/leaselab-company/slack-team-preflight.py
install -d -m 755 /etc/systemd/system/leaselab-company-gateway.service.d
cat > /etc/systemd/system/leaselab-company-gateway.service.d/slack-team.conf <<'DROPIN'
[Service]
ExecStartPre=/home/hermes/.hermes/hermes-agent/venv/bin/python /usr/local/libexec/leaselab-company/slack-team-preflight.py
DROPIN
install -m 644 "$source_dir/bootstrap/specialist-gateway-preflight.py" /usr/local/libexec/leaselab-company/specialist-gateway-preflight.py
install -m 644 "$source_dir/systemd/leaselab-company-specialist@.service" /etc/systemd/system/leaselab-company-specialist@.service
for role in "${roles[@]}"; do
  for name in .env config.yaml SOUL.md; do
    candidate="$stage/$role/$name"
    [[ $name != SOUL.md ]] || candidate="$source_dir/profiles/$role/SOUL.md"
    original="$profiles/$role/$name"
    install -o "$(stat -c %u "$original")" -g "$(stat -c %g "$original")" -m "$(stat -c %a "$original")" "$candidate" "$original"
  done
  install -d -o hermes -g hermes -m 700 "$profiles/$role/plugins"
  ln -sfn /etc/leaselab-company/guard "$profiles/$role/plugins/leaselab-company-guard"
  ln -sfn /etc/leaselab-company/slack-team "$profiles/$role/plugins/leaselab-slack-team"
  ln -sfn /etc/leaselab-company/management "$profiles/$role/plugins/leaselab-management"
done
systemctl daemon-reload
if [[ $start = true ]]; then
  for unit in "${units[@]}"; do systemctl start "$unit"; done
fi
trap - ERR
printf 'Installed incremental Slack team configuration; rollback: %s/rollback.sh\n' "$backup"
printf '%s\n' 'Services were not enabled automatically. Native weekly schedule provisioning is a separate CoS operation.'
