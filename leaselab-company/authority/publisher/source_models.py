"""Strict GitHub source identities and cryptographically checked Git trees."""
import hashlib
import unicodedata
from typing import Annotated, ClassVar, Literal

from publisher_models import Denied, Record, Sha
from pydantic import ConfigDict, Field


class Pair(Record):
    head: Sha
    base: Sha


class APIRecord(Record):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, strict=True, extra='ignore')


class TreeIdentity(APIRecord):
    sha: Sha


class Commit(APIRecord):
    sha: Sha
    tree: TreeIdentity


class Entry(APIRecord):
    path: str
    mode: Literal['100644', '100755', '040000']
    type: Literal['blob', 'tree']
    sha: Sha
    size: Annotated[int, Field(ge=0, le=16777216)] | None = None


class Tree(APIRecord):
    sha: Sha
    truncated: Literal[False]
    tree: Annotated[tuple[Entry, ...], Field(max_length=10000)]


def safe_path(value: str) -> tuple[str, ...]:
    parts = tuple(value.split('/'))
    if len(value.encode()) > 1024 or len(parts) > 32:
        raise Denied
    for part in parts:
        if (part in ('', '.', '..') or len(part.encode()) > 255
                or any(ord(c) < 32 or ord(c) == 127 or c in '\\:' for c in part)
                or unicodedata.normalize('NFKC', part).rstrip('. ').casefold() == '.git'):
            raise Denied
    return parts


def git_hash(kind: str, data: bytes) -> str:
    """Git object identity uses SHA-1; this is not password cryptography."""
    return hashlib.sha1(kind.encode() + b' ' + str(len(data)).encode() + b'\0' + data,
                        usedforsecurity=False).hexdigest()


def verify_tree(tree: Tree, expected: str) -> None:
    if tree.sha != expected:
        raise Denied
    entries: dict[str, Entry] = {}
    folded: set[str] = set()
    total = 0
    children: dict[str, list[Entry]] = {'': []}
    for entry in tree.tree:
        parts = safe_path(entry.path)
        normalized = unicodedata.normalize('NFKC', entry.path).casefold()
        if normalized in folded:
            raise Denied
        folded.add(normalized)
        entries[entry.path] = entry
        if (entry.type == 'tree') != (entry.mode == '040000'):
            raise Denied
        if entry.type == 'blob':
            if entry.size is None:
                raise Denied
            total += entry.size
        children.setdefault('/'.join(parts[:-1]), []).append(entry)
        if entry.type == 'tree':
            _ = children.setdefault(entry.path, [])
    if total > 134217728:
        raise Denied
    for directory, members in children.items():
        if directory and (directory not in entries or entries[directory].type != 'tree'):
            raise Denied
        ordered = sorted(members, key=lambda e: (e.path.rsplit('/', 1)[-1] + ('/' if e.type == 'tree' else '')).encode())
        raw = b''.join(e.mode.lstrip('0').encode() + b' ' + e.path.rsplit('/', 1)[-1].encode() + b'\0' + bytes.fromhex(e.sha) for e in ordered)
        sha = entries[directory].sha if directory else expected
        if git_hash('tree', raw) != sha:
            raise Denied
