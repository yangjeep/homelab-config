"""Broker protocol, scope and Linux peer-credential boundaries."""
import importlib
import os
from pathlib import Path
import socket
import sys
import threading

import pytest

BROKER = Path(__file__).parents[1] / 'github-broker'
sys.path.insert(0, str(BROKER))


def test_rejects_role_selection_before_mint():
    # Given
    broker = importlib.import_module('broker')
    # When / Then
    with pytest.raises(broker.Denied):
        broker.parse_request(b'get reviewer\n')


@pytest.mark.parametrize('raw', [b'', b'get', b'get\nget\n', b'{"role":"reviewer"}', b'get /etc/key\n', b'get contents=write\n', b'x' * 500])
def test_rejects_nonliteral_requests(raw):
    # Given
    broker = importlib.import_module('broker')
    # When / Then
    with pytest.raises(broker.Denied):
        broker.parse_request(raw)


def test_scope_has_no_shell_elevation():
    # Given
    policy = importlib.import_module('policy')
    # When
    roles = {role.name: role for role in policy.ROLES}
    # Then
    assert roles['engineer'].installation_id is None
    for name, role in roles.items():
        if name != 'engineer':
            assert role.permissions['contents'] == 'read'
        assert set(key for key, level in role.permissions.items() if level == 'write') <= {'issues', 'pull_requests'}
    assert roles['qa-security'].permissions['checks'] == 'read'
    assert roles['reviewer'].permissions['checks'] == 'read'
    assert roles['sre'].permissions['deployments'] == 'read'


@pytest.mark.parametrize('uid', [0, 555, 102])
def test_unknown_root_and_disabled_identity_never_mints(uid):
    # Given
    broker = importlib.import_module('broker')
    def forbidden(role):
        pytest.fail('issuer must not run')
    service = broker.Broker({101: broker.ROLES[0], 102: broker.ROLES[-1]}, forbidden)
    # When / Then
    with pytest.raises(broker.Denied):
        service.token(uid)


def test_cache_is_per_uid_and_refreshes_before_expiry(monkeypatch):
    # Given
    broker = importlib.import_module('broker')
    now = [1000]
    calls = []
    monkeypatch.setattr(broker.time, 'time', lambda: now[0])
    def issuer(role):
        calls.append(role.name)
        return broker.Token('token_' + role.name, now[0] + 120)
    service = broker.Broker({101: broker.ROLES[0], 102: broker.ROLES[1]}, issuer)
    # When
    first = service.token(101)
    second = service.token(101)
    other = service.token(102)
    now[0] = 1060
    service.token(101)
    # Then
    assert first == second
    assert other != first
    assert calls == ['chief-of-staff', 'support', 'chief-of-staff']


@pytest.mark.parametrize('fields', [b'protocol=http\nhost=github.com\npath=yangjeep/leaselab\n', b'protocol=https\nhost=evil.test\npath=yangjeep/leaselab\n', b'protocol=https\nhost=github.com\npath=other/repo\n', b'protocol=https\nhost=github.com\n', b'protocol=https\nprotocol=https\nhost=github.com\npath=yangjeep/leaselab\n', b'\xff'])
def test_helper_rejects_wrong_scope(fields):
    # Given
    helper = importlib.import_module('credential_helper')
    # When / Then
    with pytest.raises((helper.Denied, UnicodeError)):
        helper.credential_request(fields)


def test_helper_accepts_fixed_scope():
    # Given
    helper = importlib.import_module('credential_helper')
    # When / Then
    helper.credential_request(b'protocol=https\nhost=github.com\npath=yangjeep/leaselab.git\n\n')


def response_fixture():
    import datetime
    import policy
    return {'token': 'ghs_TEST_ONLY_12345', 'expires_at': (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=50)).isoformat(), 'permissions': dict(policy.ROLES[0].permissions), 'repositories': [{'full_name': 'yangjeep/leaselab'}]}


@pytest.mark.parametrize('mutation', ['repo', 'permissions', 'expiry', 'token', 'missing', 'list'])
def test_upstream_excess_authority_or_invalid_token_fails_closed(mutation):
    # Given
    import json
    import upstream
    import policy
    data = response_fixture()
    if mutation == 'repo': data['repositories'] = [{'full_name': 'other/repo'}]
    if mutation == 'permissions': data['permissions']['contents'] = 'write'
    if mutation == 'expiry': data['expires_at'] = '2000-01-01T00:00:00Z'
    if mutation == 'token': data['token'] = 'abc\npassword=leak'
    if mutation == 'missing': del data['repositories']
    if mutation == 'list': data = []
    # When / Then
    with pytest.raises(upstream.Denied):
        upstream.parse_token(json.dumps(data).encode(), policy.ROLES[0])


def test_fixed_https_request_has_explicit_permission_subset(monkeypatch):
    # Given: narrow external SaaS transport seam, no network or live credential.
    import json
    import upstream
    import policy
    observed = []
    class Connection:
        def __init__(self, host, **kwargs): observed.append((host, kwargs))
        def request(self, method, path, **kwargs): observed.append((method, path, kwargs))
        def getresponse(self): return self
        status = 201
        def read(self, limit): return json.dumps(response_fixture()).encode()
        def close(self): return None
    monkeypatch.setattr(upstream.http.client, 'HTTPSConnection', Connection)
    # When
    upstream.exchange(policy.ROLES[0], 'FAKE_ASSERTION')
    # Then
    assert observed[0][0] == 'api.github.com'
    assert observed[0][1]['timeout'] == 10
    assert observed[1][:2] == ('POST', '/app/installations/161803163/access_tokens')
    assert json.loads(observed[1][2]['body']) == {'repositories': ['leaselab'], 'permissions': {'metadata': 'read', 'contents': 'read', 'issues': 'write', 'pull_requests': 'write'}}


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='SO_PEERCRED is a Linux-only authorization boundary')
@pytest.mark.parametrize('wire_request,mode', [(b'get\n', 'ok'), (b'get reviewer\n', 'ok'), (b'get\n', 'unknown'), (b'get\n', 'upstream')])
def test_real_unix_peer_boundary(wire_request, mode, capsys):
    # Given: real kernel credentials, not a claimed JSON UID.
    import broker
    uid = os.getuid()
    identities = {uid: broker.ROLES[0]} if mode != 'unknown' else {}
    def issuer(role):
        if mode == 'upstream': raise OSError('SECRET_SENTINEL_DO_NOT_LOG')
        return broker.Token('ghs_TEST_ONLY_12345', 9999999999)
    service = broker.Broker(identities, issuer)
    server, client = socket.socketpair()
    with server, client:
        thread = threading.Thread(target=service.handle, args=(server,))
        thread.start()
        # When
        client.sendall(wire_request)
        client.shutdown(socket.SHUT_WR)
        result = client.recv(1024)
        thread.join(timeout=3)
    # Then
    expected = b'ghs_TEST_ONLY_12345\n' if uid != 0 and mode == 'ok' and wire_request == b'get\n' else b'error\n'
    assert result == expected
    assert not thread.is_alive()
    captured = capsys.readouterr()
    assert 'SECRET_SENTINEL' not in captured.out + captured.err


def test_socket_error_response_never_logs_upstream_body(monkeypatch, capsys):
    # Given
    import broker
    monkeypatch.setattr(broker, 'peer_uid', lambda connection: 101)
    def issuer(role): raise OSError('SECRET_SENTINEL_DO_NOT_LOG')
    service = broker.Broker({101: broker.ROLES[0]}, issuer)
    server, client = socket.socketpair()
    with server, client:
        thread = threading.Thread(target=service.handle, args=(server,))
        thread.start()
        # When
        client.sendall(b'get\n')
        client.shutdown(socket.SHUT_WR)
        result = client.recv(1024)
        thread.join(timeout=3)
    # Then
    assert result == b'error\n'
    captured = capsys.readouterr()
    assert captured.out + captured.err == ''


@pytest.fixture
def short_socket_dir():
    import tempfile
    with tempfile.TemporaryDirectory(prefix='ghb-', dir='/tmp') as directory:
        yield Path(directory)


def test_helper_process_emits_git_protocol_only(short_socket_dir):
    # Given: real helper process and UNIX socket, synthetic noncredential token.
    import subprocess
    path = str(short_socket_dir / 'test.sock')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(path)
        server.listen(1)
        def serve():
            connection, _ = server.accept()
            with connection:
                assert connection.recv(20) == b'get\n'
                connection.sendall(b'ghs_SYNTHETIC.payload-with_hyphens.signature\n')
        thread = threading.Thread(target=serve)
        thread.start()
        program = 'import sys; sys.path.insert(0, sys.argv[1]); import credential_helper as h; h.SOCKET=sys.argv[2]; sys.argv=["helper", "get"]; sys.exit(h.main())'
        # When
        result = subprocess.run([sys.executable, '-I', '-c', program, str(BROKER), path], input=b'protocol=https\nhost=github.com\npath=yangjeep/leaselab.git\n\n', capture_output=True, timeout=5)
        thread.join(timeout=3)
    # Then
    assert result.returncode == 0
    assert result.stderr == b''
    assert result.stdout == b'username=x-access-token\npassword=ghs_SYNTHETIC.payload-with_hyphens.signature\n\n'


def test_jwt_is_verifiable_rs256_and_key_mode_enforced(tmp_path, monkeypatch):
    # Given: ephemeral test key, never a GitHub App key.
    import base64
    import json
    import subprocess
    import upstream
    import policy
    key = tmp_path / 'test.pem'
    public = tmp_path / 'public.pem'
    subprocess.run(['/usr/bin/openssl', 'genrsa', '-out', str(key), '2048'], check=True, capture_output=True)
    key.chmod(0o600)
    subprocess.run(['/usr/bin/openssl', 'rsa', '-in', str(key), '-pubout', '-out', str(public)], check=True, capture_output=True)
    monkeypatch.setattr(policy.Role, 'key_path', property(lambda self: key))
    # When
    jwt = upstream.jwt(policy.ROLES[0])
    header, claims, signature = jwt.split('.')
    signed = tmp_path / 'signature'
    signed.write_bytes(base64.urlsafe_b64decode(signature + '=' * (-len(signature) % 4)))
    result = subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256', '-verify', str(public), '-signature', str(signed)], input=(header + '.' + claims).encode(), capture_output=True)
    # Then
    assert result.returncode == 0
    payload = json.loads(base64.urlsafe_b64decode(claims + '=' * (-len(claims) % 4)))
    assert payload['iss'] == '4948371'
    assert payload['exp'] - payload['iat'] == 600
    key.chmod(0o644)
    with pytest.raises(policy.Denied): upstream.jwt(policy.ROLES[0])


def test_gh_wrapper_passes_only_caller_token_to_system_cli(monkeypatch, capsys):
    # Given
    import gh_client
    captured = []
    monkeypatch.setattr(gh_client, 'obtain', lambda: 'ghs_TEST_ONLY_12345')
    monkeypatch.setattr(sys, 'argv', ['leaselab-gh', 'issue', 'list'])
    monkeypatch.setenv('GITHUB_TOKEN', 'OLD_CREDENTIAL')
    monkeypatch.setenv('GH_ENTERPRISE_TOKEN', 'OLD_CREDENTIAL')
    monkeypatch.setenv('GH_DEBUG', 'api')
    monkeypatch.setattr(os, 'execve', lambda path, args, env: captured.append((path, args, env)))
    # When
    gh_client.main()
    # Then
    path, arguments, environment = captured[0]
    assert path == '/usr/bin/gh'
    assert arguments == ['/usr/bin/gh', 'issue', 'list']
    assert environment['GH_TOKEN'] == 'ghs_TEST_ONLY_12345'
    assert environment['GH_HOST'] == 'github.com'
    assert not {'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GH_DEBUG'} & environment.keys()
    output = capsys.readouterr()
    assert output.out + output.err == ''


def test_accepts_installation_token_with_dot_and_hyphen():
    # Given: GitHub now returns opaque installation tokens with these characters.
    import json
    import upstream
    import policy
    data = response_fixture()
    data['token'] = 'ghs_SYNTHETIC.payload-with_hyphens.signature'
    # When
    token = upstream.parse_token(json.dumps(data).encode(), policy.ROLES[0])
    # Then
    assert token.value == data['token']


def test_source_fetch_identity_is_service_read_only():
    # Given a dedicated service identity, when grants resolve, then no role scope changes.
    import policy
    assert [r.name for r in policy.SERVICE_ROLES] == ['source-fetch']
    role = policy.SERVICE_ROLES[0]
    assert dict(role.permissions) == {'metadata': 'read', 'contents': 'read', 'pull_requests': 'read'}
    assert role.key_path == next(r.key_path for r in policy.ROLES if r.name == 'sre')
    assert role not in policy.ROLES


@pytest.mark.parametrize('length', [512, 520, 2048, 4096])
def test_documented_long_opaque_installation_token_is_accepted(length):
    import json
    import upstream
    import policy
    data=response_fixture()
    data['token']='ghs_'+('a'*(length-6))+'.b'
    assert len(data['token'])==length
    assert upstream.parse_token(json.dumps(data).encode(),policy.ROLES[0]).value==data['token']


@pytest.mark.parametrize('value', ['a'*4097, 'ghs_abc\nInjected', 'ghs_abc\rInjected', 'ghs_abc\x00Injected', 'ghs_abc token'])
def test_opaque_token_bound_and_control_chars_remain_denied(value):
    import json
    import upstream
    import policy
    data=response_fixture();data['token']=value
    with pytest.raises(policy.Denied):
        upstream.parse_token(json.dumps(data).encode(),policy.ROLES[0])


@pytest.mark.parametrize('length', [520, 4096])
def test_helper_receives_long_token_without_truncation(short_socket_dir, monkeypatch, length):
    import credential_helper
    path=str(short_socket_dir/'long.sock')
    value='ghs_'+('a'*(length-6))+'.b'
    monkeypatch.setattr(credential_helper,'SOCKET',path)
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
        listener.bind(path);listener.listen(1)
        def serve():
            connection,_=listener.accept()
            with connection:
                assert connection.recv(20)==b'get\n'
                assert connection.recv(1) == b''
                connection.sendall((value+'\n').encode())
        thread=threading.Thread(target=serve);thread.start()
        try:
            assert credential_helper.obtain()==value
        finally:
            thread.join(timeout=3)


@pytest.mark.parametrize('value', ['a'*4097, 'ghs_abc\nInjected', 'ghs_abc\x00Injected'])
def test_helper_denies_oversize_and_control_character_responses(short_socket_dir, monkeypatch, value):
    import credential_helper
    path=str(short_socket_dir/'malformed.sock')
    monkeypatch.setattr(credential_helper,'SOCKET',path)
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
        listener.bind(path);listener.listen(1)
        def serve():
            connection,_=listener.accept()
            with connection:
                assert connection.recv(20)==b'get\n'
                assert connection.recv(1) == b''
                connection.sendall((value+'\n').encode())
        thread=threading.Thread(target=serve);thread.start()
        try:
            with pytest.raises(credential_helper.Denied):
                credential_helper.obtain()
        finally:
            thread.join(timeout=3)
