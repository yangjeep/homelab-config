# Publisher job storage, step 1 only

This module parses run requests and stores trusted-supervisor job lifecycle state. It does not execute Codex/tests, read credentials, fetch GitHub, expose a socket, publish checks, or determine whether evidence is genuine. It is not a completed publisher.

`parse_request(bytes)` accepts at most 256 bytes with exactly `{ "pr": positive_integer, "head": "40 lowercase hex" }`. Duplicate keys, extra authority fields, boolean PR IDs, trailing data, malformed values and oversized input fail. Role, base, repository, paths, commands and PASS are never caller inputs.

A future trusted supervisor constructs `Candidate` from a fresh fixed-repository observation. `Jobs(Files(absolute_private_directory), fixed_role)` is configured per service instance; use separate directories for QA and Reviewer. Candidate repository is fixed to `yangjeep/leaselab`; role is one of `qa-security` or `reviewer`. The source request's PR/head must match the supervisor observation.

- `begin(request, candidate)` derives a job ID from repository/role/PR/H/B/policy version, returns an existing identical job on duplicate submission, and atomically selects the current job for that PR. A previous nonterminal job becomes stale; previous completed manifests stay unchanged.
- `start(job_id, fresh_candidate)` changes queued to running, idempotently returns running, or finalizes stale if the observation/current pointer differs.
- `complete(job_id, fresh_candidate, completion)` accepts only a running job and a **supervisor-owned** `Completion` with evidence digest. It finalizes passed/failed/blocked, or stale if H/B changed. This internal API must never be bound to a caller-supplied PASS endpoint.
- `eligible(job_id, fresh_candidate)` requires passed, matching repository/PR/H/B, and the current pointer. Reading an old manifest whose state is passed is not sufficient.
- Terminal state is immutable through this API. Repeated submission returns its existing terminal result, not a new attempt. Retry-attempt orchestration and policy/contract/scenario digests are future work; do not overwrite a completed manifest to implement retries.

The directory must already exist, be absolute, contain no symlink components, be owned by the effective service UID and have mode 0700. It is not created by this module. All operations use the opened directory descriptor and generated names, O_NOFOLLOW, regular-file/owner/link-count/mode checks, bounded 16 KiB reads and nonblocking flock. No arbitrary evidence path is accepted. All writes stage a fresh O_EXCL temporary file, fsync, atomically replace and fsync the directory. Mutable records are 0600; completed manifests are 0400 and overwrite is denied. This protects the service boundary and accidental mutation; it is not an assertion that root or a compromised trusted service UID cannot chmod files.

A pointer update can fail after a new queued manifest was persisted. Retrying `begin` reuses that manifest and safely completes the pointer update; old state cannot become a false PASS. Failed writes propagate. Lock contention returns immediately for the future request layer to retry with bounds. No busy loop, network or unbounded directory scan is present.

`publisher_models.py` owns strict records and request parsing; `publisher_files.py` owns safe atomic file operations; `publisher_jobs.py` owns lifecycle transitions. `pyrightconfig.json` uses all diagnostics with two intentional exceptions: installed flat-module import resolution, and the exhaustive `assert_never` fallback required by the programming skill.

No production path was provisioned and no existing merge code was changed. Integration must still authenticate callers, retain executor isolation, independently validate evidence, include trusted contract/scenario identity and implement GitHub publication from supervisor-owned results.
