"""Boundary tests for separate native Slack profile gateways."""

import importlib.util
from pathlib import Path

import pytest
import typer

SPEC = importlib.util.spec_from_file_location(
    "slack_config", Path(__file__).parents[1] / "slack" / "configure.py"
)
assert SPEC and SPEC.loader
config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(config)


def test_specialist_has_native_slack_without_telegram_or_dispatcher() -> None:
    original = {
        "platform_toolsets": {"cli": ["terminal"]},
        "platforms": {"telegram": {"enabled": True}},
        "model": "preserved",
    }
    result = config.reconciled(original, "engineer")
    assert result["platforms"]["slack"]["enabled"] is True
    assert result["platforms"]["telegram"] == {"enabled": False}
    assert result["kanban"]["dispatch_in_gateway"] is False
    assert result["gateway"]["multiplex_profiles"] is False
    assert result["model"] == "preserved"


def test_cos_keeps_existing_telegram_policy_and_dispatches() -> None:
    telegram = {"enabled": True, "extra": {"group_policy": "disabled"}}
    result = config.reconciled(
        {"platform_toolsets": {"cli": []}, "platforms": {"telegram": telegram}},
        "chief-of-staff",
    )
    assert result["platforms"]["telegram"] == telegram
    assert result["kanban"]["dispatch_in_gateway"] is True


def credentials(directory: Path, extra: str = "") -> None:
    directory.mkdir(exist_ok=True)
    path = directory / ".env"
    path.write_text(
        "SLACK_BOT_TOKEN=xoxb-test\nSLACK_APP_TOKEN=xapp-test\nSLACK_ALLOWED_USERS=U0225R7NP8Q\n"
        + extra
    )
    path.chmod(0o600)


def test_specialist_requires_app_token(tmp_path: Path) -> None:
    credentials(tmp_path)
    config.check_credentials(tmp_path, "engineer")
    (tmp_path / ".env").write_text(
        "SLACK_BOT_TOKEN=xoxb-test\nSLACK_ALLOWED_USERS=U0225R7NP8Q\n"
    )
    with pytest.raises(typer.BadParameter):
        config.check_credentials(tmp_path, "engineer")


def test_specialist_telegram_credential_rejected(tmp_path: Path) -> None:
    credentials(tmp_path, "TELEGRAM_BOT_TOKEN=unused\n")
    with pytest.raises(typer.BadParameter):
        config.check_credentials(tmp_path, "engineer")


def test_duplicate_role_credentials_rejected_before_any_write(tmp_path: Path) -> None:
    for role in config.ROLES:
        directory = tmp_path / role
        credentials(directory)
        (directory / "config.yaml").write_text("platform_toolsets:\n  cli: []\n")
    with pytest.raises(typer.BadParameter, match="distinct"):
        config.main(profiles_root=tmp_path, apply=True)
    assert all(
        (tmp_path / role / "config.yaml").read_text()
        == "platform_toolsets:\n  cli: []\n"
        for role in config.ROLES
    )


PREFLIGHT_SPEC = importlib.util.spec_from_file_location(
    "specialist_preflight",
    Path(__file__).parents[1] / "bootstrap" / "specialist-gateway-preflight.py",
)
assert PREFLIGHT_SPEC and PREFLIGHT_SPEC.loader
preflight = importlib.util.module_from_spec(PREFLIGHT_SPEC)
PREFLIGHT_SPEC.loader.exec_module(preflight)


@pytest.mark.parametrize(
    "unsafe",
    [
        "none",
        "dispatcher",
        "telegram",
        "inherited_telegram",
        "multiplex",
        "env_dispatcher",
    ],
)
def test_specialist_startup_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unsafe: str
) -> None:
    import yaml

    home = tmp_path / "engineer"
    credentials(home)
    desired = config.reconciled({"platform_toolsets": {"cli": []}}, "engineer")
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setenv("HERMES_PROFILE", "engineer")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_KANBAN_DISPATCH_IN_GATEWAY", "false")
    if unsafe == "dispatcher":
        desired["kanban"]["dispatch_in_gateway"] = True
    if unsafe == "telegram":
        desired["platforms"]["telegram"]["enabled"] = True
    if unsafe == "multiplex":
        desired["gateway"]["multiplex_profiles"] = True
    if unsafe == "env_dispatcher":
        credentials(home, "HERMES_KANBAN_DISPATCH_IN_GATEWAY=true\n")
    if unsafe == "inherited_telegram":
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-only")
    (home / "config.yaml").write_text(yaml.safe_dump(desired))
    assert preflight.main() == (0 if unsafe == "none" else 1)


def test_configure_uses_identity_channels_for_all_roles(tmp_path: Path) -> None:
    import json

    import yaml

    for index, role in enumerate(config.ROLES):
        directory = tmp_path / role
        credentials(directory)
        env = directory / ".env"
        _ = env.write_text(
            env.read_text()
            .replace("xoxb-test", f"xoxb-test{index}")
            .replace("xapp-test", f"xapp-test{index}")
        )
        _ = (directory / "config.yaml").write_text("platform_toolsets:\n  cli: []\n")
    mapping = tmp_path / "identities.json"
    _ = mapping.write_text(
        json.dumps(
            {
                "team_id": "T021CUR5KTP",
                "founder_user_id": "U0225R7NP8Q",
                "channels": ["CINCIDENTS"],
            }
        )
    )
    config.main(profiles_root=tmp_path, apply=True, identities_file=mapping)
    for role in config.ROLES:
        result = yaml.safe_load((tmp_path / role / "config.yaml").read_text())
        assert result["platforms"]["slack"]["extra"]["allowed_channels"] == [
            "CINCIDENTS"
        ]


@pytest.mark.parametrize("role", config.ROLES)
def test_slack_gateway_skips_local_ssh_context_and_has_role_home(role: str) -> None:
    result = config.reconciled(
        {
            "platform_toolsets": {"cli": []},
            "terminal": {"cwd": "/private/ssh/workspace"},
        },
        role,
    )
    assert result["gateway"]["platforms"]["slack"]["skip_context_files"] is True
    assert result["terminal"]["cwd"] == "/private/ssh/workspace"
    assert (
        result["platforms"]["slack"]["home_channel"]["chat_id"]
        == config.HOME_CHANNELS[role]
    )
