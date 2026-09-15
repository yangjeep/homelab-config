from pydantic import JsonValue

class Response:
    data: JsonValue

class WebClient:
    def __init__(
        self, *, token: str, timeout: int, retry_handlers: list[None]
    ) -> None: ...
    def conversations_history(
        self, *, channel: str, oldest: str, latest: str, inclusive: bool, limit: int
    ) -> Response: ...
