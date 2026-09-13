from __future__ import annotations

import json
import stat
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from .collector import Collector
from .config import load_runtime_config
from .errors import ApiError, PrivateFileRequiredError
from .google_api import GoogleProcessesApi, create_client, refresh_access_token
from .models import OAuthClientDocument, OAuthTokenFile


def _read_private(path: Path) -> str:
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise PrivateFileRequiredError(path=str(path))
    return path.read_text(encoding="utf-8").strip()


def run() -> int:
    runtime = load_runtime_config()
    client_document = OAuthClientDocument.model_validate_json(
        _read_private(runtime.google_oauth_client_config)
    )
    token_file = OAuthTokenFile.model_validate_json(
        _read_private(runtime.google_oauth_refresh_token_file)
    )
    with create_client() as client:
        access_token = refresh_access_token(
            client,
            token_url=str(client_document.token_uri),
            client_id=client_document.client_id,
            client_secret=client_document.client_secret.get_secret_value(),
            refresh_token=token_file.refresh_token.get_secret_value(),
        )
        api = GoogleProcessesApi(client=client, access_token=access_token)
        result = Collector(
            runtime.collector_config(),
            api,
            now=lambda: datetime.now(tz=UTC),
            sleep=time.sleep,
        ).run()
    sys.stdout.write(
        json.dumps(
            {
                "event": "apps_script.collection",
                "success": result.success,
                "records": result.records,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )
    return 0 if result.success else 1


def main() -> None:
    try:
        raise SystemExit(run())
    except (ApiError, OSError, PrivateFileRequiredError, ValidationError) as error:
        sys.stderr.write(
            json.dumps(
                {
                    "event": "apps_script.collection_error",
                    "error_type": type(error).__name__,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )
        raise SystemExit(1) from error
