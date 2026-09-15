#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT

mkdir -p "$fixture/profiles/engineer" "$fixture/workspaces/engineer" "$fixture/bin"
printf 'ROLE_MODEL_KEY=engineer-only\n' > "$fixture/profiles/engineer/.env"

cat > "$fixture/bin/hermes" <<EOF
#!/usr/bin/env bash
set -euo pipefail
set -a
source "\$HERMES_HOME/.env"
set +a
env | LC_ALL=C sort > "$fixture/capture"
EOF
chmod 700 "$fixture/bin/hermes"

sed \
  -e "s|/var/lib/leaselab-company/profiles/\\\$role|$fixture/profiles/\\\$role|g" \
  -e "s|/var/lib/leaselab-company/workspaces/\\\$role|$fixture/workspaces/\\\$role|g" \
  -e "s|/home/hermes/.local/bin/hermes|$fixture/bin/hermes|g" \
  "$root/bootstrap/company-worker.sh" > "$fixture/company-worker.sh"
chmod 700 "$fixture/company-worker.sh"

capture="$fixture/capture"
env -i \
  HOME=/home/hermes USER=hermes LOGNAME=hermes SHELL=/bin/bash \
  PATH=/home/hermes/.local/bin:/usr/local/bin:/usr/bin:/bin \
  XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
  HERMES_PROFILE=engineer HERMES_HOME="$fixture/profiles/engineer" \
  HERMES_KANBAN_TASK=t_synthetic HERMES_KANBAN_BOARD=leaselab-company \
  HERMES_KANBAN_DB=/var/lib/leaselab-company/kanban/boards/leaselab-company/kanban.db \
  HERMES_KANBAN_WORKSPACES_ROOT=/var/lib/leaselab-company/kanban/boards/leaselab-company/workspaces \
  HERMES_KANBAN_WORKSPACE="$fixture/workspaces/engineer" \
  HERMES_KANBAN_RUN_ID=run_synthetic HERMES_KANBAN_CLAIM_LOCK=claim_synthetic \
  HERMES_KANBAN_BRANCH=synthetic-branch HERMES_KANBAN_GOAL_MODE=1 HERMES_KANBAN_GOAL_MAX_TURNS=3 \
  HERMES_SESSION_SOURCE=kanban HERMES_TENANT=tenant_synthetic TERMINAL_CWD=/tmp/co-s-terminal-cwd \
  OPENROUTER_API_KEY=co-s-secret CO_S_ONLY=co-s-behavior TERMINAL_TIMEOUT=999 \
  TELEGRAM_BOT_TOKEN=synthetic-telegram-token SLACK_BOT_TOKEN=synthetic-slack-bot-token \
  SLACK_APP_TOKEN=synthetic-slack-app-token \
  HERMES_SESSION_CHAT_ID=C001 \
  "$fixture/company-worker.sh" -p engineer chat -q synthetic

for expected in \
  'HERMES_PROFILE=engineer' \
  "HERMES_HOME=$fixture/profiles/engineer" \
  'HERMES_KANBAN_TASK=t_synthetic' \
  'HERMES_KANBAN_BOARD=leaselab-company' \
  'HERMES_KANBAN_DB=/var/lib/leaselab-company/kanban/boards/leaselab-company/kanban.db' \
  'HERMES_KANBAN_WORKSPACES_ROOT=/var/lib/leaselab-company/kanban/boards/leaselab-company/workspaces' \
  "HERMES_KANBAN_WORKSPACE=$fixture/workspaces/engineer" \
  'HERMES_KANBAN_RUN_ID=run_synthetic' \
  'HERMES_KANBAN_CLAIM_LOCK=claim_synthetic' \
  'HERMES_KANBAN_BRANCH=synthetic-branch' \
  'HERMES_KANBAN_GOAL_MODE=1' \
  'HERMES_KANBAN_GOAL_MAX_TURNS=3' \
  'HERMES_SESSION_SOURCE=kanban' \
  'HERMES_TENANT=tenant_synthetic' \
  "TERMINAL_CWD=$fixture/workspaces/engineer" \
  'XDG_RUNTIME_DIR=/run/user/1000' \
  'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus' \
  'ROLE_MODEL_KEY=engineer-only'; do
  grep -Fxq "$expected" "$capture"
done
for absent in OPENROUTER_API_KEY CO_S_ONLY TERMINAL_TIMEOUT HERMES_SESSION_CHAT_ID \
  TELEGRAM_BOT_TOKEN SLACK_BOT_TOKEN SLACK_APP_TOKEN; do
  if grep -q "^${absent}=" "$capture"; then
    exit 1
  fi
done

if env -i HERMES_PROFILE=attacker HERMES_HOME="$fixture/profiles/attacker" \
  HERMES_KANBAN_TASK=t HERMES_KANBAN_BOARD=leaselab-company \
  HERMES_KANBAN_WORKSPACE="$fixture/workspaces/engineer" "$fixture/company-worker.sh" -p attacker chat -q synthetic; then
  exit 1
fi
if env -i HERMES_PROFILE=engineer HERMES_HOME="$fixture/profiles/engineer" \
  HERMES_KANBAN_TASK=t HERMES_KANBAN_BOARD=leaselab-company \
  HERMES_KANBAN_WORKSPACE="$fixture/outside" "$fixture/company-worker.sh" -p engineer chat -q synthetic; then
  exit 1
fi

printf 'Company worker clean environment, role configuration, task context, and boundary denial: PASS\n'
