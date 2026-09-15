# Reviewer shell scope after App permission expansion

Observed on LXC916 at 2026-09-15T05:21:49Z. The parent task reported that
Reviewer App Contents write and Checks write were accepted by installation
161807039 for a future trusted controller. The shell broker grant was unchanged.

After restarting `leaselab-github-broker.service` to clear its in-memory cache,
a fresh installation token was requested through the installed broker's
`upstream.exchange` using its fixed Reviewer policy and service-held key.
Only this nonsecret metadata was emitted:

```json
{
  "app_id": 4948588,
  "installation_id": 161807039,
  "repositories": ["yangjeep/leaselab"],
  "permissions": {
    "actions": "read",
    "checks": "read",
    "contents": "read",
    "issues": "write",
    "metadata": "read",
    "pull_requests": "write",
    "statuses": "read"
  }
}
```

The installed parser accepted the returned repository and permissions as an
exact match. The diagnostic token was revoked immediately (HTTP 204).

The actual role client then requested a new token through the running Unix
socket broker and executed:

```sh
runuser -u leaselab-reviewer -- /usr/local/bin/leaselab-gh api repos/yangjeep/leaselab --jq .full_name
```

Exit code: 0. Output: `yangjeep/leaselab`.

No broker policy or GitHub grants changed during this validation. No token,
JWT, PEM, authorization header, or sensitive API response was printed.
The parent explicitly preferred returned-scope verification when sufficient;
therefore synthetic branch creation and check-run publication were not attempted.
This is evidence of actual newly issued read-only Contents/Checks scopes and a
successful broker-authenticated read, not evidence of an executed mutation's
HTTP 403 response. It does not validate the future privileged controller.
