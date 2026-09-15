from pathlib import Path
from sqlite3 import Connection

def connect(db_path: Path | None = ..., *, board: str | None = ...) -> Connection: ...
