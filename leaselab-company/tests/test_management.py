"""Exercise real native Kanban; set PYTHONPATH to the installed Hermes source."""

from pathlib import Path

import pytest

pytest.importorskip("hermes_cli.kanban_db")
from management.models import IncidentRequest
from management.native import Board
from management.workflow import (
    close_incident,
    start_incident,
    start_weekly,
    summary_context,
)


@pytest.fixture(autouse=True)
def native_notification_transport(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from management import incident_notification as notification
    from management.models import ROLES
    from management.slack_directory import SlackDirectory

    directory = SlackDirectory.model_validate(
        {
            "team_id": "T021CUR5KTP",
            "channels": ["C001", "C002"],
            "incident_channel_id": "C001",
            "roles": {
                role: {"bot_user_id": f"U{index}"}
                for index, role in enumerate(["chief-of-staff", *ROLES])
            },
        }
    )
    monkeypatch.setattr(notification, "load_directory", lambda: directory)
    from management import slack_root
    from management.models import Record

    def read_root(channel: str, timestamp: str) -> slack_root.History:
        board = Board(tmp_path / "kanban.db")
        task = next(
            task
            for task in board.tasks()
            if task.idempotency_key
            and task.idempotency_key.startswith("incident:")
            and task.assignee == "chief-of-staff"
            and task.body
            and '"record_type"' in task.body
        )
        record = Record.model_validate_json(task.body or "")
        return slack_root.History(
            ok=True,
            messages=[
                slack_root.RootMessage(
                    ts=timestamp,
                    user="U0",
                    text=f"{record.identity}\nAuthoritative Kanban: {task.id}",
                )
            ],
        )

    monkeypatch.setattr(
        slack_root, "_test_original_read_root", slack_root.read_root, raising=False
    )
    monkeypatch.setattr(slack_root, "read_root", read_root)

    monkeypatch.setattr(
        notification,
        "send_message_tool",
        lambda args: '{"success":true,"message_id":"1789481511.334529"}',
    )


def test_weekly_retry_is_idempotent_and_dependencies_are_acyclic(
    tmp_path: Path,
) -> None:
    # Given a real isolated Hermes board.
    board = Board(tmp_path / "kanban.db")
    # When the same management cycle is resumed.
    first = start_weekly(board, "2026-W38")
    second = start_weekly(board, "2026-W38")
    # Then one durable cycle exists; no child waits for the unfinished parent.
    assert first == second
    assert len(board.tasks()) == 8
    assert all(board.parents(task_id) == [] for task_id in first.children)
    assert set(board.parents(first.summary)) == set(first.children)
    assert board.task(first.summary).status == "todo"


def test_failure_remains_visible_without_discarding_completed_notes(
    tmp_path: Path,
) -> None:
    # Given independent interviews, with one incomplete role.
    board = Board(tmp_path / "kanban.db")
    cycle = start_weekly(board, "2026-W38")
    for task_id in cycle.children[:-1]:
        board.complete(
            task_id, "Observed synthetic state; no work shipped. Evidence: fixture."
        )
    # When CoS requests current evidence before all interviews complete.
    report = summary_context(board, cycle.parent)
    # Then partial evidence and missing role are explicit, never invented PASS.
    assert len(report.completed) == 5
    assert len(report.incomplete) == 1
    assert report.incomplete[0].status == "ready"


def test_summary_becomes_dispatchable_after_last_real_completion(
    tmp_path: Path,
) -> None:
    board = Board(tmp_path / "kanban.db")
    cycle = start_weekly(board, "2026-W38")
    for task_id in cycle.children:
        board.complete(task_id, "Synthetic verified note")
    assert board.task(cycle.summary).status == "ready"


def test_incident_closure_requires_all_participants_and_verification(
    tmp_path: Path,
) -> None:
    board = Board(tmp_path / "kanban.db")
    request = IncidentRequest(
        incident_id="INC-SYNTHETIC-1",
        severity="P1",
        impact="Synthetic drill; no production impact",
        primary_owner="support",
        participants=["support", "engineer", "qa-security"],
        synthetic=True,
    )
    incident = start_incident(board, request)
    with pytest.raises(ValueError, match="incomplete"):
        close_incident(board, incident.parent, "No changes", "fixture verified")
    for task_id in incident.children:
        board.complete(task_id, "Synthetic verified evidence")
    close_incident(
        board,
        incident.parent,
        "No production change",
        "All synthetic handoffs verified",
    )
    assert board.task(incident.parent).status == "done"


def test_specialist_cannot_invoke_manager_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from management.plugin import company_management

    monkeypatch.setenv("HERMES_PROFILE", "engineer")
    assert "authority required" in company_management({"action": "weekly_start"})


def test_incident_rejects_duplicate_roles_and_missing_owner() -> None:
    with pytest.raises(ValueError, match="must participate"):
        IncidentRequest(
            incident_id="INC-SYNTHETIC-2",
            severity="P1",
            impact="Synthetic",
            primary_owner="sre",
            participants=["support", "engineer"],
        )


def test_incident_checkpoint_survives_new_adapter_instance(tmp_path: Path) -> None:
    from management.models import IncidentUpdate
    from management.records import current_record, update_incident

    path = tmp_path / "kanban.db"
    board = Board(path)
    cycle = start_incident(
        board,
        IncidentRequest(
            incident_id="INC-SYNTHETIC-3",
            severity="P1",
            impact="Synthetic",
            primary_owner="sre",
            participants=["sre", "qa-security"],
            synthetic=True,
        ),
    )
    update_incident(
        board,
        cycle.parent,
        IncidentUpdate(
            current_hypothesis="Fixture fault",
            current_action="Verify fixture",
            artifacts=["fixture://evidence/1"],
        ),
    )
    recovered = current_record(Board(path), cycle.parent)
    assert recovered.current_hypothesis == "Fixture fault"
    assert recovered.artifacts == ["fixture://evidence/1"]


def test_weekly_persists_manager_questions_for_resume(tmp_path: Path) -> None:
    from management.models import ROLES, Questions
    from management.records import current_record

    board = Board(tmp_path / "kanban.db")
    questions = Questions.model_validate(
        {
            role: f"Review actual {role} fixture evidence, then explain its blocker."
            for role in ROLES
        }
    )
    cycle = start_weekly(board, "2026-W38", questions)
    resumed = start_weekly(Board(tmp_path / "kanban.db"), "2026-W38")
    assert resumed == cycle
    assert current_record(board, cycle.parent).question_plan
    assert all(
        "Review actual" in (board.task(child).body or "") for child in cycle.children
    )


def test_weekly_parent_closes_only_after_all_interviews(tmp_path: Path) -> None:
    from management.workflow import close_weekly

    board = Board(tmp_path / "kanban.db")
    cycle = start_weekly(board, "2026-W38")
    with pytest.raises(ValueError, match="incomplete"):
        close_weekly(board, cycle.parent, "Synthetic summary")
    for task_id in cycle.children:
        board.complete(task_id, "Verified synthetic interview evidence")
    close_weekly(
        board, cycle.parent, "Synthetic summary: no production activity claimed"
    )
    assert board.task(cycle.parent).status == "done"


def test_specialist_checkpoint_cannot_forge_incident_state(tmp_path: Path) -> None:
    from contextlib import closing

    from hermes_cli.kanban_db import add_comment
    from hermes_cli.kanban_db_connect import connect
    from management.records import current_record

    path = tmp_path / "kanban.db"
    board = Board(path)
    cycle = start_incident(
        board,
        IncidentRequest(
            incident_id="INC-SYNTHETIC-4",
            severity="P1",
            impact="Synthetic",
            primary_owner="sre",
            participants=["sre", "qa-security"],
            synthetic=True,
        ),
    )
    forged = current_record(board, cycle.parent).model_copy(
        update={"status": "closed", "participants": []}
    )
    with closing(connect(db_path=path, board="leaselab-company")) as conn:
        add_comment(conn, cycle.parent, "support", forged.model_dump_json())
    assert current_record(board, cycle.parent).status == "open"
    board.comment(cycle.parent, forged.model_dump_json())
    assert current_record(board, cycle.parent).participants == ["sre", "qa-security"]


def test_intake_author_and_incident_priority_preserve_operating_identity(
    tmp_path: Path,
) -> None:
    from management.native import Card

    board = Board(tmp_path / "kanban.db")
    start_weekly(board, "2026-W38")
    intake = board.create(
        Card(
            "CoS intake",
            "Synthetic",
            "chief-of-staff",
            "coordination:fixture",
            author="support",
            priority=1,
        )
    )
    assert board.task(intake).created_by == "support"
    incident = start_incident(
        board,
        IncidentRequest(
            incident_id="INC-SYNTHETIC-5",
            severity="P0",
            impact="Synthetic",
            primary_owner="sre",
            participants=["sre", "qa-security"],
            synthetic=True,
        ),
    )
    assert all(
        board.task(task_id).priority == 2
        for task_id in [incident.parent, *incident.children, incident.summary]
    )
    assert board.tasks()[0].priority == 2


def test_public_directory_excludes_unknown_credential_fields() -> None:
    from management.models import ROLES
    from management.slack_directory import SlackDirectory

    directory = SlackDirectory.model_validate(
        {
            "team_id": "T021CUR5KTP",
            "channels": ["C001"],
            "incident_channel_id": "C001",
            "roles": {
                role: {"bot_user_id": f"U{index}", "extra_private_field": "discard-me"}
                for index, role in enumerate(["chief-of-staff", *ROLES])
            },
            "extra_private_field": "discard-me",
        }
    )
    assert "discard-me" not in directory.model_dump_json()
    assert len(directory.roles) == 7


def test_public_directory_rejects_role_writable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import management.slack_directory as directory

    path = tmp_path / "slack-identities.json"
    path.write_text("{}")
    path.chmod(0o666)
    monkeypatch.setattr(directory, "DIRECTORY", path)
    with pytest.raises(ValueError, match="root-owned"):
        directory.load_directory()


@pytest.mark.parametrize("user,allowed", [("U0225R7NP8Q", True), ("U999999", False)])
def test_slack_provenance_comes_from_native_contextvars(
    user: str, allowed: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gateway.session_context import clear_session_vars, set_session_vars
    from management.models import ROLES
    from management.session_context import slack_conversation
    from management.slack_directory import SlackDirectory

    directory = SlackDirectory.model_validate(
        {
            "team_id": "T021CUR5KTP",
            "channels": ["C001"],
            "incident_channel_id": "C001",
            "roles": {
                role: {"bot_user_id": f"U{index}"}
                for index, role in enumerate(["chief-of-staff", *ROLES])
            },
        }
    )
    monkeypatch.setenv("HERMES_SESSION_CHAT_ID", "C999")
    tokens = set_session_vars(
        platform="slack",
        scope_id="T021CUR5KTP",
        user_id=user,
        chat_id="C001",
        message_id="1234567890.123456",
        thread_id="1234567890.000001",
    )
    try:
        if allowed:
            origin = slack_conversation(directory)
            assert origin is not None
            assert origin.source_ref == "slack:T021CUR5KTP:C001:1234567890.123456"
            assert origin.thread_root == "1234567890.000001"
        else:
            with pytest.raises(ValueError, match="not authorized"):
                slack_conversation(directory)
    finally:
        clear_session_vars(tokens)


def test_coordination_schema_accepts_only_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    from collections.abc import Callable, Mapping

    from management import register
    from management.models import CoordinationRequest
    from management.plugin import Value

    class Capture:
        def __init__(self) -> None:
            self.schemas: list[Mapping[str, Value]] = []

        def register_tool(
            self,
            *,
            name: str,
            toolset: str,
            schema: Mapping[str, Value],
            handler: Callable[..., str],
        ) -> None:
            self.schemas.append(schema)

    monkeypatch.setenv("HERMES_PROFILE", "support")
    capture = Capture()
    register(capture)
    assert len(capture.schemas) == 1
    assert "source_ref" not in json.dumps(capture.schemas[0])
    with pytest.raises(ValueError):
        CoordinationRequest.model_validate(
            {"intent": "Synthetic drill", "source_ref": "guessed"}
        )


def test_intent_only_intake_uses_native_origin_and_deduplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from gateway.session_context import clear_session_vars, set_session_vars
    from management import plugin
    from management.models import ROLES
    from management.slack_directory import SlackDirectory

    board = Board(tmp_path / "kanban.db")
    directory = SlackDirectory.model_validate(
        {
            "team_id": "T021CUR5KTP",
            "channels": ["C001"],
            "incident_channel_id": "C001",
            "roles": {
                role: {"bot_user_id": f"U{index}"}
                for index, role in enumerate(["chief-of-staff", *ROLES])
            },
        }
    )
    monkeypatch.setenv("HERMES_PROFILE", "support")
    monkeypatch.setattr(plugin, "Board", lambda: board)
    monkeypatch.setattr(plugin, "load_directory", lambda: directory)
    tokens = set_session_vars(
        platform="slack",
        scope_id="T021CUR5KTP",
        user_id="U0225R7NP8Q",
        chat_id="C001",
        message_id="1789479429.211659",
        thread_id="1789479400.000001",
    )
    try:
        first = plugin.company_request_coordination(
            {"intent": "Synthetic P1 drill; no production access"}
        )
        second = plugin.company_request_coordination(
            {"intent": "Synthetic P1 drill; no production access"}
        )
    finally:
        clear_session_vars(tokens)
    assert first == second
    response = json.loads(first)
    assert response["thread_root"] == "1789479400.000001"
    assert len(board.tasks()) == 1
    task = board.tasks()[0]
    assert task.created_by == "support"
    assert "slack:T021CUR5KTP:C001:1789479429.211659" in (task.body or "")


def test_weekly_result_names_each_assigned_role(tmp_path: Path) -> None:
    from management.models import ROLES

    board = Board(tmp_path / "kanban.db")
    cycle = start_weekly(board, "2026-W38")
    assert set(cycle.assignments) == set(ROLES)
    assert all(
        board.task(task_id).assignee == role
        for role, task_id in cycle.assignments.items()
    )


def test_management_validation_identifies_fields_without_echoing_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from management.models import ROLES
    from management.plugin import company_management

    monkeypatch.setenv("HERMES_PROFILE", "chief-of-staff")
    questions = {role: "Review this role's observed evidence." for role in ROLES}
    questions["support"] = "private-fixture-text" * 200
    result = company_management(
        {"action": "weekly_start", "week": "2026-09-15", "questions": questions}
    )
    assert "string_pattern_mismatch" in result
    assert "questions.support" in result
    assert "string_too_long" in result
    assert "private-fixture-text" not in result


def test_incident_qa_and_review_follow_primary_evidence(tmp_path: Path) -> None:
    board = Board(tmp_path / "kanban.db")
    cycle = start_incident(
        board,
        IncidentRequest(
            incident_id="INC-SYNTHETIC-6",
            severity="P1",
            impact="Synthetic",
            primary_owner="engineer",
            participants=["support", "reviewer", "qa-security", "engineer"],
            synthetic=True,
        ),
    )
    assert board.parents(cycle.assignments["qa-security"]) == [
        cycle.assignments["engineer"]
    ]
    assert board.parents(cycle.assignments["reviewer"]) == [
        cycle.assignments["qa-security"]
    ]
    assert "functional" in (board.task(cycle.assignments["qa-security"]).body or "")
    assert "independent code review" in (
        board.task(cycle.assignments["reviewer"]).body or ""
    )


def test_native_summary_only_completion_is_visible_to_management(
    tmp_path: Path,
) -> None:
    from contextlib import closing

    from hermes_cli.kanban_db import complete_task, get_task
    from hermes_cli.kanban_db_connect import connect

    board = Board(tmp_path / "kanban.db")
    cycle = start_weekly(board, "2026-W38")
    child = cycle.assignments["support"]
    with closing(connect(db_path=board.path, board="leaselab-company")) as conn:
        assert complete_task(
            conn, child, summary="Actual native handoff: verified synthetic evidence."
        )
        task = get_task(conn, child)
        assert task is not None and task.result is None
    assert (
        board.task(child).handoff_summary
        == "Actual native handoff: verified synthetic evidence."
    )
    evidence = summary_context(board, cycle.parent)
    assert (
        evidence.completed[0].handoff_summary
        == "Actual native handoff: verified synthetic evidence."
    )


def test_assignee_note_and_native_completion_metadata_reach_summary(
    tmp_path: Path,
) -> None:
    from contextlib import closing

    from hermes_cli.kanban_db import add_comment, complete_task
    from hermes_cli.kanban_db_connect import connect

    board = Board(tmp_path / "kanban.db")
    cycle = start_weekly(board, "2026-W38")
    child = cycle.assignments["sre"]
    with closing(connect(db_path=board.path, board="leaselab-company")) as conn:
        add_comment(
            conn,
            child,
            "sre",
            "Role: SRE\nCurrent focus: synthetic backup validation\nEvidence: fixture://backup",
        )
        add_comment(
            conn, child, "support", "Unrelated role must not impersonate the SRE note"
        )
        assert complete_task(
            conn,
            child,
            summary="Full findings in native comment and metadata",
            metadata={
                "fixture": "fixture://backup",
                "method": "synthetic",
                "evidence": ["fixture://backup"],
                "verdict": "PASS",
            },
        )
    evidence = summary_context(board, cycle.parent).completed[0]
    assert [note.author for note in evidence.authored_notes] == ["sre"]
    assert "backup validation" in evidence.authored_notes[0].body
    metadata = evidence.completion_evidence[-1].metadata
    assert metadata is not None and metadata["verdict"] == "PASS"
    assert board.comments(child) == []


@pytest.mark.parametrize("action", ["incident_start", "incident_update"])
@pytest.mark.parametrize(
    "target,allowed",
    [
        ("", True),
        ("slack:C001:1789481511.334529", True),
        ("slack:C002:1789481511.334529", False),
        ("slack:T021CUR5KTP:C001:1789481511.334529", False),
        ("slack:C001:bad", False),
    ],
)
def test_incident_thread_destination_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    target: str,
    allowed: bool,
) -> None:
    import json

    from management import plugin
    from management.models import ROLES
    from management.slack_directory import SlackDirectory

    board = Board(tmp_path / "kanban.db")
    directory = SlackDirectory.model_validate(
        {
            "team_id": "T021CUR5KTP",
            "channels": ["C001", "C002"],
            "incident_channel_id": "C001",
            "roles": {
                role: {"bot_user_id": f"U{index}"}
                for index, role in enumerate(["chief-of-staff", *ROLES])
            },
        }
    )
    monkeypatch.setenv("HERMES_PROFILE", "chief-of-staff")
    monkeypatch.setattr(plugin, "Board", lambda: board)
    monkeypatch.setattr(plugin, "load_directory", lambda: directory)
    contract = {
        "incident_id": "TEST-THREAD",
        "severity": "P1",
        "impact": "Synthetic",
        "primary_owner": "engineer",
        "participants": ["engineer", "qa-security"],
        "synthetic": True,
    }
    if action == "incident_start":
        args = {"action": action, "incident": {**contract, "slack_thread": target}}
    else:
        cycle = start_incident(board, IncidentRequest.model_validate(contract))
        args = {
            "action": action,
            "parent_id": cycle.parent,
            "checkpoint": {"slack_thread": target},
        }
    result = json.loads(plugin.company_management(args))
    assert ("error" not in result) == allowed
    if not allowed:
        assert target not in json.dumps(result)
        assert "#incidents" in json.dumps(result)
        assert "provenance" in json.dumps(result)


def test_historical_incident_thread_remains_readable() -> None:
    from management.models import Record

    record = Record(
        record_type="incident",
        identity="TEST-HISTORICAL",
        started_at="2026-09-15",
        slack_thread="slack:T021CUR5KTP:C001:1789481511.334529",
    )
    assert Record.model_validate_json(record.model_dump_json()) == record


def test_incident_start_returns_durable_thread_before_dispatch(tmp_path: Path) -> None:
    board = Board(tmp_path / "kanban.db")
    cycle = start_incident(
        board,
        IncidentRequest(
            incident_id="TEST-NOTIFY",
            severity="P1",
            impact="Fixture only",
            primary_owner="engineer",
            participants=["engineer", "qa-security"],
            synthetic=True,
        ),
    )
    assert cycle.slack_thread == "slack:C001:1789481511.334529"
    assert all(
        cycle.slack_thread in (board.task(child).body or "") for child in cycle.children
    )


@pytest.mark.parametrize("failure", ["returned_error", "crash"])
def test_incident_uncertain_send_blocks_dispatch_and_blind_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    from management import incident_notification as notification
    from management.records import current_record

    board = Board(tmp_path / "kanban.db")
    request = IncidentRequest(
        incident_id="TEST-UNCERTAIN",
        severity="P1",
        impact="Fixture",
        primary_owner="engineer",
        participants=["engineer", "qa-security"],
        synthetic=True,
    )
    calls = []

    def send(args: dict[str, str]) -> str:
        calls.append(args)
        tasks = board.tasks()
        assert len(tasks) == 1
        assert current_record(board, tasks[0].id).notification_state == "pending"
        assert "<@U3>" in args["message"]
        if failure == "crash":
            raise KeyboardInterrupt()
        return '{"error":"timeout"}'

    monkeypatch.setattr(notification, "send_message_tool", send)
    with pytest.raises((ValueError, KeyboardInterrupt)):
        start_incident(board, request)
    assert len(board.tasks()) == 1
    with pytest.raises(ValueError, match="reconciliation"):
        start_incident(board, request)
    assert len(calls) == 1
    recovered = start_incident(
        board,
        request.model_copy(update={"slack_thread": "slack:C001:1789481511.334529"}),
    )
    again = start_incident(Board(board.path), request)
    assert again == recovered
    assert len(calls) == 1
    assert len(board.tasks()) == 4


def test_incident_success_receipt_is_idempotent_and_checkpoint_preserves_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from management import incident_notification as notification
    from management.models import IncidentUpdate
    from management.records import current_record, update_incident

    board = Board(tmp_path / "kanban.db")
    request = IncidentRequest(
        incident_id="TEST-RECEIPT",
        severity="P1",
        impact="Fixture",
        primary_owner="engineer",
        participants=["engineer", "qa-security"],
        synthetic=True,
    )
    calls = []

    def send(args: dict[str, str]) -> str:
        calls.append(args)
        assert len(board.tasks()) == 1
        return '{"success":true,"message_id":"1789481511.334529"}'

    monkeypatch.setattr(notification, "send_message_tool", send)
    first = start_incident(board, request)
    update_incident(
        board, first.parent, IncidentUpdate(current_action="Investigating fixture")
    )
    assert current_record(board, first.parent).slack_thread == first.slack_thread
    assert start_incident(Board(board.path), request) == first
    assert len(calls) == 1
    with pytest.raises(ValueError, match="different canonical"):
        start_incident(
            board,
            request.model_copy(update={"slack_thread": "slack:C001:1789481511.000001"}),
        )


def test_receipt_cannot_be_overwritten_by_checkpoint(tmp_path: Path) -> None:
    from management.models import IncidentUpdate
    from management.records import update_incident

    board = Board(tmp_path / "kanban.db")
    cycle = start_incident(
        board,
        IncidentRequest(
            incident_id="TEST-IMMUTABLE",
            severity="P1",
            impact="Fixture",
            primary_owner="engineer",
            participants=["engineer", "qa-security"],
            synthetic=True,
        ),
    )
    with pytest.raises(ValueError, match="different canonical"):
        update_incident(
            board,
            cycle.parent,
            IncidentUpdate(slack_thread="slack:C001:1789481511.000001"),
        )


def test_concurrent_incident_operation_cannot_send(tmp_path: Path) -> None:
    from management.incident_notification import incident_lock

    board = Board(tmp_path / "kanban.db")
    request = IncidentRequest(
        incident_id="TEST-LOCK",
        severity="P1",
        impact="Fixture",
        primary_owner="engineer",
        participants=["engineer", "qa-security"],
        synthetic=True,
    )
    with (
        incident_lock(board),
        pytest.raises(ValueError, match="Another incident operation"),
    ):
        start_incident(board, request)
    assert board.tasks() == []


@pytest.mark.parametrize(
    "changed",
    [
        {"primary_owner": "qa-security"},
        {"participants": ["engineer", "support"]},
        {"severity": "P0"},
        {"github_links": ["https://github.com/yangjeep/leaselab/issues/999"]},
    ],
)
def test_retry_cannot_change_incident_contract(
    tmp_path: Path, changed: dict[str, str | list[str]]
) -> None:
    board = Board(tmp_path / "kanban.db")
    request = IncidentRequest(
        incident_id="TEST-CONTRACT",
        severity="P1",
        impact="Fixture",
        primary_owner="engineer",
        participants=["engineer", "qa-security"],
        synthetic=True,
    )
    first = start_incident(board, request)
    with pytest.raises(ValueError, match="contract differs"):
        start_incident(board, request.model_copy(update=changed))
    assert start_incident(board, request) == first
    assert len(board.tasks()) == 4


def test_historical_invalid_target_requires_explicit_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from management import incident_notification as notification
    from management.models import Record
    from management.native import Card

    board = Board(tmp_path / "kanban.db")
    request = IncidentRequest(
        incident_id="TEST-HISTORY",
        severity="P1",
        impact="Fixture",
        primary_owner="engineer",
        participants=["engineer", "qa-security"],
        synthetic=True,
    )
    record = Record(
        record_type="incident",
        identity=request.incident_id,
        started_at="2026-09-15",
        severity="P1",
        primary_owner="engineer",
        participants=["engineer", "qa-security"],
        impact="Fixture",
        synthetic=True,
        slack_thread="slack:T021CUR5KTP:C002:1789481511.334529",
    )
    parent = board.create(
        Card(
            "Historical incident",
            record.model_dump_json(),
            "chief-of-staff",
            "incident:TEST-HISTORY",
            status="blocked",
        )
    )
    calls = []
    monkeypatch.setattr(
        notification, "send_message_tool", lambda args: calls.append(args)
    )
    with pytest.raises(ValueError, match="reconciliation"):
        start_incident(board, request)
    recovered = start_incident(
        board,
        request.model_copy(update={"slack_thread": "slack:C001:1789481511.334529"}),
    )
    assert recovered.parent == parent
    assert calls == []


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_ts",
        "reply",
        "other_bot",
        "wrong_incident",
        "wrong_parent",
        "missing",
        "error",
    ],
)
def test_recovery_rejects_unverified_slack_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from management import slack_root

    board = Board(tmp_path / "kanban.db")
    request = IncidentRequest(
        incident_id="TEST-VERIFY",
        severity="P1",
        impact="Fixture",
        primary_owner="engineer",
        participants=["engineer", "qa-security"],
        synthetic=True,
        slack_thread="slack:C001:1789481511.334529",
    )

    def read(channel: str, timestamp: str) -> slack_root.History:
        assert channel == "C001"
        parent = board.tasks()[0].id
        return slack_root.History(
            ok=fault != "error",
            messages=[]
            if fault == "missing"
            else [
                slack_root.RootMessage(
                    ts="1789481511.000001" if fault == "wrong_ts" else timestamp,
                    thread_ts="1789481511.000001" if fault == "reply" else "",
                    user="U3" if fault == "other_bot" else "U0",
                    text=f"{'TEST-OTHER' if fault == 'wrong_incident' else request.incident_id}\nAuthoritative Kanban: {'t_wrong' if fault == 'wrong_parent' else parent}",
                )
            ],
        )

    monkeypatch.setattr(slack_root, "read_root", read)
    with pytest.raises(ValueError, match="root"):
        start_incident(board, request)
    assert len(board.tasks()) == 1


def test_sdk_read_error_is_safe_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    from management import slack_root

    monkeypatch.setattr(
        slack_root, "get_secret", lambda key, default: "synthetic-secret"
    )

    class BrokenClient:
        def __init__(
            self, *, token: str, timeout: int, retry_handlers: list[None]
        ) -> None:
            assert timeout == 15 and retry_handlers == []

        def conversations_history(self, **kwargs: str | bool | int) -> None:
            raise OSError("synthetic-secret must not surface")

    monkeypatch.setattr(slack_root, "WebClient", BrokenClient)
    with pytest.raises(ValueError, match="verification unavailable") as error:
        slack_root._test_original_read_root("C001", "1789481511.334529")
    assert "synthetic-secret" not in str(error.value)


def test_sent_checkpoint_still_requires_external_proof_on_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from management import slack_root

    board = Board(tmp_path / "kanban.db")
    request = IncidentRequest(
        incident_id="TEST-SENT-PROOF",
        severity="P1",
        impact="Fixture",
        primary_owner="engineer",
        participants=["engineer", "qa-security"],
        synthetic=True,
    )
    first = start_incident(board, request)
    monkeypatch.setattr(
        slack_root,
        "read_root",
        lambda channel, timestamp: slack_root.History(ok=True, messages=[]),
    )
    with pytest.raises(ValueError, match="root missing"):
        start_incident(board, request)
    assert len(board.tasks()) == 4
    assert board.task(first.parent).status == "blocked"
