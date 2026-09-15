"""Supervisor copies verified bytes into its own immutable source ownership."""
import os
import stat
from pathlib import Path

from publisher_models import Denied
from source_models import Tree, git_hash, safe_path, verify_tree


def seal(source: Path, destination: Path, tree: Tree) -> None:
    verify_tree(tree, tree.sha)
    if destination.exists() or destination.is_symlink():
        raise Denied
    expected = {e.path: e for e in tree.tree}
    actual: set[str] = set()
    owner = source.lstat().st_uid
    if source.is_symlink():
        raise Denied
    for path in source.rglob('*'):
        relative = path.relative_to(source).as_posix()
        entry = expected.get(relative)
        info = path.lstat()
        if info.st_uid != owner or entry is None or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise Denied
        if (entry.type == 'tree') != stat.S_ISDIR(info.st_mode):
            raise Denied
        if entry.type == 'blob' and info.st_nlink != 1:
            raise Denied
        actual.add(relative)
    if actual != set(expected):
        raise Denied
    destination.mkdir(mode=0o700)
    for entry in sorted(tree.tree, key=lambda e: (e.path.count('/'), e.path)):
        target = destination.joinpath(*safe_path(entry.path))
        if entry.type == 'tree':
            target.mkdir(mode=0o700)
            continue
        origin = source.joinpath(*safe_path(entry.path))
        fd = os.open(origin, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != entry.size:
                raise Denied
            data = stream.read(16777217)
            after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise Denied
        if len(data) != entry.size or git_hash('blob', data) != entry.sha:
            raise Denied
        with target.open('xb') as output:
            _ = output.write(data)
            output.flush()
            os.fsync(output.fileno())
        target.chmod(0o555 if entry.mode == '100755' else 0o444)
    for path in sorted(destination.rglob('*'), reverse=True):
        if path.is_dir():
            path.chmod(0o555)
    destination.chmod(0o555)


def metadata(path: Path, maximum: int) -> bytes:
    import pwd
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum
                or info.st_uid != pwd.getpwnam('leaselab-source-fetch').pw_uid):
            raise Denied
        result = stream.read(maximum + 1)
    if len(result) > maximum:
        raise Denied
    return result
