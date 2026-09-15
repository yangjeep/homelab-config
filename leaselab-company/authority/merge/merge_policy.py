"""Deterministic exact-head merge decision; no credential or network handling."""
import base64
import hashlib
import re
from typing import Final, Protocol

from merge_models import (
    Checks,
    Commit,
    Comparison,
    Disposition,
    File,
    Issue,
    MergeResult,
    Policy,
    Pull,
    Request,
    Review,
    Ruleset,
    Runs,
)
from pydantic import TypeAdapter

REPO: Final = 'yangjeep/leaselab'
REVIEWER: Final = 'leaselab-reviewer[bot]'
WORKFLOW: Final = '.github/workflows/deploy-preview-pr.yml'
CHECKS: Final = {
    'Workers Builds: leaselab-worker-preview': 85455,
    'Worker Regression Tests': 15368,
    'leaselab/qa-exact-sha': 4948555,
    'leaselab/independent-review': 4948588,
}


class Denied(Exception):
    """The fixed merge policy could not establish authorization."""


class GitHub(Protocol):
    def get(self, path: str) -> bytes: ...
    def policy(self) -> tuple[Ruleset, ...]: ...
    def merge(self, request: Request) -> bytes: ...


def require(condition: bool) -> None:
    if not condition:
        raise Denied


def rules(api: GitHub, policy: Policy) -> None:
    snapshot = api.policy()
    require(len({entry.id for entry in snapshot}) == len(snapshot))
    quality_matches = [entry for entry in snapshot if entry.id == policy.quality_ruleset]
    actor_matches = [entry for entry in snapshot if entry.id == policy.actor_ruleset]
    require(len(quality_matches) == len(actor_matches) == 1)
    quality, actor = quality_matches[0], actor_matches[0]
    require(quality.id == policy.quality_ruleset and actor.id == policy.actor_ruleset)
    for entry in (quality, actor):
        require(entry.enforcement == 'active' and entry.target == 'branch')
        require(entry.conditions.ref_name.include == ['refs/heads/main'])
        require(entry.conditions.ref_name.exclude == [])
    require(quality.bypass_actors == [])
    require(len(actor.bypass_actors) == 1)
    bypass = actor.bypass_actors[0]
    require((bypass.actor_id, bypass.actor_type, bypass.bypass_mode) ==
            (4948588, 'Integration', 'pull_request'))
    require(any(rule.type == 'update' for rule in actor.rules))
    types = [rule.type for rule in quality.rules]
    require(len(types) == len(set(types)))
    require({'pull_request', 'required_status_checks', 'required_deployments',
             'deletion', 'non_fast_forward', 'required_linear_history'} <= set(types))
    for rule in quality.rules:
        if rule.type == 'required_status_checks':
            checks = rule.parameters.required_status_checks
            require(len(checks) == len(CHECKS))
            require({check.context: check.integration_id for check in checks} == CHECKS)
            require(rule.parameters.strict_required_status_checks_policy)
        if rule.type == 'pull_request':
            require(rule.parameters.dismiss_stale_reviews_on_push)
            require(rule.parameters.required_review_thread_resolution)
        if rule.type == 'required_deployments':
            require(set(rule.parameters.required_deployment_environments) == {
                'Preview – ops', 'Preview – storefront-alda', 'Preview – leaselab-site'})


def pull(api: GitHub, request: Request, policy: Policy) -> Pull:
    candidate = Pull.model_validate_json(api.get(f'/pulls/{request.pr}'))
    require(candidate.number == request.pr and candidate.head.sha == request.head)
    require(candidate.base.ref == 'main' and candidate.head.ref != 'main')
    for ref in (candidate.head, candidate.base):
        require(ref.repo.full_name == REPO and ref.repo.id == policy.repository_id)
    require(candidate.state == 'open' and not candidate.draft and not candidate.merged)
    require(candidate.mergeable is True and candidate.mergeable_state == 'clean')
    require(candidate.user.login != REVIEWER)
    return candidate


def attestations(api: GitHub, candidate: Pull) -> frozenset[int]:
    head, base = candidate.head.sha, candidate.base.sha
    result = Checks.model_validate_json(api.get(f'/commits/{head}/check-runs?filter=all&per_page=100'))
    require(result.total_count == len(result.check_runs) and result.total_count < 100)
    dispositions: list[frozenset[int]] = []
    for name, app_id in CHECKS.items():
        matching = [check for check in result.check_runs if check.name == name]
        require(len(matching) == 1)
        check = matching[0]
        require(check.app.id == app_id and check.head_sha == head)
        require(check.status == 'completed' and check.conclusion == 'success')
        if name.startswith('leaselab/'):
            require(check.external_id == f'leaselab:v1:pr:{candidate.number}:head:{head}:base:{base}')
            disposition = Disposition.model_validate_json(check.output.summary or '')
            require((disposition.pr, disposition.head, disposition.base) == (candidate.number, head, base))
            require(len(disposition.resolved_issues) == len(set(disposition.resolved_issues)))
            dispositions.append(frozenset(disposition.resolved_issues))
    reviews = TypeAdapter(list[Review]).validate_json(api.get(f'/pulls/{candidate.number}/reviews?per_page=100'))
    require(len(reviews) < 100)
    latest = {review.user.id: review for review in sorted(reviews, key=lambda item: item.id)}
    require(all(review.state != 'CHANGES_REQUESTED' for review in latest.values()))
    approving = [review for review in latest.values() if review.user.login == REVIEWER]
    require(len(approving) == 1)
    approval = approving[0]
    require(approval.state == 'APPROVED' and approval.commit_id == head)
    require(approval.user.id != candidate.user.id)
    commits = TypeAdapter(list[Commit]).validate_json(api.get(f'/pulls/{candidate.number}/commits?per_page=100'))
    require(0 < len(commits) < 100 and commits[-1].sha == head)
    require(all(commit.author is not None and commit.committer is not None for commit in commits))
    require(all(commit.author.login != REVIEWER and commit.committer.login != REVIEWER
                for commit in commits if commit.author is not None and commit.committer is not None))

    require(len(dispositions) == 2)
    return dispositions[0] & dispositions[1]


def ci(api: GitHub, candidate: Pull, policy: Policy) -> None:
    head, base = candidate.head.sha, candidate.base.sha
    comparison = Comparison.model_validate_json(api.get(f'/compare/{base}...{head}'))
    require(comparison.status == 'ahead' and comparison.behind_by == 0)
    require(comparison.merge_base_commit.sha == base)
    runs = Runs.model_validate_json(api.get(f'/actions/workflows/211331547/runs?head_sha={head}&per_page=100'))
    require(runs.total_count == len(runs.workflow_runs) == 1)
    run = runs.workflow_runs[0]
    require(run.workflow_id == 211331547 and run.path == WORKFLOW)
    require(run.head_sha == head and run.event == 'pull_request' and run.run_attempt == 1)
    require(run.status == 'completed' and run.conclusion == 'success')
    checks = Checks.model_validate_json(api.get(f'/commits/{head}/check-runs?filter=all&per_page=100'))
    regression = [check for check in checks.check_runs if check.name == 'Worker Regression Tests']
    require(len(regression) == 1 and regression[0].check_suite.id == run.check_suite_id)
    for ref in (base, head):
        workflow = File.model_validate_json(api.get(f'/contents/{WORKFLOW}?ref={ref}'))
        require(workflow.path == WORKFLOW)
        decoded = base64.b64decode(''.join(workflow.content.split()), validate=True)
        require(hashlib.sha256(decoded).hexdigest() == policy.workflow_sha256)


def contract(api: GitHub, candidate: Pull, resolved: frozenset[int]) -> None:
    matches = [match.group(1) for match in re.finditer(
        r'(?im)^\s*(?:closes|fixes|resolves)\s+#([1-9][0-9]*)\s*[.]?\s*$', candidate.body or '')]
    closing = frozenset(int(number) for number in matches)
    require(0 < len(closing) <= 20 and len(closing) == len(matches))
    for number in closing:
        issue = Issue.model_validate_json(api.get(f'/issues/{number}'))
        require(issue.number == number and issue.state == 'open' and bool(issue.body))
    issues = TypeAdapter(list[Issue]).validate_json(api.get('/issues?state=open&per_page=100'))
    require(len(issues) < 100)
    # Only a closing-linked issue resolved by both trusted exact-SHA publishers is exempt.
    for entry in issues:
        labels = {label.name.casefold() for label in entry.labels}
        require(not labels.intersection({'founder-decision', 'founder-blocked'}))
        if entry.number in closing and entry.number in resolved:
            continue
        require(not any(re.search(r'\bp[01]\b', label) for label in labels))
        require(not labels.intersection({'security'}))


def execute(api: GitHub, request: Request, policy: Policy) -> MergeResult:
    require(policy.enabled)
    rules(api, policy)
    candidate = pull(api, request, policy)
    resolved = attestations(api, candidate)
    contract(api, candidate, resolved)
    ci(api, candidate, policy)
    rules(api, policy)
    current = pull(api, request, policy)
    require(current.base.sha == candidate.base.sha and current.user == candidate.user)
    # Head is a server-enforced precondition; strict rules constrain base movement.
    result = MergeResult.model_validate_json(api.merge(request))
    require(result.merged and result.sha != request.head)
    merged = Pull.model_validate_json(api.get(f'/pulls/{request.pr}'))
    require(merged.merged and merged.state == 'closed' and merged.head.sha == request.head)
    require(merged.merge_commit_sha == result.sha and merged.base.repo.id == policy.repository_id)
    return result
