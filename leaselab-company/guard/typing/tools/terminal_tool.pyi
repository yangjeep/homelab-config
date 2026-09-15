from typing import TypedDict

class NativeTerminalConfig(TypedDict):
    env_type: str
    ssh_host: str
    ssh_user: str
    ssh_port: int
    ssh_key: str

def _get_env_config() -> NativeTerminalConfig: ...
