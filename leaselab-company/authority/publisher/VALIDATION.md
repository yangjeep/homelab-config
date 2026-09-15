# Publisher job-store validation

2026-09-15. Step 1 only; no deployment, network, credentials, executor or publisher operation.

- Local real-filesystem pytest: **37 passed in 0.20s**.
- LXC 916 isolated `/tmp/leaselab-publisher-jobs-tests`, root-run temporary fixtures: **37 passed in 0.31s**. This is Linux filesystem/locking verification, not actual production service-UID admission testing.
- Core basedpyright `typeCheckingMode=all`: **0 errors, 0 warnings**.
- Repository Ruff: clean; programming no-excuse checker: no violations.
- Evidence: caller authority fields rejected; malformed/duplicate requests rejected; restart dedupe; running/terminal state sequencing; current-H/base staleness; old completed bytes preserved and ineligible; wrong role; symlink/hardlink/FIFO/oversized/world-writable file rejection; path traversal and unsafe root rejection; bounded lock contention; manifest identity tampering; final-state/mode mismatch; rename failure preserves prior bytes; interrupted pointer update recovers without PASS.

Architectural self-review: three files each own one boundary. Typed frozen Pydantic records cross input/storage boundaries. No Any/object/cast/ignore escape in implementation; no secrets or arbitrary evidence paths are stored. Completion digest is deliberately only an internal supervisor input and does not itself prove test authenticity. The module cannot be exposed as a PASS-accepting API. Full trusted execution/publication remains unimplemented.

Pure nonblank/noncomment source line counts: publisher_files.py: 81; publisher_models.py: 70; publisher_jobs.py: 103.

| File | SHA-256 |
| --- | --- |
| `publisher_files.py` | `398649035703096888e52b1ae1b4cf9041fb2ae9b7c7bd11a47dda8897ea4ef1` |
| `publisher_jobs.py` | `0643686f1446861e7094b8a1aaef5ff297ecac676a2491870b061e947f9bc0b9` |
| `publisher_models.py` | `b49da8d90325a68a044976cded2ff41d9b579bf108374f9f60cfae599dd7fbe5` |
| `test_publisher_jobs.py` | `e87754a41b1a33f56eb6c26893cb9e0e284ad99ec77ffdb7c43392f0a89b2c1d` |
