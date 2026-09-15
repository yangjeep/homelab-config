"""Fixed-operation CoS GitHub boundary tests; no real credentials or mutations."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parents[1] / 'github-tools'
SPEC = importlib.util.spec_from_file_location('company_github_plugin', ROOT / '__init__.py')
assert SPEC and SPEC.loader
plugin = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = plugin
SPEC.loader.exec_module(plugin)


@pytest.mark.parametrize('role', ['', 'engineer', 'reviewer', 'support', 'chief-of-staff;id'])
def test_non_cos_role_is_denied_before_transport(monkeypatch, role):
    # Given
    monkeypatch.setenv('HERMES_PROFILE', role)
    # When
    result = plugin.company_github({'action': 'repo_read'})
    # Then
    assert result == '{"error":"role_denied"}'


@pytest.mark.parametrize('args', [
    {'action': 'merge', 'number': 1}, {'action': 'workflow_dispatch'},
    {'action': 'repo_read', 'repository': 'evil/repo'},
    {'action': 'repo_read', 'command': 'id'},
    {'action': 'issue_read', 'number': '../pulls/1/merge'},
    {'action': 'issue_read', 'number': True},
    {'action': 'issue_read', 'number': 0},
    {'action': 'issue_read', 'number': 1, 'include_body': 'yes'},
    {'action': 'issue_create', 'title': ''},
    {'action': 'issue_create', 'title': 'x' * 201},
    {'action': 'pr_comment', 'number': 1, 'body': '\x00'},
    {'action': 'issue_update', 'number': 1},
    {'action': 'issue_update', 'number': 1, 'state': 'merged'},
    {'action': 'repo_read', 'host': 'attacker.example'},
    [], {'action': {}},
])
def test_invalid_action_or_injection_is_denied_before_transport(args, monkeypatch):
    # Given
    monkeypatch.setenv('HERMES_PROFILE', 'chief-of-staff')
    def forbidden(*args): pytest.fail('transport must not execute')
    monkeypatch.setattr(plugin, 'capture', forbidden)
    # When
    result = plugin.company_github(args)
    # Then
    assert result == '{"error":"invalid_request"}'


def test_shell_metacharacters_remain_json_stdin_only(monkeypatch):
    # Given
    import json
    from company_github_plugin import operations
    calls = []
    text = '$(touch /tmp/should-not-exist); `id` " quote\nsecond line'
    def capture(arguments, payload):
        calls.append((arguments, payload))
        return '{"number":1,"title":"synthetic","state":"open","html_url":"https://github.com/yangjeep/leaselab/issues/1"}'
    monkeypatch.setattr(operations, 'capture', capture)
    request = operations.parse_request({'action': 'issue_create', 'title': 'synthetic', 'body': text})
    # When
    operations.execute(request)
    # Then
    arguments, payload = calls[0]
    assert arguments[:7] == ['/usr/local/bin/leaselab-gh', 'api', '--method', 'POST', '--hostname', 'github.com', 'repos/yangjeep/leaselab/issues']
    assert arguments[-2:] == ['--input', '-']
    assert text not in ' '.join(arguments)
    assert json.loads(payload) == {'title': 'synthetic', 'body': text}


@pytest.mark.parametrize('include_body', [False, True])
def test_issue_body_projection_requires_explicit_request(include_body, monkeypatch):
    # Given
    from company_github_plugin import operations
    calls = []
    monkeypatch.setattr(operations, 'capture', lambda args, payload: calls.append(args) or '{}')
    data = {'action': 'issue_read', 'number': 7, 'include_body': include_body}
    # When
    operations.execute(operations.parse_request(data))
    # Then: these are machine-consumed jq selectors, not prose assertions.
    assert ('body:' in calls[0][-1]) is include_body
    assert calls[0][6] == 'repos/yangjeep/leaselab/issues/7'


def test_issue_update_cannot_change_a_pull_request(monkeypatch):
    # Given
    from company_github_plugin import operations
    calls = []
    monkeypatch.setattr(operations, 'capture', lambda args, payload: calls.append(args) or 'true')
    data = {'action': 'issue_update', 'number': 7, 'title': 'synthetic'}
    # When / Then
    with pytest.raises(operations.Denied): operations.execute(operations.parse_request(data))
    assert len(calls) == 1 and calls[0][3] == 'GET'


def test_pr_comment_confirms_pr_then_posts_only_comment(monkeypatch):
    # Given
    from company_github_plugin import operations
    calls = []
    monkeypatch.setattr(operations, 'capture', lambda args, payload: calls.append((args, payload)) or '{}')
    # When
    operations.execute(operations.parse_request({'action': 'pr_comment', 'number': 8, 'body': 'synthetic'}))
    # Then
    assert [(args[3], args[6]) for args, _ in calls] == [('GET', 'repos/yangjeep/leaselab/pulls/8'), ('POST', 'repos/yangjeep/leaselab/issues/8/comments')]


def test_ssh_command_is_fixed_and_user_input_is_stdin(monkeypatch):
    # Given
    import json
    monkeypatch.setenv('HERMES_PROFILE', 'chief-of-staff')
    observed = []
    monkeypatch.setattr(plugin, 'capture', lambda args, payload: observed.append((args, payload)) or '{"full_name":"yangjeep/leaselab"}')
    # When
    result = json.loads(plugin.company_github({'action': 'repo_read'}))
    # Then
    args, payload = observed[0]
    assert args[-2:] == ['leaselab-chief-of-staff@127.0.0.1', 'leaselab-company-github-v1']
    assert args[args.index('-i') + 1] == '/etc/leaselab-company/ssh/chief-of-staff'
    assert 'StrictHostKeyChecking=yes' in args
    assert json.loads(payload) == {'action': 'repo_read'}
    assert result['result']['full_name'] == 'yangjeep/leaselab'


def test_transport_bounds_output_from_real_process():
    # Given
    from company_github_plugin.transport import capture, TransportFailure
    # When / Then
    with pytest.raises(TransportFailure):
        capture([sys.executable, '-I', '-c', 'import sys; sys.stdout.write("x"*40000)'], b'')


def test_transport_discards_stderr_from_real_process():
    # Given
    from company_github_plugin.transport import capture
    # When
    result = capture([sys.executable, '-I', '-c', 'import sys; sys.stderr.write("SECRET_SENTINEL"); print("{}")'], b'')
    # Then
    assert result.strip() == '{}'


def test_failed_transport_returns_no_exception_content(monkeypatch):
    # Given
    monkeypatch.setenv('HERMES_PROFILE', 'chief-of-staff')
    def failed(*args): raise OSError('SECRET_SENTINEL')
    monkeypatch.setattr(plugin, 'capture', failed)
    # When
    result = plugin.company_github({'action': 'repo_read'})
    # Then
    assert result == '{"error":"operation_failed_or_outcome_unknown"}'


def test_forced_runner_rejects_wrong_marker_before_execution(monkeypatch):
    # Given
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location('company_runner_test', ROOT / 'runner.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(runner.os, 'getuid', lambda: 1001)
    monkeypatch.setattr(runner.pwd, 'getpwnam', lambda name: SimpleNamespace(pw_uid=1001))
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'id; arbitrary shell')
    monkeypatch.setattr(runner.signal, 'signal', lambda *args: None)
    monkeypatch.setattr(runner.signal, 'alarm', lambda *args: None)
    monkeypatch.setattr(runner, 'execute', lambda request: pytest.fail('execution forbidden'))
    # When
    result = runner.main()
    # Then
    assert result == 1


def test_plugin_registers_only_company_tool():
    # Given
    captured = []
    class Context:
        def register_tool(self, **values): captured.append(values)
    # When
    plugin.register(Context())
    # Then
    assert len(captured) == 1
    assert captured[0]['name'] == 'company_github'
    assert captured[0]['toolset'] == 'leaselab-company-github'
    assert captured[0]['handler'] is plugin.company_github


def test_oversized_stdin_is_denied_before_spawning(monkeypatch):
    # Given
    from company_github_plugin import transport
    monkeypatch.setattr(transport.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('spawn forbidden'))
    # When / Then
    with pytest.raises(transport.TransportFailure): transport.capture(['/usr/bin/ssh'], b'x' * 8193)


def test_transport_deadline_kills_process_and_returns_typed_failure(monkeypatch):
    # Given: advance the deadline without sleeping or contacting SSH.
    from company_github_plugin import transport
    moments = iter([0, 41])
    monkeypatch.setattr(transport.time, 'monotonic', lambda: next(moments))
    # When / Then
    with pytest.raises(transport.TransportFailure):
        transport.capture([sys.executable, '-I', '-c', 'import time; time.sleep(60)'], b'')


def test_plugin_timeout_has_no_traceback_or_exception_text(monkeypatch, capsys):
    # Given
    monkeypatch.setenv('HERMES_PROFILE', 'chief-of-staff')
    def timeout(*args): raise TimeoutError('SECRET_SENTINEL')
    monkeypatch.setattr(plugin, 'capture', timeout)
    # When
    result = plugin.company_github({'action': 'repo_read'})
    # Then
    assert result == '{"error":"operation_failed_or_outcome_unknown"}'
    output = capsys.readouterr()
    assert output.out + output.err == ''


def test_forced_runner_timeout_has_no_traceback(monkeypatch, capsys):
    # Given
    import io
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location('company_runner_timeout', ROOT / 'runner.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(runner.os, 'getuid', lambda: 1001)
    monkeypatch.setattr(runner.pwd, 'getpwnam', lambda name: SimpleNamespace(pw_uid=1001))
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', runner.MARKER)
    monkeypatch.setattr(runner.signal, 'signal', lambda *args: None)
    monkeypatch.setattr(runner.signal, 'alarm', lambda *args: None)
    monkeypatch.setattr(runner.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'{"action":"repo_read"}')))
    def timeout(request): raise TimeoutError('SECRET_SENTINEL')
    monkeypatch.setattr(runner, 'execute', timeout)
    # When
    result = runner.main()
    # Then
    assert result == 1
    output = capsys.readouterr()
    assert output.out + output.err == ''
