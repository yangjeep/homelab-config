# /// script
# requires-python = ">=3.11"
# dependencies = ["PyYAML>=6", "pydantic>=2", "python-dotenv>=1"]
# ///
# Run: installed Hermes venv/bin/python specialist-gateway-preflight.py
"""Fail closed before a dedicated specialist native gateway starts."""

import os
from pathlib import Path
from typing import Final

import yaml
from dotenv import dotenv_values
from pydantic import ConfigDict, JsonValue, TypeAdapter, ValidationError

ROLES: Final = ("engineer", "reviewer", "qa-security", "sre", "support", "growth")
ROOT: Final = Path("/var/lib/leaselab-company/profiles")
FOUNDER: Final = "U0225R7NP8Q"
CONFIG: Final = TypeAdapter(
    dict[str, JsonValue], config=ConfigDict(hide_input_in_errors=True)
)


def main() -> int:
    """Validate fixed process identity, private credentials and inactive dispatcher."""
    role = os.environ.get("HERMES_PROFILE", "")
    if role not in ROLES or os.environ.get("HERMES_HOME") != str(ROOT / role):
        return 1
    if os.environ.get("HERMES_KANBAN_DISPATCH_IN_GATEWAY") != "false":
        return 1
    directory = ROOT / role
    env_path = directory / ".env"
    config_path = directory / "config.yaml"
    try:
        if directory.is_symlink() or env_path.is_symlink() or config_path.is_symlink():
            return 1
        if not env_path.is_file() or env_path.stat().st_mode & 0o077:
            return 1
        credentials = dotenv_values(env_path, interpolate=False)
        for source in (credentials, os.environ):
            required_identity = {
                "HERMES_PROFILE": role,
                "HERMES_HOME": str(directory),
                "HERMES_KANBAN_DISPATCH_IN_GATEWAY": "false",
            }
            if any(
                source.get(key, value) != value
                for key, value in required_identity.items()
            ):
                return 1
            if any(key.startswith("TELEGRAM_") for key in source):
                return 1
            if any(
                (source.get(flag) or "").lower() not in ("", "0", "false", "no")
                for flag in ("SLACK_ALLOW_ALL_USERS", "GATEWAY_ALLOW_ALL_USERS")
            ):
                return 1
            if source.get("SLACK_ALLOWED_USERS", FOUNDER) != FOUNDER:
                return 1
        if not all(
            credentials.get(key) for key in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN")
        ):
            return 1
        if credentials.get("SLACK_ALLOWED_USERS") != FOUNDER:
            return 1
        config = CONFIG.validate_python(yaml.safe_load(config_path.read_text()))
        gateway = CONFIG.validate_python(config.get("gateway", {}))
        runtime_platforms = CONFIG.validate_python(gateway.get("platforms", {}))
        runtime_slack = CONFIG.validate_python(runtime_platforms.get("slack", {}))
        if runtime_slack.get("skip_context_files") is not True:
            return 1
        kanban = CONFIG.validate_python(config.get("kanban", {}))
        platforms = CONFIG.validate_python(config.get("platforms", {}))
        telegram = CONFIG.validate_python(platforms.get("telegram", {}))
        slack = CONFIG.validate_python(platforms.get("slack", {}))
        extra = CONFIG.validate_python(slack.get("extra", {}))
        if (
            gateway.get("multiplex_profiles") is not False
            or kanban.get("dispatch_in_gateway") is not False
        ):
            return 1
        if telegram != {"enabled": False} or slack.get("enabled") is not True:
            return 1
        expected: dict[str, JsonValue] = {
            "allowed_users": [FOUNDER],
            "require_mention": True,
            "strict_mention": True,
            "thread_require_mention": True,
            "disable_dms": True,
            "allow_bots": "none",
        }
        if any(extra.get(key) != value for key, value in expected.items()):
            return 1
        if not extra.get("allowed_channels"):
            return 1
    except (OSError, ValueError, ValidationError, yaml.YAMLError):
        return 1
    print("Specialist Slack gateway authority preflight PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
