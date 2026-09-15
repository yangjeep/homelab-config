"""Fixed executor identities and root-owned launch parameters."""
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from publisher_models import Denied, Role

ROOT: Final = Path('/var/lib/leaselab-publisher/executor')
CODE: Final = Path('/usr/local/libexec/leaselab-company/publisher')
CODEX: Final = Path('/usr/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex')
Lane = Literal['codex-canary', 'test-canary', 'auth-smoke']


@dataclass(frozen=True, slots=True)
class Executor:
    role: Role
    user: str

    @property
    def root(self) -> Path:
        return ROOT / self.role

    @property
    def home(self) -> Path:
        return self.root / 'home'


def executor(role: str) -> Executor:
    if role == 'qa-security':
        return Executor('qa-security', 'leaselab-qa-exec')
    if role == 'reviewer':
        return Executor('reviewer', 'leaselab-review-exec')
    raise Denied
