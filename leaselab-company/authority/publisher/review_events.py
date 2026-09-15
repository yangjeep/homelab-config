"""Validate bounded Codex JSONL structure; never treat nested tool stdout as events."""
import json
from typing import Annotated, Literal

from publisher_models import Denied, Record, unique_keys
from pydantic import Field
from review_models import Disposition, ReviewIdentity
from source_models import APIRecord, safe_path


class Item(APIRecord):
    id: str
    type: str
    text: str | None = None
    command: str | None = None
    aggregated_output: str | None = None
    exit_code: int | None = None
    status: str | None = None


class Event(APIRecord):
    type: str
    item: Item | None = None


class Boundary(Record):
    home_canary_denied: Literal[True]
    auth_open_denied: Literal[True]
    broker_absent: Literal[True]
    evidence_absent: Literal[True]
    nonroot: Literal[True]
    secret_env_absent: Literal[True]
    source_config_absent: Literal[True]
    source_skills_absent: Literal[True]
    head_readable: Literal[True]
    base_readable: Literal[True]
    network_denied: Literal[True]
    source_write_denied: Literal[True]


class SemanticRecord(Record):
    family: Literal['codex'] = 'codex'
    role: Literal['reviewer'] = 'reviewer'
    disposition: Disposition
    command_count: Annotated[int, Field(gt=0, le=200)]


def boundary(raw: bytes) -> None:
    json.loads(raw, object_pairs_hook=unique_keys)
    _ = Boundary.model_validate_json(raw)


def disposition(raw: bytes, expected: ReviewIdentity, paths: tuple[str, ...]) -> SemanticRecord:
    if len(raw) > 1048576:
        raise Denied
    started = False
    thread = False
    finished = False
    messages: list[str] = []
    completed: set[str] = set()
    commands = 0
    canary = False
    for line in raw.splitlines():
        # Codex writes bounded warnings to stderr, captured alongside JSON stdout.
        if not line.startswith(b'{'):
            continue
        json.loads(line, object_pairs_hook=unique_keys)
        event = Event.model_validate_json(line)
        if event.type == 'thread.started' and not thread and not started:
            thread = True
        elif event.type == 'turn.started' and thread and not started:
            started = True
        elif event.type == 'turn.completed' and started and not finished:
            finished = True
        elif event.type in ('item.started', 'item.updated') and started and not finished:
            if event.item is None or event.item.id in completed:
                raise Denied
        elif event.type == 'item.completed' and started and not finished and event.item is not None:
            item = event.item
            if item.id in completed:
                raise Denied
            completed.add(item.id)
            if item.type == 'agent_message' and item.text is not None:
                messages.append(item.text)
            elif item.type == 'command_execution':
                commands += 1
                if item.command == "/usr/bin/bash -lc 'python3 /opt/review_boundary.py'":
                    if item.exit_code != 0 or item.status != 'completed' or item.aggregated_output is None:
                        raise Denied
                    boundary(item.aggregated_output.encode())
                    canary = True
            elif item.type not in ('reasoning', 'todo_list'):
                raise Denied
        else:
            raise Denied
    if not started or not finished or not canary or not messages:
        raise Denied
    if len(messages[-1].encode()) > 32768:
        raise Denied
    json.loads(messages[-1], object_pairs_hook=unique_keys)
    value = Disposition.model_validate_json(messages[-1])
    if value.identity != expected:
        raise Denied
    for finding in value.findings:
        _ = safe_path(finding.path)
        if finding.path not in paths:
            raise Denied
    return SemanticRecord(disposition=value, command_count=commands)
