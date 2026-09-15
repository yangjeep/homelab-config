"""Boundary signatures verified against Hermes 0.21.3 b8bf484; runtime integration tested."""

from collections.abc import Iterable
from sqlite3 import Connection

class Task:
    id: str
    title: str
    body: str | None
    assignee: str | None
    status: str
    result: str | None
    idempotency_key: str | None
    consecutive_failures: int
    last_failure_error: str | None

def create_task(
    conn: Connection,
    *,
    title: str,
    body: str | None = ...,
    assignee: str | None = ...,
    created_by: str | None = ...,
    priority: int = ...,
    idempotency_key: str | None = ...,
    parents: Iterable[str] = ...,
    creator_task_id: str | None = ...,
    initial_status: str = ...,
    max_retries: int | None = ...,
    max_runtime_seconds: int | None = ...,
    workspace_kind: str | None = ...,
    workspace_path: str | None = ...,
    board: str | None = ...,
) -> str: ...
def list_tasks(conn: Connection) -> list[Task]: ...
def get_task(conn: Connection, task_id: str) -> Task | None: ...
def parent_ids(conn: Connection, task_id: str) -> list[str]: ...
def complete_task(
    conn: Connection,
    task_id: str,
    *,
    result: str | None = ...,
    summary: str | None = ...,
) -> bool: ...
def add_comment(conn: Connection, task_id: str, author: str, body: str) -> int: ...

class Comment:
    id: int
    created_at: int
    body: str
    author: str

def list_comments(conn: Connection, task_id: str) -> list[Comment]: ...
def latest_summary(conn: Connection, task_id: str) -> str | None: ...
def latest_summaries(conn: Connection, task_ids: Iterable[str]) -> dict[str, str]: ...

class Run:
    profile: str | None

class Attachment:
    uploaded_by: str | None

def list_runs(
    conn: Connection, task_id: str, *, include_active: bool = ...
) -> list[Run]: ...
def list_attachments(conn: Connection, task_id: str) -> list[Attachment]: ...
