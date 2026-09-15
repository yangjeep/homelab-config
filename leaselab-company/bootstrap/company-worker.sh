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

runtime_dir=${XDG_RUNTIME_DIR:-"/run/user/$(/usr/bin/id -u)"}
bus_address=${DBUS_SESSION_BUS_ADDRESS:-"unix:path=$runtime_dir/bus"}
worker_env=(
  "HOME=/home/hermes"
  "USER=hermes"
  "LOGNAME=hermes"
  "SHELL=/bin/bash"
  "PATH=/home/hermes/.local/bin:/usr/local/bin:/usr/bin:/bin"
  "XDG_RUNTIME_DIR=$runtime_dir"
  "DBUS_SESSION_BUS_ADDRESS=$bus_address"
  "HERMES_PROFILE=$role"
  "HERMES_HOME=$HERMES_HOME"
  "HERMES_KANBAN_TASK=$HERMES_KANBAN_TASK"
  "HERMES_KANBAN_BOARD=$HERMES_KANBAN_BOARD"
  "HERMES_KANBAN_WORKSPACE=$HERMES_KANBAN_WORKSPACE"
  "HERMES_SESSION_SOURCE=${HERMES_SESSION_SOURCE:-kanban}"
  "TERMINAL_CWD=$context"
)
for task_context in \
  HERMES_KANBAN_DB HERMES_KANBAN_WORKSPACES_ROOT HERMES_KANBAN_RUN_ID \
  HERMES_KANBAN_CLAIM_LOCK HERMES_KANBAN_BRANCH HERMES_KANBAN_GOAL_MODE \
  HERMES_KANBAN_GOAL_MAX_TURNS HERMES_TENANT; do
  value=${!task_context:-}
  [[ -n $value ]] && worker_env+=("$task_context=$value")
done
exec /usr/bin/env -i "${worker_env[@]}" /home/hermes/.local/bin/hermes "$@"
