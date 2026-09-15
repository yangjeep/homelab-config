#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) = 0 && $(hostname) = hermes-leaselab ]] || exit 1
source_dir=$(cd "$(dirname "$0")/.." && pwd)
install -d -m 755 /etc/leaselab-company/guard
install -m 644 "$source_dir/guard/__init__.py" /etc/leaselab-company/guard/__init__.py
install -m 644 "$source_dir/guard/plugin.yaml" /etc/leaselab-company/guard/plugin.yaml
for role in chief-of-staff support sre engineer reviewer qa-security growth; do
  profile="/var/lib/leaselab-company/profiles/$role"
  [[ -d $profile ]] || exit 1
  tools='[memory, skills, session_search, kanban, terminal, file]'
  dispatch=false
  if [[ $role = chief-of-staff ]]; then
    tools='[memory, skills, session_search, kanban]'
    dispatch=true
  fi
  cat > "$profile/config.yaml" <<YAML
model:
  provider: openrouter
  default: '~deepseek/deepseek-v4-flash-latest'
agent:
  max_turns: 40
  run_budget_seconds: 240
platform_toolsets:
  cli: $tools
  telegram: $tools
memory:
  memory_enabled: true
  user_profile_enabled: true
  write_approval: false
skills:
  external_dirs: []
  create_dir: ''
  project_discovery: false
  trusted_project_dirs: []
  inline_shell: false
  guard_agent_created: true
  write_approval: false
  ledger: true
auxiliary:
  background_review:
    enabled: true
    extra_tools: []
plugins:
  enabled: [leaselab-company-guard]
tools:
  tool_search:
    enabled: 'off'
kanban:
  dispatch_in_gateway: $dispatch
  dispatch_interval_seconds: 30
  orchestrator_profile: chief-of-staff
  default_assignee: chief-of-staff
  review_dispatch: true
  max_in_progress: 2
  max_in_progress_per_profile: 1
  failure_limit: 2
terminal:
  backend: ssh
  ssh_host: 127.0.0.1
  ssh_port: 22
  ssh_user: leaselab-$role
  ssh_key: /etc/leaselab-company/ssh/$role
  cwd: /srv/leaselab/roles/$role/workspaces
  home_mode: real
  env_passthrough: []
  timeout: 180
platforms:
  telegram:
    enabled: false
    extra:
      dm_policy: allowlist
      group_policy: disabled
      unauthorized_dm_behavior: ignore
YAML
  chmod 640 "$profile/config.yaml"
  chown root:hermes "$profile/config.yaml"
  install -m 640 -o root -g hermes "$source_dir/profiles/$role/SOUL.md" "$profile/SOUL.md"
  install -d -m 700 -o hermes -g hermes "$profile/plugins"
  ln -sfn /etc/leaselab-company/guard "$profile/plugins/leaselab-company-guard"
  if [[ ! -e $profile/.env ]]; then
    install -m 600 -o hermes -g hermes /dev/null "$profile/.env"
  fi
done
runuser -u hermes -- env HOME=/home/hermes HERMES_KANBAN_HOME=/var/lib/leaselab-company /home/hermes/.local/bin/hermes kanban init
runuser -u hermes -- env HOME=/home/hermes HERMES_KANBAN_HOME=/var/lib/leaselab-company /home/hermes/.local/bin/hermes kanban boards create leaselab-company
printf '%s\n' 'Native profiles and board configured. Telegram remains fail-closed until verified credentials and founder identity are installed.'
