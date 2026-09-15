"""Idempotent provisioning in the existing CoS Hermes cron provider only.

Run with the installed Hermes interpreter: python -m management.scheduler.
"""

import json
import os
from typing import Final

from cron.jobs import create_job, list_jobs, resume_job, update_job
from hermes_time import get_timezone_name

from .models import ManagementError

JOBS: Final = (
    (
        "weekly-cos-management",
        "0 9 * * 1",
        (
            "First call company_management action=team_status. Read current work, previous 1:1 notes, linked GitHub/QA/deployment evidence, then select meaningful questions for each role. Call company_management action=weekly_start with questions mapping all six roles (engineer, reviewer, qa-security, sre, support, growth) to your evidence-grounded questions. It idempotently starts this Toronto ISO-week cycle. "
            "Inspect the returned parent and previous incomplete cycles. CoS coordinates; six specialists interview "
            "independently, and native dependencies release the synthesis card on completion. Do not create duplicate "
            "cards. Native retries are bounded. Do not mistake missing evidence for no activity."
        ),
    ),
    (
        "weekly-cos-management-checkpoint",
        "0 10 * * 1",
        (
            "Call company_management action=weekly_start to resume this ISO-week cycle, then summary_context on its "
            "parent. If all interviews and the synthesis card are complete, do nothing. Otherwise record a concise "
            "partial management note on the parent: completed roles, unavailable roles, actual failure/retry state, "
            "verified findings, blockers and next manager action. One unavailable role must not suppress the other "
            "notes. Check previous weeks for repeated unavailability. Keep the final synthesis dependency gate intact. "
            "Escalate only material human blockers; do not invent findings or force retries past policy."
        ),
    ),
)


def provision() -> list[str]:
    """Reuse named native jobs; never run a second scheduler or duplicate a job."""
    if os.environ.get("HERMES_PROFILE") != "chief-of-staff":
        raise PermissionError("CoS profile required for management scheduling")
    if get_timezone_name() != "America/Toronto":
        raise ManagementError("Persist CoS timezone America/Toronto before scheduling")
    existing = list_jobs(include_disabled=True)
    ids: list[str] = []
    for name, schedule, prompt in JOBS:
        matches = [job for job in existing if job["name"] == name]
        if len(matches) > 1:
            raise ManagementError(
                "Duplicate management jobs require explicit reconciliation"
            )
        if matches:
            job = update_job(
                matches[0]["id"],
                {"prompt": prompt, "schedule": schedule, "deliver": "local"},
            )
            if job is None:
                raise ManagementError("Existing management job vanished during update")
        else:
            job = create_job(
                prompt=prompt, schedule=schedule, name=name, deliver="local"
            )
        if resume_job(job["id"]) is None:
            raise ManagementError("Native scheduler failed to enable management job")
        ids.append(job["id"])
    return ids


if __name__ == "__main__":
    print(json.dumps({"job_ids": provision()}))
