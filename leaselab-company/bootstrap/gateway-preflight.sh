#!/usr/bin/env bash
set -euo pipefail
[[ $(id -un) = hermes && ${HERMES_PROFILE:-} = chief-of-staff ]] || exit 1
/home/hermes/.hermes/hermes-agent/venv/bin/python /usr/local/libexec/leaselab-company/gateway-policy.py
for role in chief-of-staff support sre engineer reviewer qa-security growth; do
  profile="/var/lib/leaselab-company/profiles/$role"
  [[ $(stat -c %a "$profile/.env") = 600 ]] || exit 1
  grep -q '^OPENROUTER_API_KEY=sk-or-v1-' "$profile/.env"
  if [[ $role != chief-of-staff ]] && grep -q '^TELEGRAM_BOT_TOKEN=' "$profile/.env"; then
    exit 1
  fi
  HERMES_HOME="$profile" HERMES_PROFILE="$role" /home/hermes/.hermes/hermes-agent/venv/bin/python - <<'PY'
import os
import telegram
from hermes_cli.config import apply_terminal_config_to_env
from hermes_cli.plugins import discover_plugins, get_pre_tool_call_block_message
apply_terminal_config_to_env(override=True)
discover_plugins()
assert get_pre_tool_call_block_message("execute_code", {}) is not None
assert get_pre_tool_call_block_message("memory", {}) is None
if os.environ["HERMES_PROFILE"] == "chief-of-staff":
    assert get_pre_tool_call_block_message("terminal", {}) is not None
else:
    assert get_pre_tool_call_block_message("terminal", {}) is None
PY
done
grep -qx 'TELEGRAM_ALLOWED_USERS=660328434' /var/lib/leaselab-company/profiles/chief-of-staff/.env
grep -qx 'TELEGRAM_HOME_CHANNEL=660328434' /var/lib/leaselab-company/profiles/chief-of-staff/.env
printf '%s\n' 'Company role guard, credential presence and founder allowlist preflight PASS'
