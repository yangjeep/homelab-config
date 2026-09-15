"""Fixed GitHub reads; service-held Administration-write token is never exported."""
import http.client
import ssl
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from typing_extensions import override

sys.path.insert(0, '/usr/local/libexec/leaselab-company/github-broker')
from observer_models import Config, Denied
from observer_policy import Response, allowed_path
from policy import Role
from upstream import Token, mint


@dataclass(frozen=True, slots=True)
class ObserverRole(Role):
    @property
    @override
    def key_path(self) -> Path:
        return Path('/etc/leaselab-company/policy-observer/observer.pem')


class Client:
    def __init__(self, config: Config) -> None:
        if not config.enabled or config.app_id is None or config.installation_id is None:
            raise Denied('observer disabled or unprovisioned')
        role = ObserverRole('policy-observer', config.app_id, config.installation_id,
                            MappingProxyType({'administration': 'write', 'metadata': 'read'}))
        self._token: Token = mint(role)

    def get(self, path: str) -> Response:
        if not allowed_path(path):
            raise Denied('path forbidden')
        with closing(http.client.HTTPSConnection('api.github.com', timeout=10,
                                                context=ssl.create_default_context())) as connection:
            connection.request('GET', path, headers={
                'Authorization': 'Bearer ' + self._token.value,
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
                'User-Agent': 'leaselab-policy-observer', 'Cache-Control': 'no-cache'})
            response = connection.getresponse()
            if response.status != 200 or response.getheader('Content-Encoding'):
                raise Denied('upstream response denied')
            raw = response.read(2000001)
            if len(raw) > 2000000:
                raise Denied('upstream response too large')
            return Response(raw, response.getheader('Link'))
