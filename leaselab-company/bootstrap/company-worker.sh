#!/usr/bin/env bash
set -euo pipefail
[[ ${1:-} = -p && $# -ge 3 ]] || { echo 'Company worker requires an explicit profile' >&2; exit 64; }
role=$2
case "$role" in
  chief-of-staff|support|sre|engineer|reviewer|qa-security|growth) ;;
  *) echo 'Non-company assignee denied' >&2; exit 77 ;;
esac
[[ ${HERMES_PROFILE:-} = "$role" ]] || exit 77
[[ ${HERMES_HOME:-} = "/var/lib/leaselab-company/profiles/$role" || ${HERMES_HOME:-} = "/home/hermes/.hermes/profiles/$role" ]] || exit 77
[[ -n ${HERMES_KANBAN_TASK:-} && ${HERMES_KANBAN_BOARD:-} = leaselab-company ]] || exit 77
context="/var/lib/leaselab-company/workspaces/$role"
[[ ${HERMES_KANBAN_WORKSPACE:-} = "$context" && -d $context && ! -L $context ]] || exit 77
cd "$context"
exec /home/hermes/.local/bin/hermes "$@"
