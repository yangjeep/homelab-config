"""Bounded full policy reads; no cached bypass list or authorization verdict."""
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from observer_models import Denied, Detail, Observation, Request, Ruleset
from pydantic import TypeAdapter

PREFIX = '/repos/yangjeep/leaselab/rulesets'
MAX_PAGES = 4
MAX_RULESETS = 200


@dataclass(frozen=True, slots=True)
class Response:
    body: bytes
    link: str | None = None


class Reader(Protocol):
    def get(self, path: str) -> Response: ...


def allowed_path(path: str) -> bool:
    return bool(re.fullmatch(
        re.escape(PREFIX) + r'(?:\?includes_parents=true&per_page=100&page=[1-4]|/[1-9][0-9]{0,9}\?includes_parents=true)',
        path)) and (path.count('/') != 5 or int(path.split('/')[-1].split('?')[0]) <= 2147483647)


def inventory(reader: Reader) -> tuple[Ruleset, ...]:
    collected: list[Ruleset] = []
    for page in range(1, MAX_PAGES + 1):
        path = f'{PREFIX}?includes_parents=true&per_page=100&page={page}'
        response = reader.get(path)
        entries = TypeAdapter(tuple[Ruleset, ...]).validate_json(response.body)
        if len(entries) > 100:
            raise Denied('oversized inventory page')
        collected.extend(entries)
        if len(collected) > MAX_RULESETS or len({item.id for item in collected}) != len(collected):
            raise Denied('oversized or duplicate inventory')
        if response.link:
            links = [(match.group(1), match.group(2)) for match in
                     re.finditer(r'<([^<>]+)>; rel="([a-z]+)"', response.link)]
            if not links or ', '.join(f'<{url}>; rel="{rel}"' for url, rel in links) != response.link:
                raise Denied('ambiguous pagination')
            next_links = [url for url, rel in links if rel == 'next']
            if len(next_links) > 1 or any(rel not in {'next', 'prev', 'first', 'last'} for _, rel in links):
                raise Denied('ambiguous pagination')
            if next_links:
                expected = f'https://api.github.com{PREFIX}?includes_parents=true&per_page=100&page={page + 1}'
                if next_links != [expected]:
                    raise Denied('unexpected pagination destination')
                continue
        if len(entries) == 100:
            # A full page without next metadata is ambiguous; never guess completeness.
            raise Denied('truncated inventory')
        return tuple(sorted(collected, key=lambda item: item.id))
    raise Denied('pagination limit')


def details(reader: Reader, entries: tuple[Ruleset, ...]) -> tuple[Detail, ...]:
    result: list[Detail] = []
    total_bytes = 0
    for entry in entries:
        response = reader.get(f'{PREFIX}/{entry.id}?includes_parents=true')
        total_bytes += len(response.body)
        if total_bytes > 2000000:
            raise Denied('policy evidence too large')
        if response.link:
            raise Denied('unexpected detail pagination')
        detail = Detail.model_validate_json(response.body)
        for field in Ruleset.model_fields:
            if getattr(detail, field) != getattr(entry, field):
                raise Denied('detail and inventory differ')
        if detail.source_type == 'Repository' and detail.source != 'yangjeep/leaselab':
            raise Denied('repository source differs')
        result.append(detail)
    return tuple(result)


def observe(reader: Reader, request: Request) -> Observation:
    first = inventory(reader)
    if not first:
        raise Denied('empty policy inventory')
    full = details(reader, first)
    return Observation(nonce=request.nonce, observed_at=datetime.now(timezone.utc).isoformat(), rulesets=full)
