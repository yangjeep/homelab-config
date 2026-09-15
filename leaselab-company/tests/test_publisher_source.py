"""Hostile source names, archive contents and source identity boundaries."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'authority/publisher'))
from publisher_models import Denied
from source_models import safe_path


@pytest.mark.parametrize('value', ['/root/key', '../key', 'a/../../key', 'a//b', 'a/./b', '.git/config', 'a/.GiT/config', 'a\\b', 'a:b', 'a\x00b', 'a\nb', 'a/' , 'a/.git. /config'])
def test_hostile_paths_are_rejected(value: str) -> None:
    # Given an archive/tree-controlled pathname.
    # When parsed, then it cannot become an output pathname.
    with pytest.raises(Denied):
        safe_path(value)


def test_normal_repository_path_is_retained() -> None:
    # Given a real repository path, when parsed, then exact components survive.
    assert safe_path('apps/storefront/package.json') == ('apps','storefront','package.json')

import io
import tarfile

from source_archive import export
from source_models import Entry, Tree, git_hash, verify_tree


def fixture_tree() -> Tree:
    blob = git_hash('blob', b'hello\n')
    root = git_hash('tree', b'100644 readme.txt\0' + bytes.fromhex(blob))
    return Tree(sha=root, truncated=False, tree=(Entry(path='readme.txt', mode='100644', type='blob', sha=blob, size=6),))


def archive(name: str = 'repo/readme.txt', content: bytes = b'hello\n', kind: bytes = tarfile.REGTYPE) -> bytes:
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w:gz') as stream:
        entry = tarfile.TarInfo(name)
        entry.type = kind
        entry.linkname = '/etc/passwd' if kind != tarfile.REGTYPE else ''
        entry.size = len(content) if kind == tarfile.REGTYPE else 0
        stream.addfile(entry, io.BytesIO(content) if kind == tarfile.REGTYPE else None)
    return result.getvalue()


def test_exact_blob_is_exported_immutable(tmp_path: Path) -> None:
    # Given a Git tree and matching archive, when exported, then only exact blob bytes exist.
    target = tmp_path / 'source'
    export(archive(), fixture_tree(), target)
    assert (target / 'readme.txt').read_bytes() == b'hello\n'
    assert (target / 'readme.txt').stat().st_mode & 0o777 == 0o444
    assert target.stat().st_mode & 0o777 == 0o555


@pytest.mark.parametrize('kind', [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE])
def test_archive_special_entries_are_denied(tmp_path: Path, kind: bytes) -> None:
    # Given an archive-controlled special node, when exported, then nothing follows its target.
    with pytest.raises(Denied):
        export(archive(kind=kind), fixture_tree(), tmp_path / 'source')


@pytest.mark.parametrize('name', ['repo/../readme.txt', '/repo/readme.txt', 'repo/.git/config', 'repo/unexpected'])
def test_archive_paths_must_match_tree(tmp_path: Path, name: str) -> None:
    with pytest.raises(Denied):
        export(archive(name=name), fixture_tree(), tmp_path / 'source')


def test_altered_blob_is_denied(tmp_path: Path) -> None:
    with pytest.raises(Denied):
        export(archive(content=b'other\n'), fixture_tree(), tmp_path / 'source')


def test_tree_root_cannot_be_claimed_without_matching_objects() -> None:
    with pytest.raises(Denied):
        verify_tree(fixture_tree(), '0' * 40)


def test_existing_destination_is_never_reused(tmp_path: Path) -> None:
    target = tmp_path / 'source'
    target.mkdir()
    (target/'unrelated').write_text('preserve')
    with pytest.raises(Denied):
        export(archive(), fixture_tree(), target)
    assert (target/'unrelated').read_text() == 'preserve'


def test_duplicate_file_is_denied(tmp_path: Path) -> None:
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w:gz') as stream:
        for _ in range(2):
            entry=tarfile.TarInfo('repo/readme.txt');entry.size=6
            stream.addfile(entry,io.BytesIO(b'hello\n'))
    with pytest.raises(Denied):
        export(result.getvalue(), fixture_tree(), tmp_path/'source')

import httpx2
from pydantic import SecretStr, ValidationError
from source_fetch import GitHub, archive_location
from source_seal import seal


def test_root_copy_rechecks_blob_after_fetch(tmp_path: Path) -> None:
    incoming=tmp_path/'incoming'
    export(archive(),fixture_tree(),incoming)
    (incoming/'readme.txt').chmod(0o644)
    (incoming/'readme.txt').write_bytes(b'other\n')
    with pytest.raises(Denied):
        seal(incoming,tmp_path/'sealed',fixture_tree())


def test_root_copy_rejects_added_symlink(tmp_path: Path) -> None:
    incoming=tmp_path/'incoming'
    export(archive(),fixture_tree(),incoming)
    incoming.chmod(0o755)
    (incoming/'evil').symlink_to('/etc/passwd')
    with pytest.raises(Denied):
        seal(incoming,tmp_path/'sealed',fixture_tree())


def test_root_copy_has_independent_inode(tmp_path: Path) -> None:
    incoming=tmp_path/'incoming'
    export(archive(),fixture_tree(),incoming)
    target=tmp_path/'sealed'
    seal(incoming,target,fixture_tree())
    assert (incoming/'readme.txt').stat().st_ino != (target/'readme.txt').stat().st_ino
    assert (target/'readme.txt').read_bytes()==b'hello\n'


@pytest.mark.parametrize('url',['http://codeload.github.com/yangjeep/leaselab/legacy.tar.gz/','https://evil.test/','https://codeload.github.com@evil.test/','https://codeload.github.com/other/repo/legacy.tar.gz/'])
def test_archive_redirect_is_fixed_origin_and_repo(url: str) -> None:
    with pytest.raises(Denied):
        archive_location(url+'a'*40,'a'*40)


def test_archive_bearer_never_crosses_redirect() -> None:
    observed=[]
    def handler(request: httpx2.Request) -> httpx2.Response:
        observed.append(request.headers.get('Authorization'))
        if request.url.host=='api.github.com':
            return httpx2.Response(302,headers={'Location':'https://codeload.github.com/yangjeep/leaselab/legacy.tar.gz/'+'a'*40+'?token=synthetic'})
        return httpx2.Response(200,content=b'archive')
    with httpx2.Client(transport=httpx2.MockTransport(handler)) as transport:
        assert GitHub(transport,SecretStr('synthetic-only')).archive('a'*40)==b'archive'
    assert observed==['Bearer synthetic-only',None]


@pytest.mark.parametrize('changes', [{'truncated':True},{'sha':'bad'},{'tree':[{'path':'x','mode':'120000','type':'blob','sha':'a'*40,'size':1}]}])
def test_unusable_api_tree_is_rejected(changes) -> None:
    data=fixture_tree().model_dump(mode='json')
    data.update(changes)
    with pytest.raises((ValidationError,Denied)):
        tree=Tree.model_validate_json(__import__('json').dumps(data))
        verify_tree(tree,fixture_tree().sha)
