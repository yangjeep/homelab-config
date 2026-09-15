"""Parse the finite CoS operation set and construct fixed GitHub API calls."""
from dataclasses import dataclass
from enum import Enum
import json
from typing import Final, assert_never

from .transport import capture

JSONValue = str | int | float | bool | None | list['JSONValue'] | dict[str, 'JSONValue']
REPO: Final = 'repos/yangjeep/leaselab'
ISSUE_FIELDS: Final = '{number,title:(.title[:200]),state,html_url}'


class Denied(Exception):
    """Input does not belong to the fixed operation schema."""


class Action(str, Enum):
    REPO_READ = 'repo_read'
    ISSUE_LIST = 'issue_list'
    ISSUE_READ = 'issue_read'
    ISSUE_CREATE = 'issue_create'
    ISSUE_UPDATE = 'issue_update'
    PR_COMMENT = 'pr_comment'


@dataclass(frozen=True, slots=True)
class Request:
    action: Action
    number: int = 0
    title: str | None = None
    body: str | None = None
    state: str | None = None
    include_body: bool = False


def parse_request(data: JSONValue) -> Request:
    """Reject surplus fields and parse user text once without interpreting it."""
    if not isinstance(data, dict) or not isinstance(data.get('action'), str):
        raise Denied
    try:
        action = Action(data['action'])
    except ValueError:
        raise Denied from None
    allowed = {
        Action.REPO_READ: set(), Action.ISSUE_LIST: set(),
        Action.ISSUE_READ: {'number', 'include_body'},
        Action.ISSUE_CREATE: {'title', 'body'},
        Action.ISSUE_UPDATE: {'number', 'title', 'body', 'state'},
        Action.PR_COMMENT: {'number', 'body'},
    }[action]
    if set(data) - allowed - {'action'}:
        raise Denied
    number = data.get('number', 0)
    if type(number) is not int or ('number' in allowed and not 1 <= number <= 2147483647):
        raise Denied
    title, body, state = data.get('title'), data.get('body'), data.get('state')
    for text, limit in ((title, 200), (body, 4000)):
        if text is not None and (not isinstance(text, str) or len(text) > limit
                or any(ord(char) < 32 and char not in '\n\t' for char in text)):
            raise Denied
    if title is not None and not title.strip():
        raise Denied
    if state is not None and state not in ('open', 'closed'):
        raise Denied
    include_body = data.get('include_body', False)
    if type(include_body) is not bool:
        raise Denied
    if action == Action.ISSUE_CREATE and title is None:
        raise Denied
    if action == Action.PR_COMMENT and (body is None or not body.strip()):
        raise Denied
    if action == Action.ISSUE_UPDATE and title is None and body is None and state is None:
        raise Denied
    return Request(action, number, title, body, state, include_body)


@dataclass(frozen=True, slots=True)
class APICall:
    method: str
    endpoint: str
    projection: str


def call(api: APICall, payload: bytes = b'') -> str:
    args = ['/usr/local/bin/leaselab-gh', 'api', '--method', api.method,
            '--hostname', 'github.com', api.endpoint, '--jq', api.projection]
    if payload:
        args.extend(['--input', '-'])
    return capture(args, payload)


def execute(request: Request) -> str:
    """Request bodies travel on stdin; remote command and jq are never user-defined."""
    issue = f'{REPO}/issues/{request.number}'
    payload = json.dumps({key: value for key, value in (
        ('title', request.title), ('body', request.body), ('state', request.state)
    ) if value is not None}, ensure_ascii=False).encode('utf-8')
    match request.action:
        case Action.REPO_READ:
            return call(APICall('GET', REPO, '{full_name,private,default_branch,open_issues_count}'))
        case Action.ISSUE_LIST:
            return call(APICall('GET', f'{REPO}/issues?state=open&per_page=20',
                'map(select(has("pull_request") | not) | ' + ISSUE_FIELDS + ')'))
        case Action.ISSUE_READ:
            projection = ISSUE_FIELDS
            if request.include_body:
                projection = '{number,title:(.title[:200]),state,html_url,body:(.body[:4000])}'
            return call(APICall('GET', issue,
                'if has("pull_request") then {error:"not_an_issue"} else ' + projection + ' end'))
        case Action.ISSUE_CREATE:
            return call(APICall('POST', f'{REPO}/issues', ISSUE_FIELDS), payload)
        case Action.ISSUE_UPDATE:
            kind = call(APICall('GET', issue, 'has("pull_request")'))
            if kind.strip() != 'false':
                raise Denied
            return call(APICall('PATCH', issue, ISSUE_FIELDS), payload)
        case Action.PR_COMMENT:
            # The pull endpoint confirms this number belongs to a PR before commenting.
            call(APICall('GET', f'{REPO}/pulls/{request.number}', '{number}'))
            return call(APICall('POST', f'{issue}/comments', '{id,html_url}'), payload)
        case unreachable:
            assert_never(unreachable)
