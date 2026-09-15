"""Immutable shell role grants; service-held elevated grants never enter here."""
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Mapping


class Denied(Exception):
    """A request or credential failed the fixed broker policy."""


@dataclass(frozen=True, slots=True)
class Role:
    name: str
    app_id: int
    installation_id: int | None
    permissions: Mapping[str, str]

    @property
    def key_path(self) -> Path:
        return Path('/etc/leaselab-company/github') / f'{self.name}.pem'


def grant(name: str, ids: tuple[int, int | None], **permissions: str) -> Role:
    return Role(name, *ids, MappingProxyType({'metadata': 'read', **permissions}))


ROLES: Final = (
    grant('chief-of-staff', (4948371, 161803163), contents='read', issues='write', pull_requests='write'),
    grant('support', (4948622, 161807858), contents='read', issues='write', pull_requests='read'),
    grant('growth', (4948599, 161807370), contents='read', issues='write', pull_requests='read'),
    grant('qa-security', (4948555, 161806533), contents='read', actions='read', checks='read', statuses='read', issues='write', pull_requests='write'),
    grant('reviewer', (4948588, 161807039), contents='read', actions='read', checks='read', statuses='read', issues='write', pull_requests='write'),
    grant('sre', (4948651, 161808475), contents='read', actions='read', checks='read', statuses='read', deployments='read', issues='read', pull_requests='read'),
    grant('engineer', (4948533, None)),
)
SOCKET: Final = '/run/leaselab-github/broker.sock'
