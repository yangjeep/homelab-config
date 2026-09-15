# /// script
# requires-python = ">=3.11"
# dependencies = ["PyYAML>=6", "python-dotenv>=1"]
# ///
# Run: installed Hermes venv/bin/python /usr/local/libexec/leaselab-company/gateway-policy.py
"""Reject permissive startup settings before profile loading can override the environment."""

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

import yaml
from dotenv import dotenv_values

Value = str | int | bool | None | list["Value"] | dict[str, "Value"]
FOUNDER: Final = "660328434"
REQUIRED: Final = {"TELEGRAM_ALLOWED_USERS": FOUNDER, "TELEGRAM_HOME_CHANNEL": FOUNDER}
FLAGS: Final = (
    "TELEGRAM_ALLOW_ALL_USERS",
    "GATEWAY_ALLOW_ALL_USERS",
    "TELEGRAM_GUEST_MODE",
)


def policy_valid(
    config: Value, profile: Mapping[str, str | None], environment: Mapping[str, str]
) -> bool:
    """Check both persisted and inherited authority before runtime configuration bridging."""
    if not isinstance(config, dict):
        return False
    platforms = config.get("platforms")
    if not isinstance(platforms, dict):
        return False
    telegram = platforms.get("telegram")
    if not isinstance(telegram, dict) or telegram.get("enabled") is not True:
        return False
    extra = telegram.get("extra")
    if not isinstance(extra, dict):
        return False
    expected = {
        "dm_policy": "allowlist",
        "group_policy": "disabled",
        "unauthorized_dm_behavior": "ignore",
        "group_allow_from": [],
        "allowed_chats": [FOUNDER],
        "guest_mode": False,
    }
    if "allow_from" in extra and extra["allow_from"] != [FOUNDER]:
        return False
    if any(extra.get(key) != value for key, value in expected.items()):
        return False
    if any(profile.get(key) != value for key, value in REQUIRED.items()):
        return False
    if any(
        key in environment and environment[key] != value
        for key, value in REQUIRED.items()
    ):
        return False
    for source in (profile, environment):
        if any(
            (source.get(flag) or "").strip().lower() not in ("", "false", "0", "no")
            for flag in FLAGS
        ):
            return False
        if (source.get("GATEWAY_ALLOWED_USERS") or "") not in ("", FOUNDER):
            return False
        if any(
            source.get(key)
            for key in ("TELEGRAM_GROUP_ALLOWED_USERS", "TELEGRAM_GROUP_ALLOWED_CHATS")
        ):
            return False
    return True


def _read_config(path: Path, loader: Callable[[str], Value] = yaml.safe_load) -> Value:
    return loader(path.read_text())


def main() -> int:
    home = Path("/var/lib/leaselab-company/profiles/chief-of-staff")
    try:
        config = _read_config(home / "config.yaml")
        profile = dotenv_values(home / ".env", interpolate=False)
        valid = policy_valid(config, profile, os.environ)
    except (OSError, ValueError, yaml.YAMLError):
        valid = False
    if not valid:
        print("Company Telegram authority preflight denied unsafe or missing settings.")
        return 1
    print("Company Telegram authority preflight PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
