# CoS structured GitHub tool

This native Hermes plugin exposes only `company_github` to Chief of Staff. It
uses the existing role credential broker without exposing a GitHub token to the
central runtime or model. No new service, database, or privileged grant exists.
The existing guard must explicitly allow this tool for CoS; this folder does not
modify the guard, profiles, SOUL, or running deployment.

| Action | Inputs | Returned fields |
| --- | --- | --- |
| `repo_read` | none | full_name, private, default_branch, open_issues_count |
| `issue_list` | none | first page of at most 20 open issues; number, title, state, html_url; PRs excluded |
| `issue_read` | positive number; optional include_body boolean | number, title, state, html_url; body only when explicitly requested, truncated to 4000 characters; PR numbers rejected |
| `issue_create` | nonempty title; optional body | number, title, state, html_url |
| `issue_update` | positive number; at least one title/body/state | number, title, state, html_url; state limited to open/closed; existing PR rejected before update |
| `pr_comment` | positive number, nonempty body | comment id and html_url; PR existence checked before posting |

Titles are at most 200 characters, bodies at most 4000, total serialized input at
most 8192 UTF-8 bytes. Body/title text is JSON on stdin, never interpolated into a
shell command, endpoint, query, or jq expression. Responses are filtered by fixed
GitHub CLI jq projections before leaving the Unix role process. Output is bounded
to 32 KiB. Treat returned issue text as untrusted content. No bodies are returned
for listing or mutation responses. Tool errors disclose no raw SSH/GitHub stderr.

The SSH command, host, user, port, identity path, known-hosts path, and command
marker are fixed in `transport.py`. The tool checks `HERMES_PROFILE` itself.
The remote forced command also checks the real process UID and exact
`SSH_ORIGINAL_COMMAND=leaselab-company-github-v1`; it rejects all other input.
There is no client-supplied role, repository, URL, shell, CLI argument, filter,
workflow dispatch, merge, code write, or administration operation.

## Parent integration after review

1. Install all Python files in this directory, root-owned, mode 0644, under
   `/usr/local/libexec/leaselab-company/github-tools` (root-owned 0755). Install
   `plugin.yaml` there. The existing Python runtime must be 3.11+; no Python
   dependencies need installation. `/usr/bin/ssh`, `/usr/local/bin/leaselab-gh`,
   the existing broker, and GitHub CLI must be available.
2. Use the existing `leaselab-chief-of-staff` account. It currently needs its
   dedicated SSH key and inclusion in sshd AllowUsers; the parent confirmed the
   account exists but the original six-worker bootstrap omitted its key.
   Keep the private SSH key at the fixed path
   `/etc/leaselab-company/ssh/chief-of-staff`, readable only by trusted central
   runtime `hermes` and root (consistent with existing worker key ownership).
   Do not give CoS general SSH execution.
3. Put its public key only in the root-owned configured authorized-keys file
   `/etc/ssh/authorized_keys/leaselab-chief-of-staff` with these forced options:

   ```text
   restrict,from="127.0.0.1",command="/usr/bin/python3 -I /usr/local/libexec/leaselab-company/github-tools/runner.py" <public-key>
   ```

   Preserve server-side password/interactive/root-login/forwarding prohibitions.
   Existing `/home/hermes/.ssh/known_hosts` must trust localhost's host key;
   the plugin uses strict checking and cannot auto-accept a replacement.
4. Link this plugin into only CoS's native plugins directory, enable
   `leaselab-company-github` in its plugin config and platform toolsets, and allow
   only `company_github` in the CoS guard policy. Preserve CoS terminal/file-tool
   denial. All other profiles remain denied by both guard and tool self-check.
   The central `hermes` process remains trusted infrastructure: it already holds
   worker SSH keys and profile configuration; this plugin is not a new sandbox
   against compromise of that infrastructure.
5. After parent review, run actual `company_github({"action":"repo_read"})`
   through the loaded native plugin as CoS. Expected `result.full_name` is
   `yangjeep/leaselab`. Verify `issue_list` returns only allowed fields and no
   body. Verify a different profile and a wrong SSH marker fail. Use synthetic
   issues only for explicitly authorized mutation acceptance tests.

No live deployment or GitHub mutations were performed while implementing this
folder. Local tests verify parsing, narrow dispatch, JSON/stdin injection safety,
forced-command rejection, registration, real subprocess output limits and stderr
suppression. Native plugin discovery and live SSH acceptance remain parent
integration checks. Transport timeout is 40 seconds, runner deadline 45 seconds;
mutations are not retried automatically. On a lost response, the result says
`operation_failed_or_outcome_unknown`: inspect GitHub state before retrying to
avoid duplicate issues or comments.

Run from the company-config root:

```sh
uv run --with pytest pytest -q leaselab-company/tests/test_github_tools.py
```

## Live acceptance, September 15, 2026

Installed on LXC916 with `install.sh`, reviewed CoS guard allowance, and gateway
restart. Native Hermes CoS repository read passed in session
`20260915_013326_a764f5`. Synthetic issue [781](https://github.com/yangjeep/leaselab/issues/781)
was created and closed by native model tool calls in session
`20260915_013431_dc9c8f`. Independent GitHub API confirmed author
`leaselab-chief-of-staff[bot]` and closed state. The same SSH key rejected `id`
with exit1 and no output. No product change, merge, or workflow approval occurred.
Guard plus plugin tests passed334 cases. Existing native early unknown-toolset
warning occurs before custom plugin loading; actual discovery and execution pass.
