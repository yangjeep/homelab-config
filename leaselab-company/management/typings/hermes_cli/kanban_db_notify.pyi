from collections.abc import Mapping
from sqlite3 import Connection

from pydantic import JsonValue

def add_notify_sub(
    conn: Connection,
    *,
    task_id: str,
    platform: str,
    chat_id: str,
    thread_id: str,
    user_id: str,
    chat_type: str,
    notifier_profile: str,
    delivery_mode: str,
    delivery_metadata: Mapping[str, str],
) -> None: ...
def list_notify_subs(conn: Connection, task_id: str) -> list[dict[str, JsonValue]]: ...
