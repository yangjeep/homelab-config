# LeaseLab shell GitHub broker

This service exports only the fixed, reduced installation token for the connecting
Unix UID. It does not export App keys, elevated merge/release tokens, or publisher
tokens. `policy.py` is the full policy: six installed Apps and a disabled Engineer.
Even if App permissions grow, requested shell permissions do not grow. The GitHub
response must contain exactly the requested permissions and `yangjeep/leaselab`.

The protocol is exactly `get\n` followed by a write-side shutdown. There are no
request parameters. Linux `SO_PEERCRED`, not a role name, identifies the caller.
Startup resolves all seven fixed `leaselab-ROLE` Unix accounts; root, duplicate UIDs,
and the service UID cannot be role principals. Missing users prevent startup.
The service caches tokens in memory until 60 seconds before expiration; restart
clears that cache. Existing exported bearer tokens remain valid until GitHub
expiration/revocation. Unix root and the central runtime that controls role SSH
keys remain trusted infrastructure authorities; this service cannot isolate from
host root or prevent an authorized role from sharing its own short-lived token.

Runtime dependencies: Linux, Python 3.11+, `/usr/bin/openssl`, OS CA certificates.
Installer also needs `acl` (`setfacl`); optional `leaselab-gh` needs `/usr/bin/gh`.
Standard-library TLS deliberately disables environment proxies and redirect handling;
no new Python packages are required. The single serial loop has a two-second client
read timeout and a 20-second total request deadline, including signing/upstream
exchange. HTTPS has a ten-second socket timeout; request/response sizes are bounded.
Errors are generic and do not log request fields, JWTs, token bodies, or key bytes.

## Deployment on LXC916 (trusted administrator only)

1. Review these files and run the tests below before copying them to LXC916.
   Ensure seven distinct unprivileged `leaselab-ROLE` accounts already exist,
   including `leaselab-chief-of-staff`. No agent should have sudo, broker UID,
   service-group primary membership, or ability to edit installed code/systemd.
2. From a root-owned staging copy run `bash github-broker/install.sh` as root.
   This installs root-owned code, dedicated non-login `leaselab-github-broker`,
   the narrowly assigned `leaselab-github-clients` socket group, and the unit.
   It grants only the broker account traverse access on the existing private
   `/etc/leaselab-company` parent. It neither fetches keys nor starts the service.
   Verify an already-existing service account has no extra groups or sudo grants.
3. Through the existing trusted secret provisioner, place each of the six App PEMs
   at `/etc/leaselab-company/github/ROLE.pem`, owner `leaselab-github-broker`,
   mode `0600`, ordinary files with one link. Directory owner is the broker and
   mode `0700`. Never stage PEMs in Git, role homes, shell arguments, or output.
   Do not provision Engineer. Restart after key rotation to clear cached tokens.
4. Start with `systemctl enable --now leaselab-github-broker.service`.
   New SSH sessions are needed for supplementary group membership changes.
   As each role, configure Git:

   ```sh
   git config --global credential.https://github.com.useHttpPath true
   git config --global credential.https://github.com.helper ''
   git config --global --add credential.https://github.com.helper /usr/local/bin/leaselab-git-credential
   ```

   The blank helper resets inherited helper chains; inspect existing Git config
   and remove inherited token-bearing extraheaders/URL rewrites separately.
   Use `leaselab-gh ... --repo yangjeep/leaselab` for GitHub CLI calls. It injects
   only the caller token into the child environment, clears alternate token and
   debug environment settings, and does not persist authentication. The token is
   necessarily visible to processes under that same role UID.
5. As the trusted administrator verify directory/key/code ownership and modes,
   socket group contains exactly the seven role users, role-to-role UID isolation,
   no role can read PEMs, and unknown/root/service peers fail. Run safe read calls
   such as `git ls-remote https://github.com/yangjeep/leaselab.git` and
   `leaselab-gh api repos/yangjeep/leaselab --jq .full_name` from each enabled role;
   Engineer must fail. Do not print the helper's raw token response to evidence.
   Verify actual GitHub scopes safely before declaring provisioning complete.

This installer does not enable Engineer, install any App, mutate GitHub settings,
change branch protection, or establish exact-SHA QA/merge/release gates. Broad
Issues/PR write capabilities permit all GitHub operations within those scopes;
this is not a comments-only policy. No elevated service functionality exists here.

## Tests

From the company-config root:

```sh
uv run --with pytest pytest -q leaselab-company/tests/test_github_broker.py
```

Run on Linux under a disposable **nonroot** UID for real positive/negative kernel
peer-boundary coverage. macOS runs parser, scope, cache, sanitized-error, real
credential-helper subprocess/Unix socket, and OpenSSL signature tests; Linux-only
SO_PEERCRED tests skip there. Tests use synthetic tokens and temporary test RSA
keys, not real GitHub credentials. Upstream transport is tested at a substituted
HTTPS connection seam: no live token issuance or live GitHub authorization is
claimed by this suite. A compromised authorized role can occupy the serial loop
for a bounded interval; no per-role availability guarantee is provided.

### Source verification service and token compatibility

A separate nologin `leaselab-source-fetch` principal can obtain only Metadata,
Contents and Pull requests read access for `yangjeep/leaselab`. The broker reuses
its existing SRE App registration/key internally; no App private key is copied to
the fetch process and none of the seven role grants is broadened. Its output is
source materialization, not a QA verdict or merge authorization.

Installation tokens are opaque and may use GitHub's longer stateless format.
Producer and socket helper share a 4096-character resource bound; malformed,
control-character and oversized values remain denied. A real stateless token
read succeeded; a bounded revoke probe returned 204 then first observed 401 at
7.57 seconds. Do not assume revocation is instantaneous, or apply that one timing
observation as a guarantee for key rotation, uninstall or cache invalidation.
