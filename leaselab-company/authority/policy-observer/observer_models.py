"""Typed policy observer boundary; unknown GitHub semantic fields are preserved."""
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

Positive = Annotated[int, Field(gt=0, le=2147483647)]
Nonce = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')]
Text = Annotated[str, StringConstraints(min_length=1, max_length=2048)]


class Denied(Exception):
    """Policy evidence could not be established completely."""


class Strict(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, frozen=True, extra='forbid')


class Request(Strict):
    nonce: Nonce


class Config(Strict):
    enabled: bool = False
    app_id: Positive | None = None
    installation_id: Positive | None = None


class Ruleset(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, frozen=True, extra='allow')
    id: Positive
    name: Text
    source_type: Literal['Repository', 'Organization', 'Enterprise']
    source: Text
    enforcement: Literal['active', 'disabled', 'evaluate']
    created_at: Text
    updated_at: Text


class Detail(Ruleset):
    target: Literal['branch', 'tag', 'push']
    bypass_actors: tuple[dict[str, JsonValue], ...]
    conditions: dict[str, JsonValue]
    rules: tuple[dict[str, JsonValue], ...]


class Observation(Strict):
    nonce: Nonce
    repository: Literal['yangjeep/leaselab'] = 'yangjeep/leaselab'
    observed_at: Text
    rulesets: tuple[Detail, ...]
