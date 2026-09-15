# /// script
# requires-python = ">=3.11"
# dependencies = ["PyYAML>=6", "pydantic>=2", "python-dotenv>=1", "typer>=0.12"]
# ///
# Run: uv run configure.py --profiles-root /var/lib/leaselab-company/profiles --apply
"""Reconcile nonsecret Slack configuration after external credential provisioning."""

import os
import tempfile
from pathlib import Path
from typing import Final

import typer
import yaml
from dotenv import dotenv_values
from pydantic import ConfigDict, JsonValue, TypeAdapter

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
FOUNDER: Final = "U0225R7NP8Q"
TOOLSET: Final = "leaselab-slack-send"
CONFIG: Final = TypeAdapter(
    dict[str, JsonValue], config=ConfigDict(hide_input_in_errors=True)
)
MAPPING: Final = CONFIG
TOOLSETS: Final = TypeAdapter(
    dict[str, list[str]], config=ConfigDict(hide_input_in_errors=True)
)


def reconciled(config: dict[str, JsonValue], role: str) -> dict[str, JsonValue]:
    platform_toolsets = TOOLSETS.validate_python(config.get("platform_toolsets", {}))
    if "cli" not in platform_toolsets:
        raise typer.BadParameter(f"{role}: platform_toolsets.cli missing")
    if role == "chief-of-staff":
        platform_toolsets.setdefault("slack", list(platform_toolsets["cli"]))
    for names in platform_toolsets.values():
        if TOOLSET not in names:
            names.append(TOOLSET)
    platforms = MAPPING.validate_python(config.get("platforms", {}))
    if role == "chief-of-staff":
        slack = MAPPING.validate_python(platforms.get("slack", {}))
        extra = MAPPING.validate_python(slack.get("extra", {}))
        extra.update(
            {
                "allowed_channels": list(CHANNELS),
                "allowed_users": [FOUNDER],
                "require_mention": True,
                "strict_mention": True,
                "thread_require_mention": True,
                "allow_bots": "none",
                "disable_dms": True,
            }
        )
        slack.update({"enabled": True, "extra": extra})
        platforms["slack"] = slack
    else:
        # Disabled Slack blocks the native sender too; token-only config is outbound capable.
        platforms.pop("slack", None)
    result = dict(config)
    result["platform_toolsets"] = CONFIG.validate_python(platform_toolsets)
    result["platforms"] = platforms
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
    if role != "chief-of-staff" and "SLACK_APP_TOKEN" in values:
        raise typer.BadParameter(f"{role}: worker app-token entry forbidden")
    if role == "chief-of-staff":
        if (
            not values.get("SLACK_APP_TOKEN")
            or values.get("SLACK_ALLOWED_USERS") != FOUNDER
        ):
            raise typer.BadParameter(
                "chief-of-staff: external app token or exact founder allowlist missing"
            )
        for flag in ("SLACK_ALLOW_ALL_USERS", "GATEWAY_ALLOW_ALL_USERS"):
            if (values.get(flag) or "").lower() not in ("", "false", "0", "no"):
                raise typer.BadParameter(f"chief-of-staff: {flag} must be disabled")


def write_config(path: Path, content: str) -> None:
    previous = path.stat()
    descriptor, temporary = tempfile.mkstemp(prefix=".slack-config-", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w") as handle:
            os.fchmod(handle.fileno(), previous.st_mode & 0o777)
            if os.geteuid() == 0:
                os.fchown(handle.fileno(), previous.st_uid, previous.st_gid)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main(
    profiles_root: Path = Path("/var/lib/leaselab-company/profiles"),
    apply: bool = False,
) -> None:
    """Validate all seven profiles, then optionally update only Slack/toolset settings."""
    changes: list[tuple[Path, str]] = []
    for role in ROLES:
        directory = profiles_root / role
        path = directory / "config.yaml"
        if directory.is_symlink() or path.is_symlink():
            raise typer.BadParameter(f"{role}: symlinked configuration forbidden")
        check_credentials(directory, role)
        current = CONFIG.validate_python(yaml.safe_load(path.read_text()))
        desired = reconciled(current, role)
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
