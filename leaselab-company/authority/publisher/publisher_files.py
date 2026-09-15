"""Bounded descriptor-relative atomic files inside a private service directory."""
import fcntl
import os
import re
import secrets
import stat
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Final, Self

from publisher_models import Denied

LIMIT: Final = 16384
NAME: Final = re.compile(r'(?:[0-9a-f]{64}\.json|current-[1-9][0-9]{0,9}\.json)')


def regular(fd: int, modes: tuple[int, ...]) -> None:
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) not in modes):
        raise Denied


@dataclass(frozen=True, slots=True)
class Blob:
    payload: bytes
    final: bool


class Files:
    """Owns one directory descriptor; no caller-supplied artifact paths are consumed."""
    def __init__(self, root: Path) -> None:
        if root != root.absolute() or root.resolve() != root:
            raise Denied
        self.fd: int = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(self.fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            os.close(self.fd)
            raise Denied

    def __enter__(self) -> Self:
        return self

    def __exit__(self, _kind: type[BaseException] | None,
                 _error: BaseException | None, _traceback: TracebackType | None) -> None:
        os.close(self.fd)

    @contextmanager
    def lock(self) -> Generator[None]:
        fd = os.open('.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=self.fd)
        with os.fdopen(fd, 'r+b') as stream:
            regular(stream.fileno(), (0o600,))
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def read(self, name: str) -> Blob | None:
        if not NAME.fullmatch(name):
            raise Denied
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, 'rb') as stream:
            regular(stream.fileno(), (0o600, 0o400))
            content = stream.read(LIMIT + 1)
            if len(content) > LIMIT:
                raise Denied
            return Blob(content, stat.S_IMODE(os.fstat(stream.fileno()).st_mode) == 0o400)

    def write(self, name: str, payload: bytes, *, final: bool = False) -> None:
        if not NAME.fullmatch(name) or len(payload) > LIMIT:
            raise Denied
        existing = self.read(name)
        if existing is not None:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
            with os.fdopen(fd, 'rb') as stream:
                regular(stream.fileno(), (0o600,))
        temporary = '.tmp-' + secrets.token_hex(16)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.fd)
        try:
            with os.fdopen(fd, 'wb') as stream:
                _ = stream.write(payload)
                stream.flush()
                os.fchmod(stream.fileno(), 0o400 if final else 0o600)
                os.fsync(stream.fileno())
            os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            os.fsync(self.fd)
        finally:
            # Atomic replacement consumes the temporary name; preserve any original error.
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=self.fd)
