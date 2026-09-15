# /// script
# requires-python = ">=3.11"
# dependencies = ["PyYAML>=6", "pydantic>=2", "python-dotenv>=1", "typer>=0.12"]
# ///
# Run: uv run configure.py --profiles-root /var/lib/leaselab-company/profiles --apply
"""Reconcile nonsecret Slack configuration after external credential provisioning."""

import os
import tempfile
from pathlib import Path
from typing import ClassVar, Final, Literal

import typer
import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

ROLES: Final = (
    "chief-of-staff",
    "engineer",
    "reviewer",
    "qa-security",
    "sre",
    "support",
    "growth",
)
CHANNELS: Final = (
    "C0C2Q3Y1QF2",
    "C0C2Q43J0KS",
    "C0C1XMT2BU1",
    "C0C1PH369DH",
    "C0C1XMYQMR7",
    "C0C1R45U8SH",
)
HOME_CHANNELS: Final = {
    "chief-of-staff": "C0C2Q3Y1QF2",
    "engineer": "C0C2Q43J0KS",
    "reviewer": "C0C2Q43J0KS",
    "qa-security": "C0C1XMT2BU1",
    "sre": "C0C1PH369DH",
    "support": "C0C1XMYQMR7",
    "growth": "C0C1R45U8SH",
}
PROFILES_ROOT: Final = Path("/var/lib/leaselab-company/profiles")
FOUNDER: Final = "U0225R7NP8Q"
TOOLSET: Final = "leaselab-slack-send"
CONFIG: Final = TypeAdapter(
    dict[str, JsonValue], config=ConfigDict(hide_input_in_errors=True)
)
MAPPING: Final = CONFIG
TOOLSETS: Final = TypeAdapter(
    dict[str, list[str]], config=ConfigDict(hide_input_in_errors=True)
)


class IdentityChannels(BaseModel):
    """Only routing scope is consumed here; ingress authenticates role identities."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True, extra="ignore", hide_input_in_errors=True
    )
    team_id: Literal["T021CUR5KTP"]
    founder_user_id: Literal["U0225R7NP8Q"]
    channels: list[str] = Field(min_length=1)


def reconciled(
    config: dict[str, JsonValue], role: str, channels: tuple[str, ...] = CHANNELS
) -> dict[str, JsonValue]:
    platform_toolsets = TOOLSETS.validate_python(config.get("platform_toolsets", {}))
    if "cli" not in platform_toolsets:
        raise typer.BadParameter(f"{role}: platform_toolsets.cli missing")
    platform_toolsets["slack"] = list(platform_toolsets["cli"])
    for names in platform_toolsets.values():
        if TOOLSET not in names:
            names.append(TOOLSET)
    platforms = MAPPING.validate_python(config.get("platforms", {}))
    slack = MAPPING.validate_python(platforms.get("slack", {}))
    extra = MAPPING.validate_python(slack.get("extra", {}))
    extra.update(
        {
            "allowed_channels": list(channels),
            "allowed_users": [FOUNDER],
            "require_mention": True,
            "strict_mention": True,
            "thread_require_mention": True,
            "allow_bots": "none",
            "disable_dms": True,
        }
    )
    slack.update({"enabled": True, "extra": extra})
    slack["home_channel"] = {
        "platform": "slack",
        "chat_id": HOME_CHANNELS[role],
        "name": role,
        "user_id": FOUNDER,
        "scope_id": "T021CUR5KTP",
    }
    platforms["slack"] = slack
    if role != "chief-of-staff":
        platforms["telegram"] = {"enabled": False}
    kanban = MAPPING.validate_python(config.get("kanban", {}))
    kanban["dispatch_in_gateway"] = role == "chief-of-staff"
    gateway = MAPPING.validate_python(config.get("gateway", {}))
    gateway["multiplex_profiles"] = False
    gateway_platforms = MAPPING.validate_python(gateway.get("platforms", {}))
    slack_runtime = MAPPING.validate_python(gateway_platforms.get("slack", {}))
    slack_runtime["skip_context_files"] = True
    gateway_platforms["slack"] = slack_runtime
    gateway["platforms"] = gateway_platforms
    result = dict(config)
    result["platform_toolsets"] = CONFIG.validate_python(platform_toolsets)
    result["platforms"] = platforms
    result["kanban"] = kanban
    result["gateway"] = gateway
    return result


def check_credentials(directory: Path, role: str) -> None:
    env_path = directory / ".env"
    if (
        not env_path.is_file()
        or env_path.is_symlink()
        or env_path.stat().st_mode & 0o077
    ):
        raise typer.BadParameter(f"{role}: .env must be a private regular file")
    values = dotenv_values(env_path, interpolate=False)
    if not values.get("SLACK_BOT_TOKEN"):
        raise typer.BadParameter(f"{role}: external bot credential missing")
    if (
        not values.get("SLACK_APP_TOKEN")
        or values.get("SLACK_ALLOWED_USERS") != FOUNDER
    ):
        raise typer.BadParameter(
            f"{role}: external app token or exact founder allowlist missing"
        )
    if role != "chief-of-staff" and any(key.startswith("TELEGRAM_") for key in values):
        raise typer.BadParameter(f"{role}: specialist Telegram settings forbidden")
    for flag in ("SLACK_ALLOW_ALL_USERS", "GATEWAY_ALLOW_ALL_USERS"):
        if (values.get(flag) or "").lower() not in ("", "false", "0", "no"):
            raise typer.BadParameter(f"{role}: {flag} must be disabled")


def write_config(path: Path, content: str) -> None:
    previous = path.stat()
    descriptor, temporary = tempfile.mkstemp(prefix=".slack-config-", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w") as handle:
            os.fchmod(handle.fileno(), previous.st_mode & 0o777)
            if os.geteuid() == 0:
                os.fchown(handle.fileno(), previous.st_uid, previous.st_gid)
            _ = handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main(
    profiles_root: Path = PROFILES_ROOT,
    apply: bool = False,
    identities_file: Path | None = None,
) -> None:
    """Validate all seven profiles, then optionally update only Slack/toolset settings."""
    channels = CHANNELS
    if identities_file is not None:
        mapping = IdentityChannels.model_validate_json(identities_file.read_text())
        if any(
            not channel.startswith("C") or not channel.isalnum()
            for channel in mapping.channels
        ):
            raise typer.BadParameter(
                "Slack channels must be explicit public channel IDs"
            )
        channels = tuple(mapping.channels)
    changes: list[tuple[Path, str]] = []
    seen_bots: set[str] = set()
    seen_apps: set[str] = set()
    for role in ROLES:
        directory = profiles_root / role
        path = directory / "config.yaml"
        if directory.is_symlink() or path.is_symlink():
            raise typer.BadParameter(f"{role}: symlinked configuration forbidden")
        check_credentials(directory, role)
        values = dotenv_values(directory / ".env", interpolate=False)
        bot = values.get("SLACK_BOT_TOKEN") or ""
        app = values.get("SLACK_APP_TOKEN") or ""
        if bot in seen_bots or app in seen_apps:
            raise typer.BadParameter(
                "Slack role bot and app credentials must be distinct"
            )
        seen_bots.add(bot)
        seen_apps.add(app)
        current = CONFIG.validate_python(yaml.safe_load(path.read_text()))
        desired = reconciled(current, role, channels)
        if desired != current:
            changes.append((path, yaml.safe_dump(desired, sort_keys=False)))
    if apply:
        for path, content in changes:
            write_config(path, content)
    typer.echo(
        f"Validated {len(ROLES)} profiles; {'updated' if apply else 'would update'} {len(changes)} configurations."
    )


if __name__ == "__main__":
    typer.run(main)
