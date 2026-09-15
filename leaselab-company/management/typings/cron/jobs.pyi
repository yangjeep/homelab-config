from typing import TypedDict

class Job(TypedDict):
    id: str
    name: str

class Update(TypedDict):
    prompt: str
    schedule: str
    deliver: str

def list_jobs(include_disabled: bool = ...) -> list[Job]: ...
def create_job(
    prompt: str | None, schedule: str, name: str | None = ..., deliver: str | None = ...
) -> Job: ...
def update_job(job_id: str, updates: Update) -> Job | None: ...
def resume_job(job_id: str) -> Job | None: ...
