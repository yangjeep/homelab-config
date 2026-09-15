"""Fixed GitHub API/codeload origins, with broker token confined to this process."""
import os
import pwd
import re
import socket
import sys
from urllib.parse import urlsplit

import httpx2
from publisher_models import Denied
from pydantic import SecretStr
from source_models import Commit, Tree, verify_tree


def credential() -> SecretStr:
    if os.getuid() != pwd.getpwnam('leaselab-source-fetch').pw_uid:
        raise Denied
    sys.path.insert(0, '/usr/local/libexec/leaselab-company/github-broker')
    from credential_helper import obtain
    from policy import Denied as BrokerDenied
    try:
        return SecretStr(obtain())
    except (BrokerDenied, OSError, ValueError):
        raise Denied from None


def client() -> httpx2.Client:
    limits = httpx2.Limits(max_connections=200, max_keepalive_connections=40, keepalive_expiry=30)
    transport = httpx2.HTTPTransport(http2=True, retries=3, limits=limits, trust_env=False,
                                    socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)])
    return httpx2.Client(transport=transport, trust_env=False, follow_redirects=False,
                         timeout=httpx2.Timeout(connect=5, read=30, write=10, pool=10))


def bounded(response: httpx2.Response, maximum: int) -> bytes:
    result = bytearray()
    for part in response.iter_bytes():
        result.extend(part)
        if len(result) > maximum:
            raise Denied
    return bytes(result)


def archive_location(value: str, sha: str) -> str:
    location = urlsplit(value)
    if (location.scheme != 'https' or location.netloc != 'codeload.github.com'
            or location.fragment or location.path != f'/yangjeep/leaselab/legacy.tar.gz/{sha}'):
        raise Denied
    return value


class GitHub:
    def __init__(self, transport: httpx2.Client, token: SecretStr) -> None:
        self.transport: httpx2.Client = transport
        self.token: SecretStr = token

    def api(self, suffix: str) -> bytes:
        with self.transport.stream('GET', 'https://api.github.com/repos/yangjeep/leaselab' + suffix,
                headers={'Authorization': 'Bearer ' + self.token.get_secret_value(),
                         'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                         'User-Agent': 'leaselab-trusted-source'}) as response:
            if response.status_code != 200 or 'Link' in response.headers:
                raise Denied
            return bounded(response, 8388608)

    def tree(self, sha: str) -> Tree:
        if not re.fullmatch('[0-9a-f]{40}', sha):
            raise Denied
        commit = Commit.model_validate_json(self.api('/git/commits/' + sha))
        if commit.sha != sha:
            raise Denied
        tree = Tree.model_validate_json(self.api('/git/trees/' + commit.tree.sha + '?recursive=1'))
        verify_tree(tree, commit.tree.sha)
        return tree

    def archive(self, sha: str) -> bytes:
        if not re.fullmatch('[0-9a-f]{40}', sha):
            raise Denied
        with self.transport.stream('GET', 'https://api.github.com/repos/yangjeep/leaselab/tarball/' + sha,
                headers={'Authorization': 'Bearer ' + self.token.get_secret_value(),
                         'User-Agent': 'leaselab-trusted-source'}) as response:
            if response.status_code != 302:
                raise Denied
            target = archive_location(response.headers.get('Location', ''), sha)
        # API bearer is never sent to the archive host; signed URL stays in memory.
        with self.transport.stream('GET', target, headers={'User-Agent': 'leaselab-trusted-source'}) as response:
            if response.status_code != 200:
                raise Denied
            return bounded(response, 67108864)
