"""Root policy: documentation syntax only; this cannot authorize a QA PASS."""
from pathlib import Path
from typing import Final

from publisher_models import Denied
from source_models import Tree, verify_tree

RECIPE: Final = 'docs-text-v1'


def changes(head: Tree, base: Tree) -> tuple[str, ...]:
    verify_tree(head, head.sha)
    verify_tree(base, base.sha)
    before = {item.path: (item.sha, item.mode) for item in base.tree if item.type == 'blob'}
    after = {item.path: (item.sha, item.mode) for item in head.tree if item.type == 'blob'}
    paths = tuple(sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path)))
    if not paths or len(paths) > 100:
        raise Denied
    for path in paths:
        # No agent policy, root instructions, package/workflow or executable documents.
        if (not path.startswith(('docs/', '.agent/WORKLOG/')) or not path.endswith('.md')
                or path not in after or after[path][1] != '100644'):
            raise Denied
    return paths


def check_document(path: Path) -> None:
    raw = path.read_bytes()
    if not raw or len(raw) > 1048576 or b'\0' in raw:
        raise Denied
    text = raw.decode('utf-8')
    if not text.endswith('\n') or any(line.startswith(('<<<<<<< ', '=======', '>>>>>>> ')) for line in text.splitlines()):
        raise Denied
