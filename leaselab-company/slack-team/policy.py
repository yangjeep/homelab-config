"""Parse the fixed Slack identity boundary before native Hermes sees messages."""
from enum import StrEnum
from pathlib import Path
import re
import stat
from typing import ClassVar, Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

FOUNDER: Final = "U0225R7NP8Q"
TEAM: Final = "T021CUR5KTP"
COS: Final = "chief-of-staff"
ROLES: Final = frozenset({COS, "engineer", "reviewer", "qa-security", "sre", "support", "growth"})
IDENTITIES: Final = Path("/etc/leaselab-company/slack-identities.json")
MENTIONS: Final = re.compile(r"<@([A-Z0-9]+)(?:\|[^>]+)?>")


class BoundaryError(ValueError):
    """Identity configuration is not safe to use."""


class Identity(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)
    app_id: str = Field(pattern=r"^A[A-Z0-9]+$")
    bot_user_id: str = Field(pattern=r"^U[A-Z0-9]+$")


class Identities(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)
    team_id: str
    founder_user_id: str
    channels: list[str]
    incident_channel_id: str
    roles: dict[str, Identity]

    @model_validator(mode="after")
    def require_company_boundary(self) -> Self:
        valid = (
            self.team_id == TEAM and self.founder_user_id == FOUNDER
            and frozenset(self.roles) == ROLES
            and len({entry.app_id for entry in self.roles.values()}) == len(ROLES)
            and len({entry.bot_user_id for entry in self.roles.values()}) == len(ROLES)
            and bool(self.channels)
            and len(set(self.channels)) == len(self.channels)
            and all(re.fullmatch(r"C[A-Z0-9]+", cid) for cid in self.channels)
            and self.incident_channel_id in self.channels
        )
        if not valid:
            raise BoundaryError("invalid LeaseLab Slack identity boundary")
        return self


def load_identities(path: Path = IDENTITIES) -> Identities:
    """Only root-controlled, non-symlink configuration can select a profile."""
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise BoundaryError("Slack identity file must be root-owned and not writable by roles")
    return Identities.model_validate_json(path.read_bytes())


class Message(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore", strict=True)
    type: str
    user: str
    text: str
    channel: str
    ts: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    team: str | None = None
    team_id: str | None = None
    channel_type: str | None = None
    subtype: str | None = None
    bot_id: str | None = None
    bot_profile: dict[str, str] | None = None


class Envelope(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore", strict=True)
    type: str
    team_id: str
    api_app_id: str
    event: Message


class Decision(StrEnum):
    DIRECT = "direct"
    COORDINATE = "coordinate"
    BLOCK = "block"


def decision(payload: Envelope, role: str, identities: Identities) -> Decision:
    """Select exactly one role, or CoS for multiple known role mentions."""
    identity = identities.roles.get(role)
    event = payload.event
    if identity is None or (
        payload.type != "event_callback" or payload.team_id != identities.team_id
        or payload.api_app_id != identity.app_id
        or event.type not in {"message", "app_mention"}
        or event.user != identities.founder_user_id
        or event.channel not in identities.channels
        or event.team not in {None, identities.team_id}
        or event.team_id not in {None, identities.team_id}
        or event.channel_type not in {None, "channel", "group"}
        or event.subtype is not None or event.bot_id is not None or event.bot_profile is not None
    ):
        return Decision.BLOCK
    mentions = {match.group(1) for match in MENTIONS.finditer(event.text)}
    bot_roles = {entry.bot_user_id: owner for owner, entry in identities.roles.items()}
    if not mentions or not mentions <= bot_roles.keys():
        return Decision.BLOCK
    mentioned_roles = {bot_roles[uid] for uid in mentions}
    if len(mentioned_roles) > 1:
        return Decision.COORDINATE if role == COS else Decision.BLOCK
    return Decision.DIRECT if mentioned_roles == {role} else Decision.BLOCK
