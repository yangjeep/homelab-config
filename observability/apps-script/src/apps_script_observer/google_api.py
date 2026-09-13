from __future__ import annotations

import socket
from datetime import UTC, datetime
from typing import Final

import httpx2
from pydantic import ValidationError

from .collector import Page
from .errors import ApiError, RateLimitedError, ResponseTooLargeError
from .models import OAuthTokenResponse, ProcessesResponse

_API_URL: Final = "https://script.googleapis.com/v1/processes:listScriptProcesses"
_MAX_BODY_BYTES: Final = 2 * 1024 * 1024
_HTTP_ERROR: Final = 400
_HTTP_RATE_LIMITED: Final = 429


class GoogleProcessesApi:
    def __init__(self, *, client: httpx2.Client, access_token: str) -> None:
        self._client = client
        self._access_token = access_token

    def fetch_page(
        self,
        *,
        script_id: str,
        started_after: datetime,
        page_token: str | None,
        page_size: int,
    ) -> Page:
        params = {
            "scriptId": script_id,
            "pageSize": str(page_size),
            "scriptProcessFilter.startTime": _google_time(started_after),
        }
        if page_token is not None:
            params["pageToken"] = page_token
        try:
            with self._client.stream(
                "GET",
                _API_URL,
                params=params,
                headers={"Authorization": f"Bearer {self._access_token}"},
            ) as response:
                if response.status_code == _HTTP_RATE_LIMITED:
                    raise RateLimitedError(retry_after_seconds=_retry_after(response))
                if response.status_code >= _HTTP_ERROR:
                    raise ApiError(status_code=response.status_code)
                body = _bounded_body(response)
        except httpx2.HTTPError as error:
            raise ApiError(status_code=503) from error
        try:
            parsed = ProcessesResponse.model_validate_json(body)
        except ValidationError as error:
            raise ApiError(status_code=502) from error
        return Page(processes=parsed.processes, next_page_token=parsed.next_page_token)


def create_client() -> httpx2.Client:
    limits = httpx2.Limits(
        max_connections=50,
        max_keepalive_connections=20,
        keepalive_expiry=5.0,
    )
    timeout = httpx2.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
    transport = httpx2.HTTPTransport(
        http2=True,
        retries=2,
        limits=limits,
        socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
    )
    return httpx2.Client(transport=transport, timeout=timeout, follow_redirects=False)


def refresh_access_token(
    client: httpx2.Client,
    *,
    token_url: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> str:
    try:
        with client.stream(
            "POST",
            token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        ) as response:
            if response.status_code >= _HTTP_ERROR:
                raise ApiError(status_code=response.status_code)
            body = _bounded_body(response)
    except httpx2.HTTPError as error:
        raise ApiError(status_code=503) from error
    try:
        parsed = OAuthTokenResponse.model_validate_json(body)
    except ValidationError as error:
        raise ApiError(status_code=502) from error
    return parsed.access_token.get_secret_value()


def _google_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _retry_after(response: httpx2.Response) -> float:
    raw = response.headers.get("Retry-After", "1")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def _bounded_body(response: httpx2.Response) -> bytes:
    body = bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) > _MAX_BODY_BYTES:
            raise ResponseTooLargeError(limit_bytes=_MAX_BODY_BYTES)
    return bytes(body)
