from __future__ import annotations


class RateLimitedError(Exception):
    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = retry_after_seconds

    def __str__(self) -> str:
        return "Apps Script API rate limit reached"


class ApiError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def __str__(self) -> str:
        return f"Apps Script API returned HTTP {self.status_code}"


class ResponseTooLargeError(Exception):
    def __init__(self, limit_bytes: int) -> None:
        self.limit_bytes = limit_bytes

    def __str__(self) -> str:
        return f"Apps Script API response exceeded {self.limit_bytes} bytes"


class CollectionBoundExceededError(Exception):
    def __init__(self, bound_name: str, limit: int) -> None:
        self.bound_name = bound_name
        self.limit = limit

    def __str__(self) -> str:
        return f"collection exceeded {self.bound_name} limit of {self.limit}"


class PrivateFileRequiredError(Exception):
    def __init__(self, path: str) -> None:
        self.path = path

    def __str__(self) -> str:
        return f"credential file must be a regular file with mode 0600: {self.path}"


class DurationParseError(ValueError):
    def __str__(self) -> str:
        return "duration must be finite, non-negative, and use the protobuf seconds suffix"
