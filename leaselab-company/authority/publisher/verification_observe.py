"""Fresh fixed-repository PR observation under the dedicated read-only fetch UID."""
import sys
from typing import Literal

from publisher_models import Candidate, Denied, parse_request
from source_fetch import GitHub, client, credential
from source_models import APIRecord


class Repository(APIRecord):
    full_name: Literal['yangjeep/leaselab']


class Ref(APIRecord):
    sha: str
    ref: str
    repo: Repository


class Pull(APIRecord):
    number: int
    head: Ref
    base: Ref


def candidate(raw: bytes, request_raw: bytes) -> Candidate:
    request = parse_request(request_raw)
    value = Pull.model_validate_json(raw)
    if value.number != request.pr or value.base.ref != 'main':
        raise Denied
    return Candidate(pr=request.pr, head=value.head.sha, base=value.base.sha)


def main() -> None:
    if len(sys.argv) != 2:
        raise Denied
    request_raw = sys.argv[1].encode()
    request = parse_request(request_raw)
    with client() as transport:
        api = GitHub(transport, credential())
        print(candidate(api.api('/pulls/' + str(request.pr)), request_raw).model_dump_json())


if __name__ == '__main__':
    try:
        main()
    except (Denied, OSError, ValueError):
        print('OBSERVATION_DENIED', file=sys.stderr)
        raise SystemExit(1) from None
