"""Founder-only gateway preflight regression checks with synthetic configuration."""

import importlib.util
from pathlib import Path
from typing import TypedDict

import pytest

SPEC = importlib.util.spec_from_file_location(
    "gateway_policy", Path(__file__).parents[1] / "bootstrap" / "gateway-policy.py"
)
assert SPEC is not None and SPEC.loader is not None
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


ExtraValue = str | bool | list[str]


class TelegramFixture(TypedDict):
    enabled: bool
    extra: dict[str, ExtraValue]


class PlatformsFixture(TypedDict):
    telegram: TelegramFixture


class ConfigFixture(TypedDict):
    platforms: PlatformsFixture


def good_config() -> ConfigFixture:
    return {
        "platforms": {
            "telegram": {
                "enabled": True,
                "extra": {
                    "dm_policy": "allowlist",
                    "group_policy": "disabled",
                    "unauthorized_dm_behavior": "ignore",
                    "group_allow_from": [],
                    "allowed_chats": ["660328434"],
                    "guest_mode": False,
                },
            }
        }
    }


def good_values() -> dict[str, str]:
    return {"TELEGRAM_ALLOWED_USERS": "660328434", "TELEGRAM_HOME_CHANNEL": "660328434"}


def test_safe_policy_passes() -> None:
    assert policy.policy_valid(good_config(), good_values(), {})


@pytest.mark.parametrize(
    "flag", ["TELEGRAM_ALLOW_ALL_USERS", "GATEWAY_ALLOW_ALL_USERS"]
)
@pytest.mark.parametrize("value", ["true", "1", "yes", "TRUE", "unexpected"])
@pytest.mark.parametrize("source", ["profile", "process"])
def test_permissive_override_rejected(flag: str, value: str, source: str) -> None:
    values, environment = good_values(), {}
    (values if source == "profile" else environment)[flag] = value
    assert not policy.policy_valid(good_config(), values, environment)


@pytest.mark.parametrize("field", ["TELEGRAM_ALLOWED_USERS", "TELEGRAM_HOME_CHANNEL"])
@pytest.mark.parametrize("value", [None, "", "*", "660328434,123"])
def test_missing_or_wider_identity_rejected(field: str, value: str | None) -> None:
    values = good_values()
    if value is None:
        values.pop(field)
    else:
        values[field] = value
    assert not policy.policy_valid(good_config(), values, {})


@pytest.mark.parametrize(
    "field,value",
    [
        ("dm_policy", "open"),
        ("group_policy", "open"),
        ("unauthorized_dm_behavior", "pair"),
    ],
)
def test_config_policy_change_rejected(field: str, value: str) -> None:
    config = good_config()
    config["platforms"]["telegram"]["extra"][field] = value
    assert not policy.policy_valid(config, good_values(), {})


def test_disabled_telegram_rejected() -> None:
    config = good_config()
    config["platforms"]["telegram"]["enabled"] = False
    assert not policy.policy_valid(config, good_values(), {})


@pytest.mark.parametrize(
    "field",
    [
        "group_allow_from",
        "allowed_chats",
        "guest_mode",
        "dm_policy",
        "group_policy",
        "unauthorized_dm_behavior",
    ],
)
def test_missing_effective_field_rejected(field: str) -> None:
    config = good_config()
    config["platforms"]["telegram"]["extra"].pop(field)
    assert not policy.policy_valid(config, good_values(), {})


@pytest.mark.parametrize(
    "field,value",
    [("group_allow_from", ["*"]), ("allowed_chats", ["*"]), ("guest_mode", True)],
)
def test_group_boundary_widening_rejected(field: str, value: ExtraValue) -> None:
    config = good_config()
    config["platforms"]["telegram"]["extra"][field] = value
    assert not policy.policy_valid(config, good_values(), {})


@pytest.mark.parametrize(
    "flag,value",
    [
        ("TELEGRAM_GUEST_MODE", "true"),
        ("GATEWAY_ALLOWED_USERS", "*"),
        ("TELEGRAM_GROUP_ALLOWED_USERS", "660328434"),
        ("TELEGRAM_GROUP_ALLOWED_CHATS", "-1001"),
    ],
)
@pytest.mark.parametrize("source", ["profile", "process"])
def test_other_grants_rejected(flag: str, value: str, source: str) -> None:
    profile, environment = good_values(), {}
    (profile if source == "profile" else environment)[flag] = value
    assert not policy.policy_valid(good_config(), profile, environment)


def test_process_identity_override_rejected() -> None:
    assert not policy.policy_valid(
        good_config(), good_values(), {"TELEGRAM_ALLOWED_USERS": "*"}
    )


def test_adapter_dm_override_rejected() -> None:
    config = good_config()
    config["platforms"]["telegram"]["extra"]["allow_from"] = ["*"]
    assert not policy.policy_valid(config, good_values(), {})
