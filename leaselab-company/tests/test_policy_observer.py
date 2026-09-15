"""Offline observer boundaries and real Unix socket framing; no credentials."""
import json
import os
import socket
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'github-broker'))
sys.path.insert(0, str(ROOT / 'authority/policy-observer'))
from observer_models import Config, Denied, Request
from observer_policy import PREFIX, Response, allowed_path, observe
from observer_socket import serve
from observer_transport import Client

NONCE = 'a' * 64
REQUEST = Request(nonce=NONCE)


class Fake:
    def __init__(self) -> None:
        self.data = {'id': 1, 'name': 'policy', 'source_type': 'Repository',
                     'source': 'yangjeep/leaselab', 'enforcement': 'active',
                     'created_at': '2026-09-15T00:00:00Z', 'updated_at': '2026-09-15T00:00:00Z',
                     'target': 'branch', 'conditions': {'ref_name': {'include': ['refs/heads/main'], 'exclude': []}},
                     'rules': [{'type': 'update', 'future_semantics': {'keep': True}}],
                     'bypass_actors': [], 'future_top_level': {'keep': True}}
        self.calls: list[str] = []
        self.pages: dict[int, Response] = {}
        self.detail_link: str | None = None

    def get(self, path: str) -> Response:
        self.calls.append(path)
        if path.startswith(PREFIX + '?'):
            page = int(path.split('page=')[-1])
            return self.pages.get(page, Response(json.dumps([self.data]).encode()))
        return Response(json.dumps(self.data).encode(), self.detail_link)


def test_complete_policy_when_upstream_is_full():
    # Given: trusted complete full-visibility GitHub response.
    reader = Fake()
    # When: one fresh observation is requested.
    result = observe(reader, REQUEST)
    # Then: nonce and every semantic field are retained without a verdict.
    payload = json.loads(result.model_dump_json())
    assert payload['nonce'] == NONCE
    assert payload['rulesets'][0] == reader.data
    assert reader.calls == [PREFIX + '?includes_parents=true&per_page=100&page=1',
                            PREFIX + '/1?includes_parents=true']
    assert 'approved' not in payload


@pytest.mark.parametrize('field', ['bypass_actors', 'conditions', 'rules', 'updated_at', 'source'])
def test_denies_when_required_policy_field_is_missing(field):
    # Given: incomplete policy visibility.
    reader = Fake()
    del reader.data[field]
    # When / Then: missing bypass is never interpreted as empty.
    with pytest.raises(ValidationError):
        observe(reader, REQUEST)


@pytest.mark.parametrize('field,value', [('bypass_actors', None), ('id', True), ('target', 'other'),
                                         ('source_type', 'unknown'), ('enforcement', 'unknown')])
def test_denies_when_upstream_shape_is_invalid(field, value):
    # Given: malformed authority evidence.
    reader = Fake()
    reader.data[field] = value
    # When / Then: no observation is issued.
    with pytest.raises(ValidationError):
        observe(reader, REQUEST)


@pytest.mark.parametrize('body', [b'[]', b'null', b'[{}]', b'invalid'])
def test_denies_when_inventory_is_unusable(body):
    # Given: empty or malformed inventory.
    reader = Fake()
    reader.pages[1] = Response(body)
    # When / Then: no evidence is issued.
    with pytest.raises((Denied, ValidationError)):
        observe(reader, REQUEST)


@pytest.mark.parametrize('link', ['<https://evil.example/x>; rel="next"',
                                  '<https://api.github.com/repos/other/repo/rulesets>; rel="next"',
                                  'garbage'])
def test_denies_when_pagination_is_untrusted(link):
    # Given: an upstream link outside the constructed next-page path.
    reader = Fake()
    reader.pages[1] = Response(json.dumps([reader.data]).encode(), link)
    # When / Then: no link is followed.
    with pytest.raises(Denied):
        observe(reader, REQUEST)
    assert len(reader.calls) == 1


def test_denies_when_inventory_has_duplicates():
    # Given: duplicated ruleset identity.
    reader = Fake()
    reader.pages[1] = Response(json.dumps([reader.data, reader.data]).encode())
    # When / Then: completeness is not guessed.
    with pytest.raises(Denied):
        observe(reader, REQUEST)


def test_reads_next_page_when_pagination_is_complete():
    # Given: valid fixed-origin pagination metadata.
    reader = Fake()
    reader.pages[1] = Response(json.dumps([reader.data]).encode(),
        f'<https://api.github.com{PREFIX}?includes_parents=true&per_page=100&page=2>; rel="next"')
    reader.pages[2] = Response(b'[]')
    # When: the complete inventory is collected.
    result = observe(reader, REQUEST)
    # Then: every page was read before details.
    assert len(result.rulesets) == 1
    assert 'page=2' in reader.calls[1]


def test_denies_when_full_page_lacks_pagination():
    # Given: a full page with no completeness indication.
    reader = Fake()
    reader.pages[1] = Response(json.dumps([dict(reader.data, id=i) for i in range(1, 101)]).encode())
    # When / Then: fail closed instead of truncating.
    with pytest.raises(Denied):
        observe(reader, REQUEST)


@pytest.mark.parametrize('path', ['/repos/yangjeep/leaselab', PREFIX, PREFIX + '/0?includes_parents=true',
    PREFIX + '/2147483648?includes_parents=true', PREFIX + '/1', PREFIX + '/../issues',
    PREFIX + '/1?includes_parents=false', PREFIX + '?includes_parents=true&per_page=100&page=5',
    'https://api.github.com' + PREFIX, PREFIX + '/1?includes_parents=true#x'])
def test_rejects_when_path_is_outside_fixed_surface(path):
    # Given / When: a caller attempts another API path.
    permitted = allowed_path(path)
    # Then: it cannot cross the network boundary.
    assert permitted is False


@pytest.mark.parametrize('raw', [b'{}', b'null', b'{"nonce":"short"}',
    json.dumps({'nonce': NONCE, 'url': 'https://evil.example'}).encode(),
    json.dumps({'nonce': NONCE, 'verdict': 'approve'}).encode(),
    json.dumps({'nonce': NONCE, 'uid': 0}).encode()])
def test_rejects_when_request_contains_claims_or_invalid_nonce(raw):
    # Given / When / Then: strict parsing rejects arbitrary authority or destinations.
    with pytest.raises(ValidationError):
        Request.model_validate_json(raw)


@pytest.mark.parametrize('config', [Config(), Config(enabled=True), Config(enabled=True, app_id=1)])
def test_denies_before_mint_when_configuration_is_disabled_or_incomplete(config):
    # Given / When / Then: disabled examples never reach key access or token mint.
    with pytest.raises(Denied):
        Client(config)


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Linux SO_PEERCRED required')
@pytest.mark.parametrize('accepted,body', [(True, REQUEST.model_dump_json().encode()),
    (False, REQUEST.model_dump_json().encode()), (True, b'x' * 257)])
def test_unix_socket_when_peer_and_framing_are_checked(accepted, body):
    # Given: actual kernel-authenticated connected Unix sockets and synthetic upstream.
    first, second = socket.socketpair()
    reader = Fake()
    expected_uid = os.geteuid() if accepted else os.geteuid() + 1
    with first, second:
        second.sendall(body)
        second.shutdown(socket.SHUT_WR)
        # When: the production socket handler serves the actual connection.
        serve(first, expected_uid, lambda: reader)
        payload = json.loads(second.recv(2000000))
    # Then: wrong peers and oversize requests never reach the reader.
    if accepted and len(body) <= 256:
        assert payload['nonce'] == NONCE
        assert reader.calls
    else:
        assert payload == {'error': 'policy_unavailable'}
        assert reader.calls == []


@pytest.mark.parametrize('status,body,encoding', [(302, b'{}', None), (403, b'{}', None),
                                                 (200, b'x' * 2000001, None), (200, b'{}', 'gzip')])
def test_transport_denies_when_response_is_untrusted(monkeypatch, status, body, encoding):
    # Given: a synthetic TLS transport and synthetic token; no key or network access.
    import observer_transport
    from upstream import Token
    monkeypatch.setattr(observer_transport, 'mint', lambda role: Token('synthetic-test-token', 0))
    captured = []

    class Connection:
        def __init__(self, host, **kwargs):
            captured.append(host)

        def request(self, method, path, **kwargs):
            captured.append((method, path))

        def getresponse(self):
            return self

        def getheader(self, name):
            return encoding if name == 'Content-Encoding' else None

        def read(self, limit):
            return body[:limit]

        def close(self):
            return None

    Connection.status = status
    monkeypatch.setattr(observer_transport.http.client, 'HTTPSConnection', Connection)
    client = Client(Config(enabled=True, app_id=1, installation_id=2))
    # When / Then: redirects, errors, encoding and excess body size fail closed.
    with pytest.raises(Denied):
        client.get(PREFIX + '/1?includes_parents=true')
    assert captured == ['api.github.com', ('GET', PREFIX + '/1?includes_parents=true')]


def test_exact_privileged_grant_when_minting(monkeypatch):
    # Given: a recording token minter with no actual credential access.
    import observer_transport
    from upstream import Token
    captured = []

    def mint(role):
        captured.append(role)
        return Token('synthetic-test-token', 0)

    monkeypatch.setattr(observer_transport, 'mint', mint)
    # When: the enabled, provisioned transport is constructed.
    Client(Config(enabled=True, app_id=1, installation_id=2))
    # Then: the exact fixed grant and custody path are used.
    assert len(captured) == 1
    assert dict(captured[0].permissions) == {'administration': 'write', 'metadata': 'read'}
    assert str(captured[0].key_path) == '/etc/leaselab-company/policy-observer/observer.pem'
