"""Root-only same-role external access-token snapshot; never copies refresh tokens."""
import fcntl
import json
import os
import pwd
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from executor_config import executor
from executor_launch import trusted
from publisher_models import Denied
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Tokens(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra='ignore')
    access_token: SecretStr
    account_id: str = Field(min_length=1)


class SourceAuth(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra='ignore')
    tokens: Tokens


def snapshot(role: str) -> None:
    if os.geteuid() != 0:
        raise Denied
    selected = executor(role)
    source_user = pwd.getpwnam('leaselab-' + selected.role)
    destination_user = pwd.getpwnam(selected.user)
    trusted(selected.root, directory=True)
    with (selected.root / 'lock').open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source = Path('/srv/leaselab/roles') / selected.role / '.codex/auth.json'
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if before.st_uid != source_user.pw_uid or before.st_mode & 0o077 or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise Denied
            contents = stream.read(65537)
            if len(contents) > 65536 or os.fstat(stream.fileno()) != before:
                raise Denied
        # Validation exceptions must never be printed: input includes auth values.
        try:
            auth = SourceAuth.model_validate_json(contents)
        except ValueError:
            raise Denied from None
        for directory in (selected.home, selected.home / '.codex'):
            info = directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != destination_user.pw_uid or info.st_mode & 0o077:
                raise Denied
        destination = selected.home / '.codex/auth.json'
        temporary = selected.home / '.codex/bootstrap.tmp'
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            token = auth.tokens.access_token.get_secret_value()
            json.dump({'auth_mode': 'chatgptAuthTokens', 'OPENAI_API_KEY': None,
                       'tokens': {'id_token': token, 'access_token': token, 'refresh_token': '',
                                  'account_id': auth.tokens.account_id},
                       'last_refresh': datetime.now(UTC).isoformat()}, stream)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchown(stream.fileno(), destination_user.pw_uid, destination_user.pw_gid)
        os.replace(temporary, destination)
        print('SAME_ROLE_EXTERNAL_TOKEN_SNAPSHOT_OK')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise Denied
        snapshot(sys.argv[1])
    except (Denied, OSError, KeyError, ValueError):
        print('AUTH_SNAPSHOT_DENIED', file=sys.stderr)
        raise SystemExit(1) from None
