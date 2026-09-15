"""Fixed GitHub installation-token exchange; stdlib TLS and installed OpenSSL."""
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import http.client
import json
import os
import re
import ssl
import stat
import subprocess
import time

from policy import Denied, Role


@dataclass(frozen=True, slots=True)
class Token:
    value: str
    expires: float


def encoded(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b'=')


def jwt(role: Role) -> str:
    """Sign without exposing key bytes or JWT in command arguments or diagnostics."""
    fd = os.open(role.key_path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as key:
        info = os.fstat(key.fileno())
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid() or info.st_nlink != 1):
            raise Denied
        now = int(time.time())
        header = encoded(b'{"alg":"RS256","typ":"JWT"}')
        payload = encoded(json.dumps({'iat': now - 60, 'exp': now + 540, 'iss': str(role.app_id)}).encode())
        message = header + b'.' + payload
        result = subprocess.run(
            ['/usr/bin/openssl', 'dgst', '-sha256', '-sign', f'/dev/fd/{key.fileno()}'],
            input=message, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            pass_fds=(key.fileno(),), timeout=5, check=True,
            env={'PATH': '/usr/bin:/bin'},
        )
    return (message + b'.' + encoded(result.stdout)).decode('ascii')


def exchange(role: Role, assertion: str) -> bytes:
    """No proxies, redirects, configurable origin, or unconstrained permissions."""
    connection = http.client.HTTPSConnection('api.github.com', timeout=10, context=ssl.create_default_context())
    try:
        connection.request('POST', f'/app/installations/{role.installation_id}/access_tokens',
            body=json.dumps({'repositories': ['leaselab'], 'permissions': dict(role.permissions)}),
            headers={'Authorization': f'Bearer {assertion}', 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'leaselab-role-broker',
                     'Content-Type': 'application/json'})
        response = connection.getresponse()
        if response.status != 201:
            raise Denied
        body = response.read(65537)
        if len(body) > 65536:
            raise Denied
        return body
    finally:
        connection.close()


def parse_token(raw: bytes, role: Role) -> Token:
    """Reject unexpected upstream authority before releasing any bearer token."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise Denied
    value = data.get('token')
    expiry = data.get('expires_at')
    repos = data.get('repositories')
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{10,512}', value)
            or not isinstance(expiry, str) or data.get('permissions') != dict(role.permissions)
            or not isinstance(repos, list) or len(repos) != 1
            or not isinstance(repos[0], dict) or repos[0].get('full_name') != 'yangjeep/leaselab'):
        raise Denied
    parsed = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise Denied
    expires = parsed.astimezone(timezone.utc).timestamp()
    remaining = expires - time.time()
    if not 60 < remaining <= 3660:
        raise Denied
    return Token(value, expires)


def mint(role: Role) -> Token:
    if role.installation_id is None:
        raise Denied
    return parse_token(exchange(role, jwt(role)), role)
