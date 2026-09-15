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
