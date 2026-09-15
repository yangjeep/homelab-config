# Merge-side policy observer integration — prepared offline

`Client.policy()` now obtains full policy evidence from the fixed local observer socket. `merge_policy.rules()` selects the exact configured quality/actor IDs from each newly obtained snapshot and applies its existing semantic checks. The initial gate and final pre-merge recheck both call `policy()` separately; nothing is cached between them. Other GitHub reads and the exact-head merge remain unchanged.

`merge_observer.snapshot()` connects only to `/run/leaselab-policy-observer/observer.sock`, resolves the noninteractive `leaselab-policy-observer` UID from local account configuration, rejects root/the merge process's own UID, and verifies Linux `SO_PEERCRED` before sending data. It does not import observer transport, configuration, key handling or token mint code. It imports only the shared, root-owned observer boundary models.

Each connection generates a cryptographically random 64-hex nonce, sends the fixed nonce-only JSON request, half-closes, then reads to EOF under a 30-second total request budget and a 2 MB cap. Connect timeout is two seconds. Exactly one newline-terminated JSON response is required. The echoed nonce, explicit fixed repository, current request-relative observation timestamp, nonempty bounded inventory and unique IDs are checked before converting details into existing typed ruleset inputs. Missing bypass data and observer error responses fail closed. A one-millisecond timestamp serialization tolerance is allowed at the request start, and one second of future clock tolerance; old observations are not reused.

The observer supplies complete current detail objects; the existing merge ruleset model/policy owns semantic authorization. Unrelated rulesets must also fit the existing ruleset model or the request fails closed. This is conservative and may reject future inherited/push policy shapes until explicitly supported. The merge gate does not infer missing bypass actors from timestamps, caller bypass rights or an old snapshot.

## Validation

- Red: the valid nonce-bound response test failed against a deny-only decoder stub.
- Local focused suite: 45 passed, 6 Linux-only tests skipped.
- LXC916 synthetic suite: **51 passed in 0.38 seconds**, no skips. It includes existing full merge-policy fixtures, final-observation actor revocation before merge, and a real fake Unix server running as UID65534. The real client accepts the expected server UID and rejects wrong UID, mismatched nonce, oversized response and stale observation.
- Basedpyright: 0 errors and 0 warnings for the full merge module set.
- Ruff and programming no-excuse checks passed for the changed Python files. Each new module/test stays below 200 pure lines; responsibilities are separated into response/client validation and security fixtures. No type suppression was introduced.

Only root-owned temporary test files and a private temporary Python venv were used on LXC916. Tests use synthetic responses, no production credentials, and no live observer. The temporary tree was removed afterward. The temporary server directory is intentionally owned by the test UID so a distinct-UID server can bind there; production uses the protected runtime path described in the observer deployment contract.

## Still pending

This code has not been deployed, and merge/observer remain disabled. The extra Administration-write App grant remains pending separate human authorization. Provisioning the observer UID/key/config, installing its root-owned model dependency, giving only the merge service access to the observer socket group, and starting services require that later approved deployment. No App, grant, credential, production service or merge was changed here.

Fresh observations are not an atomic GitHub policy snapshot or a lock spanning merge. Platform strict branch rules remain indispensable. The integration preserves the final fresh policy check; it does not claim to eliminate a change between that check and GitHub's actual mutation. No commit was created in this subtask; parent review/integration remains required.
