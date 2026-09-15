"""Nonsecret, root-controlled Slack team directory for CoS coordination."""

import stat
from pathlib import Path
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import ROLES, ManagementError

DIRECTORY: Final = Path("/etc/leaselab-company/slack-identities.json")
Channel = Annotated[str, Field(pattern=r"^C[A-Z0-9]+$")]


class SlackIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)
    bot_user_id: str = Field(pattern=r"^U[A-Z0-9]+$")


class SlackDirectory(BaseModel):
    """Only public routing fields survive parsing and tool serialization."""

    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)
    team_id: Literal["T021CUR5KTP"]
    channels: list[Channel]
    incident_channel_id: Channel
    roles: dict[str, SlackIdentity]

    @model_validator(mode="after")
    def require_exact_team(self) -> Self:
        if (
            set(self.roles) != {*ROLES, "chief-of-staff"}
            or len({role.bot_user_id for role in self.roles.values()}) != 7
            or not self.channels
            or len(set(self.channels)) != len(self.channels)
            or self.incident_channel_id not in self.channels
        ):
            raise ManagementError("Invalid public Slack team directory")
        return self


def load_directory() -> SlackDirectory:
    """Read the fixed nonsecret map; reject role-writable files and symlinks."""
    info = DIRECTORY.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ManagementError(
            "Slack directory must be root-owned and not role-writable"
        )
    return SlackDirectory.model_validate_json(DIRECTORY.read_bytes())
