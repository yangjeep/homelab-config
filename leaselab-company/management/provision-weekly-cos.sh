#!/usr/bin/env bash
set -euo pipefail
# Use the CoS profile environment and the installed Hermes interpreter.
# No credentials are arguments. Existing named cron jobs are updated in place.
: "${HERMES_PROFILE:?Run in the chief-of-staff profile environment}"
exec /home/hermes/.hermes/hermes-agent/venv/bin/python -m management.scheduler
