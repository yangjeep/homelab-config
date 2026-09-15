# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2", "slack-bolt>=1"]
# ///
# Run: installed Hermes venv/bin/python slack-team-preflight.py as hermes.
"""Require the native ingress plugin and exercise its real Bolt installation."""

import os
from dataclasses import dataclass
from typing import Final

from hermes_cli.plugins import discover_plugins, get_plugin_manager
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.authorization.authorize_result import AuthorizeResult

EXPECTED: Final = "leaselab-slack-team"


async def authorize() -> AuthorizeResult:
    """Local preflight only: no Slack credential or network use."""
    return AuthorizeResult(
        enterprise_id=None, team_id="T021CUR5KTP", bot_user_id="UPREFLIGHT"
    )


@dataclass(frozen=True, slots=True)
class Adapter:
    _team_bot_user_ids: dict[str, str]


def main() -> int:
    role = os.environ.get("HERMES_PROFILE", "")
    if role not in (
        "chief-of-staff",
        "engineer",
        "reviewer",
        "qa-security",
        "sre",
        "support",
        "growth",
    ):
        return 1
    discover_plugins()
    factories = [
        factory
        for factory, name in get_plugin_manager().get_platform_handler_factories(
            "slack"
        )
        if name == EXPECTED
    ]
    if len(factories) != 1:
        print("Required Slack ingress plugin missing or duplicated.")
        return 1
    app = AsyncApp(authorize=authorize, request_verification_enabled=False)
    before = len(app._async_middleware_list)
    factories[0](app, Adapter({}))
    if len(app._async_middleware_list) != before + 1:
        print("Required Slack ingress middleware was not installed.")
        return 1
    print("Native Slack ingress plugin and Bolt factory preflight PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
