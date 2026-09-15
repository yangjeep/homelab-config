# Merge authority validation

2026-09-15. No commit created; file SHA-256 below binds this offline verification. Not production acceptance.

- Local pytest: **29 passed, 1 Linux-only skip**.
- LXC 916 isolated `/tmp/leaselab-merge-offline-tests`: **30 passed in 0.25s**, including actual Linux socket SO_PEERCRED wrong-UID denial. No service installed or started.
- basedpyright `typeCheckingMode=all`: **0 errors, 0 warnings** on five service/client/model files.
- Repository-configured Ruff check: passed after import sorting; shell `sh -n`: passed.
- Programming no-excuse checker: no violations on five files.
- Client matching CLI surface: `--help` printed protocol; malformed `null` stdin denied without network request.
- Tests cover valid synthetic merge mapping; missing/stale/wrong-App/duplicate/failed/base-mismatched QA; stale PR; self-authored PR/commit; missing contract; quality bypass; disabled actor rules; malformed request/API; P1 blockers; missing mutual current-SHA resolution; unlinked resolved issue; stale review; wrong workflow/rerun/changed workflow bytes; disabled service policy.
- Live GitHub merge, real role-credential denial, native rules enforcement, trusted publication, and production deploy gates: **NOT RUN / prerequisite work remains**.

Architecture review: each file owns input parsing, decision policy, fixed transport, socket lifecycle, or client UI. Typed Pydantic evidence crosses the boundary; no Any/object/cast/ignore escapes in implementation. Largest file remains under 200 nonblank/noncomment lines. No external input controls repository/HTTP method/URL/credential scope. Fixed stdlib transport follows the pre-existing reviewed broker design. No raw upstream errors/tokens are printed.

| File | SHA-256 |
| --- | --- |
| `merge_client.py` | `5fb4184ffaa5087da3ce641cd292b8b111c7cb13b9422daf1da073d1eb35e1db` |
| `merge_models.py` | `b338e29498aa5fa9c3f1bebf84d4b43fdfc4f99bc24e6cd90d6e5f0b1a811c46` |
| `merge_policy.py` | `39f26b5a8276aa6eaacbc2de55d0644ff145ef36599a24c9acb0d50f0c58da8e` |
| `merge_server.py` | `8900df70e831e4d866ef3ecdfb5d734341001341f2e522667d65c585b5d24404` |
| `merge_transport.py` | `6371076b3614ccd783302a2522e27c46261b6ce38f5ca621bea24b25d86d1b1d` |
| `install.sh` | `179362dc587fa73a6af3ce1cdee063a3060bfb8ee8162e0bb49ac19b6a94fee7` |
| `leaselab-merge.service` | `dfea1423d93aa9ef79c5c5d317e218e922a1be8bab0e9d29da1f3eede51799d2` |
| `test_merge_gate.py` | `cb1bf7872cfe88e0d2f12af0d06ca6615c27589c988a331d95367eb3d2acb247` |
