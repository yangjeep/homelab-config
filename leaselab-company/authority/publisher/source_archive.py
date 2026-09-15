"""Never extract tar metadata: verify blobs, then create only new regular files."""
import gzip
import hashlib
import io
import os
import tarfile
from pathlib import Path

from publisher_models import Denied
from source_models import Tree, git_hash, safe_path, verify_tree


def export(archive: bytes, tree: Tree, destination: Path) -> str:
    verify_tree(tree, tree.sha)
    if len(archive) > 67108864 or destination.exists() or destination.is_symlink():
        raise Denied
    expected = {e.path: e for e in tree.tree if e.type == 'blob'}
    seen: set[str] = set()
    directories = {e.path for e in tree.tree if e.type == 'tree'}
    root = ''
    total = 0
    digest = hashlib.sha256()
    destination.mkdir(mode=0o700)
    with gzip.GzipFile(fileobj=io.BytesIO(archive)) as compressed:
        decoded = compressed.read(150994945)
    if len(decoded) > 150994944:
        raise Denied
    for directory in directories:
        destination.joinpath(*safe_path(directory)).mkdir(parents=True, exist_ok=True, mode=0o700)
    with tarfile.open(fileobj=io.BytesIO(decoded), mode='r|') as stream:
        for count, member in enumerate(stream):
            if count > 10001 or member.size < 0 or member.size > 16777216:
                raise Denied
            name = member.name.rstrip('/') if member.isdir() else member.name
            parts = safe_path(name)
            if not root:
                root = parts[0]
            if parts[0] != root:
                raise Denied
            relative = '/'.join(parts[1:])
            if member.isdir():
                if relative and relative not in directories:
                    raise Denied
                continue
            if not member.isreg() or member.linkname or member.sparse is not None:
                raise Denied
            entry = expected.get(relative)
            if entry is None or relative in seen or member.size != entry.size:
                raise Denied
            total += member.size
            if total > 134217728:
                raise Denied
            source = stream.extractfile(member)
            if source is None:
                raise Denied
            with source:
                data = source.read(member.size + 1)
            if len(data) != member.size or git_hash('blob', data) != entry.sha:
                raise Denied
            target = destination.joinpath(*safe_path(relative))
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as output:
                _ = output.write(data)
                os.fsync(output.fileno())
            target.chmod(0o555 if entry.mode == '100755' else 0o444)
            digest.update(relative.encode() + b'\0' + bytes.fromhex(entry.sha))
            seen.add(relative)
    if seen != set(expected):
        raise Denied
    for directory in sorted(destination.rglob('*'), reverse=True):
        if directory.is_dir():
            directory.chmod(0o555)
    destination.chmod(0o555)
    return digest.hexdigest()
