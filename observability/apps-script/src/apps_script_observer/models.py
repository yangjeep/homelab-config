from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, NewType

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, field_validator

from .errors import DurationParseError

ScriptAlias = NewType("ScriptAlias", str)
ExecutionKey = NewType("ExecutionKey", str)


class Process(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    function_name: str = Field(alias="functionName", min_length=1, max_length=256)
    process_type: str = Field(alias="processType", min_length=1, max_length=64)
    process_status: str = Field(alias="processStatus", min_length=1, max_length=64)
    start_time: datetime = Field(alias="startTime")
    duration_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = Field(
        default=None, alias="duration"
    )

    @field_validator("duration_seconds", mode="before")
    @classmethod
    def parse_duration(cls, raw: str | None) -> float | None:
        if raw is None:
            return None
        if not raw.endswith("s"):
            raise DurationParseError
        try:
            value = float(raw[:-1])
        except ValueError as error:
            raise DurationParseError from error
        if value < 0 or not math.isfinite(value):
            raise DurationParseError
        return value


class ProcessesResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    processes: tuple[Process, ...] = ()
    next_page_token: str | None = Field(default=None, alias="nextPageToken", max_length=4096)


class OAuthClientDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    client_id: str = Field(min_length=1)
    client_secret: SecretStr
    token_uri: HttpUrl


class OAuthTokenResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    access_token: SecretStr


class OAuthTokenFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    refresh_token: SecretStr


class StoredExecution(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    duration_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None
    terminal_counted: bool


class CompletedExecution(BaseModel):
    model_config = ConfigDict(frozen=True)

    script_alias: str
    start_time: datetime
    duration_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None
