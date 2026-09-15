"""Native tool schemas expose only role-appropriate operating inputs."""

import os
from collections.abc import Callable, Mapping
from typing import Protocol, TypeVar

from .models import ROLES, THREAD_HINT, THREAD_PATTERN
from .plugin import Value, company_management, company_request_coordination

Registration_co = TypeVar("Registration_co", covariant=True)


class Context(Protocol[Registration_co]):
    def register_tool(
        self,
        *,
        name: str,
        toolset: str,
        schema: Mapping[str, Value],
        handler: Callable[..., str],
    ) -> Registration_co: ...


def register(ctx: Context[Registration_co]) -> None:
    """Register only the tool appropriate for the trusted process profile."""
    role = os.environ.get("HERMES_PROFILE", "")
    if role == "chief-of-staff":
        ctx.register_tool(
            name="company_management",
            toolset="leaselab-management",
            handler=company_management,
            schema={
                "name": "company_management",
                "description": "Durable CoS weekly interviews, evidence summary and incident coordination. Never bypass release gates.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["action"],
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "weekly_start",
                                "team_status",
                                "summary_context",
                                "incident_start",
                                "incident_close",
                                "incident_update",
                                "weekly_close",
                            ],
                        },
                        "questions": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": list(ROLES),
                            "properties": {
                                role: {
                                    "type": "string",
                                    "minLength": 10,
                                    "maxLength": 2000,
                                }
                                for role in ROLES
                            },
                        },
                        "week": {
                            "type": "string",
                            "pattern": r"^(?:\d{4}-W\d{2})?$",
                            "description": "ISO week YYYY-Www, for example 2026-W38. Omit for current Toronto week. Do not supply a calendar date.",
                        },
                        "parent_id": {"type": "string"},
                        "incident": {
                            "type": "object",
                            "required": [
                                "incident_id",
                                "severity",
                                "impact",
                                "primary_owner",
                                "participants",
                            ],
                            "properties": {
                                "incident_id": {"type": "string"},
                                "severity": {"type": "string", "enum": ["P0", "P1"]},
                                "impact": {"type": "string"},
                                "primary_owner": {
                                    "type": "string",
                                    "enum": list(ROLES),
                                },
                                "participants": {
                                    "type": "array",
                                    "items": {"type": "string", "enum": list(ROLES)},
                                },
                                "github_links": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "slack_thread": {
                                    "type": "string",
                                    "pattern": THREAD_PATTERN,
                                    "description": THREAD_HINT,
                                },
                                "synthetic": {"type": "boolean"},
                            },
                        },
                        "checkpoint": {
                            "type": "object",
                            "properties": {
                                "current_hypothesis": {"type": "string"},
                                "current_action": {"type": "string"},
                                "blockers": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "artifacts": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "github_links": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "slack_thread": {
                                    "type": "string",
                                    "pattern": THREAD_PATTERN,
                                    "description": THREAD_HINT,
                                },
                                "mitigation": {"type": "string"},
                                "follow_up": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                        "summary": {"type": "string", "maxLength": 6000},
                        "resolution": {"type": "string"},
                        "verification": {"type": "string"},
                    },
                },
            },
        )
    if role in ROLES:
        ctx.register_tool(
            name="company_request_coordination",
            toolset="leaselab-management",
            handler=company_request_coordination,
            schema={
                "name": "company_request_coordination",
                "description": "Submit durable intent to CoS for multi-role, incident, unclear ownership, or engineering contract coordination. Supply only intent. The server derives the current message and reply thread automatically; do not invent routing identifiers.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["intent"],
                    "properties": {
                        "intent": {"type": "string", "maxLength": 5000},
                    },
                },
            },
        )
