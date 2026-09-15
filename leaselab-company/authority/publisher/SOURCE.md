# Trusted exact-source materialization (step 3)

`source_supervisor.py` accepts only a bounded `{head,base}` JSON pair of full lowercase 40-hex Git commit IDs for fixed repository `yangjeep/leaselab`. It is root-only. It is not a caller-facing service, PR validator, verdict publisher or merge endpoint.

The dedicated nologin `leaselab-source-fetch` identity receives an installation token through the existing UID-authenticated broker. Its separate `SERVICE_ROLES` grant contains only metadata/contents/pull_requests read. The existing broker-held SRE App key signs the exchange; no App key is copied to this account and the original seven role grants are unchanged. The fetch token remains in that process, never in argv, environment, a child command, source, metadata or logs. No role identity is impersonated.

The fetcher calls fixed GitHub HTTPS API endpoints to bind each commit to its tree, reconstructs every Git tree object/hash, and rejects truncated/malformed/oversized trees. It obtains the exact-commit archive through a manually checked redirect to the fixed codeload repository/SHA path. The API bearer is not forwarded to codeload; signed archive URLs remain in memory. Environment proxies and automatic redirects are disabled.

There is no `git` subprocess, clone, checkout, credential helper invocation through Git, filter, smudge, hook, submodule update or repository-local configuration evaluation. Archive extraction is manual: only expected regular files are created after exact blob SHA/size validation. Tar ownership/modes are ignored; executable bits come from the verified Git tree. Traversal, `.git` aliases, control characters, duplicates/casefold collisions, links, device/FIFO entries, sparse files, unexpected/missing files and altered contents fail closed. Submodules and symlinks intentionally block this initial policy. Git LFS substitutions or export attributes that change/omit bytes also fail hash/completeness checks.

Bounds: 10,000 tree entries, 16 MiB/file, 128 MiB total source, 64 MiB compressed archive, 144 MiB decompressed tar, 8 MiB API tree response. Fetch process output is capped at 64 KiB and lifetime 180 seconds. Paths are bounded in bytes/depth. The supervisor rechecks every file and copies into independent root-owned inodes; complete source files/directories are 0444/0555 and contain no `.git`. `pair.json` is written only after both source trees are verified. Failed/incomplete directories do not represent complete materialization; retry/garbage-collection integration is not implemented yet and must not treat path existence as success.

Private fetch work is under `/var/lib/leaselab-publisher/source-fetch/PAIR_ID`; final source under `/var/lib/leaselab-publisher/sources/PAIR_ID/{head,base}`. PAIR_ID is the SHA-256 of canonical typed pair JSON. Repeated existing destinations are denied, never silently overwritten. Fetch source cannot modify the supervisor-owned final copy.

`source_probe_runner.py` reuses the existing executor UIDs, per-role lock and bounded supervisor capture. It mounts real head/base source read-only in an auth-free network-isolated bubblewrap environment. Reviewer receives no scratch; QA receives separate writable scratch. The fixed probe reads actual `apps/leaselab-site/package.json`, verifies source writes fail and private auth/broker paths are absent. It does not execute repository scripts, install dependencies, build applications or perform product QA.

Install executor step 2 first, deploy matching broker policy/client files, then run `install-source.sh`. The existing broker needs a restart for its new fixed UID mapping. No publisher unit is installed/enabled here. No model authorization is migrated or renewed.

## Token compatibility fix

GitHub's [May 15 changelog](https://github.blog/changelog/2026-05-15-github-app-installation-tokens-per-request-override-header/) documents longer opaque installation tokens. The old 512-character parser and helper receive limits rejected a valid-shape 520-character synthetic token. Both now use the same 4096-character resource bound; control characters, whitespace and oversized responses remain rejected. Tokens are not decoded to infer authority; the exchange response still must prove exact repository, permissions and expiration.

Production minting leaves the optional format override header absent. A one-off live opt-in probe validated a real stateless token. Revocation returned 204 while reads remained accepted briefly; a bounded follow-up first observed 401 at 7.57 seconds. Do not promise instantaneous installation-token invalidation. Broker cache invalidation, App key rotation and App uninstall are different operations; this test does not establish their timing.

## Remaining integration gaps

Fresh PR number/head/base validation and final stale-candidate recheck belong to the future trusted publisher supervisor. H/B binding here proves source identity, not that the pair is currently mergeable. Still absent: approved test recipes/dependency acquisition, candidate execution, live model review of real source, durable finding ledger/dispositions, semantic attestations, GitHub check publication and merge integration. No PASS is accepted or published. A complete source tree is not evidence of code quality.
