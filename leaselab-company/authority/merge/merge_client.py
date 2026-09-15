#!/usr/bin/python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.10,<3"]
# ///
# How to run: printf '{"pr":123,"head":"<40 hex>"}' | leaselab-merge-pr
"""Reviewer socket client; input never controls token, repo, method, or endpoint."""
import socket
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_models import MergeResult, Request


def main() -> int:
    if sys.argv[1:] == ['--help']:
        print('Read JSON {"pr":positive_integer,"head":"40 lowercase hex"} from stdin. Reviewer UID only.')
        return 0
    if len(sys.argv) != 1:
        print('invalid arguments', file=sys.stderr)
        return 2
    try:
        request = Request.model_validate_json(sys.stdin.buffer.read(257))
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(125)
            connection.connect('/run/leaselab-merge/merge.sock')
            connection.sendall(request.model_dump_json().encode())
            connection.shutdown(socket.SHUT_WR)
            response = bytearray()
            while len(response) <= 4096:
                part = connection.recv(4097 - len(response))
                if not part:
                    break
                response.extend(part)
        result = MergeResult.model_validate_json(response)
        if not result.merged:
            return 1
        print(result.model_dump_json())
        return 0
    except (ValidationError, OSError):
        print('Merge denied or outcome indeterminate. Inspect PR before retry.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
