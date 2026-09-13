from __future__ import annotations

from datetime import UTC, datetime

import httpx2
import pytest

from apps_script_observer.errors import ResponseTooLargeError
from apps_script_observer.google_api import GoogleProcessesApi


def test_processes_api_parses_bounded_page() -> None:
    # Given a wire-level Apps Script API response.
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.params["scriptId"] == "script-id"
        assert request.url.params["scriptProcessFilter.startTime"] == "2026-09-13T00:00:00Z"
        return httpx2.Response(
            200,
            json={
                "processes": [
                    {
                        "functionName": "runCleanup",
                        "processType": "TIME_DRIVEN",
                        "processStatus": "COMPLETED",
                        "startTime": "2026-09-13T01:00:00Z",
                        "duration": "1.25s",
                    }
                ],
                "nextPageToken": "next",
            },
        )

    transport = httpx2.MockTransport(handler)
    with httpx2.Client(transport=transport) as client:
        api = GoogleProcessesApi(client=client, access_token="access-token")

        # When a page is fetched through the HTTP adapter.
        page = api.fetch_page(
            script_id="script-id",
            started_after=datetime(2026, 9, 13, tzinfo=UTC),
            page_token=None,
            page_size=50,
        )

    # Then typed metadata and pagination are returned without content fields.
    assert len(page.processes) == 1
    assert page.processes[0].function_name == "runCleanup"
    assert page.next_page_token == "next"


def test_processes_api_rejects_oversized_response() -> None:
    # Given an Apps Script response larger than the two MiB boundary.
    transport = httpx2.MockTransport(
        lambda _request: httpx2.Response(200, content=b"x" * (2 * 1024 * 1024 + 1))
    )

    # When the HTTP adapter reads the response.
    with (
        httpx2.Client(transport=transport) as client,
        pytest.raises(ResponseTooLargeError) as raised,
    ):
        GoogleProcessesApi(client=client, access_token="access-token").fetch_page(
            script_id="script-id",
            started_after=datetime(2026, 9, 13, tzinfo=UTC),
            page_token=None,
            page_size=50,
        )

    # Then collection stops at the configured body bound.
    assert raised.type is ResponseTooLargeError
