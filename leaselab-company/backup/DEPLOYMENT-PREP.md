# Deployment preparation evidence — 2026-09-15

LXC916 prerequisites installed through the existing PVE administrative connection:

* rsync `3.4.1+ds1-5+deb13u4` installed from configured Debian repositories; rsync daemon stayed disabled.
* Existing LXC913 `/usr/bin/gitleaks` copied to LXC916 `/usr/bin/gitleaks`, root-owned mode0755. SHA256 verified on source, transfer and destination: `634c8a33c6fd95ef87339f1cc345304655e3d38535a942fd096c37393bd72f8a`.
* Reviewed files staged in `/root/leaselab-backup-review.n42SuV/{backup,tests}`, root-owned with group/other access removed. This directory contains no credentials.
* All shell syntax checks passed on916. Actual candidate fixture using the copied scanner passed allowlist preservation, synthetic-secret rejection and overlap/symlink refusal. `pytest -q tests/test_backup.py` reported **2 passed in 1.45s**, no skips.

The staging copy does not install units or activate jobs. No Git deploy key or NAS account was created, and no backup was pushed/uploaded.

The previous `nas-setup.sh` is designed to run inside an authenticated TrueNAS administrator shell using `midclt`. Its sibling `host-run` only connects to PVE then LXC913 using a setup key that is no longer present. It does not supply a NAS administration connection. PVE's existing known-host verification accepts `192.168.253.100`; an explicit read-only connection attempt with `IdentitiesOnly=yes -i /root/.ssh/id_rsa root@192.168.253.100` fails `Permission denied (publickey)`. A separately authorized NAS administrator identity is still required. Do not reuse the upload-only Homelab backup identity for provisioning.

## GitHub knowledge deployment completed — 2026-09-15 01:06 EDT

GitHub GraphQL verified `yangjeep/hermes-leaselab` is private and initially empty. REST deploy-key enumeration was rate-limited; the parent registered the generated public key through authenticated GitHub UI with write access restricted to this repository. Stable title `hermes-leaselab-backup-lxc916`, fingerprint `SHA256:JI9HnJhO0m0h4DxdIiDAUz1s+3rfrcjJnMpzBRnQL1o`. The private key was generated in place at `/var/lib/leaselab-backup/keys/github_ed25519` mode0600 and never printed or copied out.

Installed the reviewed scripts and units; copied LXC913's existing verified SSH known-host pins into `/etc/leaselab-backup/known_hosts` mode0600. Initialized a root-owned backup checkout on `main` with exact remote `git@leaselab-github:yangjeep/hermes-leaselab.git`.

First candidate, staged tree and complete history secret scans passed. Initial backup pushed successfully:

`c6161904c748bfa0663c7c1c56a618384a2b073e`

A separate fresh clone from GitHub matched that SHA, passed another secret scan, and was copied into an isolated restore directory. All seven roles' config.yaml, SOUL.md and profile.yaml matched current source bytes; all seven skill trees were present. Checks confirmed no `.env`, `auth.json`, raw `.db`, `.pem` or `.key` files. The source tree was not modified. Temporary restore data was removed after success. File counts were chief-of-staff327 and325 each for the other six profiles.

The hourly `leaselab-knowledge-backup.timer` is enabled and active; its first scheduled run was shown as 2026-09-15 02:04:35 EDT (hourly plus jitter). The checkout is clean. `leaselab-full-backup.timer` remains disabled; no TrueNAS provisioning or full upload has occurred in this phase.

## TrueNAS full deployment completed — 2026-09-15 01:14 EDT

After the parent established temporary authenticated NAS administration, inspected the real Homelab dataset/account and SSH effective configuration. Created only `main/homelab/backup/hermes-agent-leaselab` with POSIX/discard, base0711 and archives0700. Dedicated account `hermes-agent-leaselab-backup` UID3004/GID3003 has no sudo/password login, a unique generated-in-place LXC916 SSH identity, and public-key restriction `from="192.168.253.217"`. NAS key fingerprint: `SHA256:KOAwfNIzcpozZ7gcuJ717zvAyZM7v8+rJn7VNLKuaWw`. The private key remains only `/var/lib/leaselab-backup/keys/truenas_ed25519` mode0600.

Both authorized-key command and effective SSH ForceCommand confine uploads with `rrsync -wo -no-del -munge` to the new archive directory. Effective SSH settings disable forwarding, TTY, password and keyboard-interactive login. Real rejection tests returned:

* Shell: `SSH_ORIGINAL_COMMAND does not run rsync`.
* Download: `reading from write-only server is not allowed`.
* Delete request (dry run): `option --delete has been disabled on this server`.

The existing `/mnt/main/homelab` NFSv4 ACL required one new UID3004 TRAVERSE/NOINHERIT entry. No existing ACE was removed or modified; see `nas-ancestor-acl-diff.json`. NAS root-only before/after snapshots remain `/var/tmp/leaselab-backup-ancestor-acl-before.json` and `...-after.json`. Rollback removes only this new UID's exact traverse ACE from the current ACL; do not replace future ACL changes wholesale. `/mnt/main` already permits traversal and was not changed. Running as the new UID confirmed its own archive directory writable, while ancestor listing and Homelab archive listing were denied.

Actual uploaded archive:

`/mnt/main/homelab/backup/hermes-agent-leaselab/archives/hermes-leaselab-full-2026-09-15-051048Z.tar.gz`

Size118630017 bytes, mode0600, owned by the dedicated backup account. SHA256 matches creation, independent NAS checksum and administrator retrieval:

`49e370dadd2f7c851927067f842e14c14389bc625c95e92224f709dc0ecfeb6b`

The administrator connection streamed that exact archive into an owner-only isolated LXC916 restore directory. All SHA256SUMS entries, ZIP CRC and SQLite integrity checks passed. Actual `hermes import --force` into a fresh `/var/lib/leaselab-backup-staging/restore-drill.*/home` restored all seven profiles' config, SOUL, skills, .env, auth.json and state.db, plus kanban.db and shared-state.db. Every restored SQLite database passed integrity_check; restored profile .env permissions were0600. No active Hermes home was overwritten and no gateway was started from restored data.

Archive policy verification confirmed native .env/auth.json inclusion for all seven profiles and no external-provider expansion, with backup keys, role homes and `/etc/leaselab-company/ssh` absent from the host companion. This remains an unencrypted secret-bearing NAS archive under the original permission-protection policy.

After verification, enabled the daily full timer. Both timers are active; observed next runs were knowledge02:03:48 EDT and full03:32:18 EDT on2026-09-15. Secret-bearing temporary retrieved archives and extracted trees were removed after the drill; owner-only logs remain under `/var/lib/leaselab-backup/`. The parent's temporary NAS administrator entry is exclusively the parent's cleanup responsibility.

The temporary NAS administrator key was subsequently removed without changing existing keys. A fresh connection using that key was denied; its control socket was closed and local temporary private key deleted. Both backup timers remain enabled.
