"""Small adapter over installed Hermes; no private tables or second state store."""

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from hermes_cli import kanban_db as native
from hermes_cli.kanban_db_connect import connect

from .models import TaskView
from .native_evidence import with_native_evidence

BOARD: Final = "leaselab-company"


@dataclass(frozen=True, slots=True)
class Card:
    title: str
    body: str
    assignee: str
    key: str
    prerequisites: tuple[str, ...] = ()
    status: str = "running"
    creator: str | None = None
    author: str = "chief-of-staff"
    priority: int = 0


@dataclass(frozen=True, slots=True)
class Board:
    path: Path | None = None

    def create(self, card: Card) -> str:
        with closing(connect(db_path=self.path, board=BOARD)) as conn:
            return native.create_task(
                conn,
                title=card.title,
                body=card.body,
                assignee=card.assignee,
                created_by=card.author,
                priority=card.priority,
                idempotency_key=card.key,
                parents=card.prerequisites,
                creator_task_id=card.creator,
                initial_status=card.status,
                max_retries=3,
                max_runtime_seconds=900,
                workspace_kind="dir",
                workspace_path=f"/var/lib/leaselab-company/workspaces/{card.assignee}",
                board=BOARD,
            )

    def tasks(self) -> list[TaskView]:
        with closing(connect(db_path=self.path, board=BOARD)) as conn:
            tasks = native.list_tasks(conn)
            summaries = native.latest_summaries(conn, [task.id for task in tasks])
            return [
                with_native_evidence(
                    conn,
                    TaskView.model_validate(task).model_copy(
                        update={"handoff_summary": summaries.get(task.id)}
                    ),
                )
                for task in tasks
            ]

    def task(self, task_id: str) -> TaskView:
        with closing(connect(db_path=self.path, board=BOARD)) as conn:
            return with_native_evidence(
                conn,
                TaskView.model_validate(native.get_task(conn, task_id)).model_copy(
                    update={"handoff_summary": native.latest_summary(conn, task_id)}
                ),
            )

    def parents(self, task_id: str) -> list[str]:
        with closing(connect(db_path=self.path, board=BOARD)) as conn:
            return native.parent_ids(conn, task_id)

    def complete(self, task_id: str, result: str) -> bool:
        with closing(connect(db_path=self.path, board=BOARD)) as conn:
            return native.complete_task(conn, task_id, result=result, summary=result)

    def comment(self, task_id: str, body: str) -> None:
        with closing(connect(db_path=self.path, board=BOARD)) as conn:
            native.add_comment(conn, task_id, "chief-of-staff", body)

    def comments(self, task_id: str) -> list[str]:
        with closing(connect(db_path=self.path, board=BOARD)) as conn:
            return [
                comment.body
                for comment in native.list_comments(conn, task_id)
                if comment.author == "chief-of-staff"
            ]
