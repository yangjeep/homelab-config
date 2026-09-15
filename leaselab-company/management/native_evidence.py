"""Read native handoff surfaces without changing the checkpoint authority path."""

from sqlite3 import Connection

from hermes_cli import kanban_db as native

from .models import ArtifactEvidence, AuthoredNote, CompletionEvidence, TaskView


def with_native_evidence(conn: Connection, task: TaskView) -> TaskView:
    """Preserve authorship and run provenance; attachment contents are never read."""
    authors = {"chief-of-staff"}
    if task.assignee:
        authors.add(task.assignee)
    notes = [
        AuthoredNote.model_validate(note)
        for note in native.list_comments(conn, task.id)
        if note.author in authors
    ]
    completions = [
        CompletionEvidence.model_validate(run)
        for run in native.list_runs(conn, task.id, include_active=False)
        if run.profile in authors
    ][-3:]
    artifacts = [
        ArtifactEvidence.model_validate(artifact)
        for artifact in native.list_attachments(conn, task.id)
        if artifact.uploaded_by in authors
    ]
    return task.model_copy(
        update={
            "authored_notes": notes,
            "completion_evidence": completions,
            "artifacts": artifacts,
        }
    )
