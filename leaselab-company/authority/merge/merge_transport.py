"""Fixed-origin transport reusing the reviewed broker's token exchange."""
import http.client
import json
import re
import ssl
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

from typing_extensions import override

# Installed sibling is root-owned, outside every role's writable workspace.
sys.path.insert(0, '/usr/local/libexec/leaselab-company/github-broker')
from merge_models import Request, Ruleset
from merge_observer import snapshot
from merge_policy import Denied
from policy import Role
from upstream import Token, mint


@dataclass(frozen=True, slots=True)
class MergeRole(Role):
    @property
    @override
    def key_path(self) -> Path:
        return Path('/etc/leaselab-company/merge/reviewer.pem')


GRANT: Final = MergeRole('reviewer', 4948588, 161807039, MappingProxyType({
    'metadata': 'read', 'contents': 'write', 'pull_requests': 'read',
    'checks': 'read', 'actions': 'read', 'statuses': 'read', 'issues': 'read'}))


class Client:
    """One short-lived service token, never returned through the Unix socket."""
    def __init__(self) -> None:
        self.token: Token = mint(GRANT)

    def request(self, path: str, body: str | None = None) -> bytes:
        if not path.startswith('/') or '..' in path or '#' in path or '\\' in path:
            raise Denied
        with closing(http.client.HTTPSConnection('api.github.com', timeout=10,
                                                context=ssl.create_default_context())) as connection:
            connection.request('GET' if body is None else 'PUT', '/repos/yangjeep/leaselab' + path,
                body=body, headers={
                    'Authorization': 'Bearer ' + self.token.value,
                    'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28',
                    'User-Agent': 'leaselab-merge-authority', 'Content-Type': 'application/json'})
            response = connection.getresponse()
            if response.status != 200 or response.getheader('Link'):
                raise Denied
            raw = response.read(2000001)
            if len(raw) > 2000000:
                raise Denied
            return raw

    def policy(self) -> tuple[Ruleset, ...]:
        return snapshot()

    def get(self, path: str) -> bytes:
        return self.request(path)

    def merge(self, request: Request) -> bytes:
        if not re.fullmatch('[0-9a-f]{40}', request.head):
            raise Denied
        return self.request(f'/pulls/{request.pr}/merge', json.dumps({
            'sha': request.head, 'merge_method': 'squash'}))
