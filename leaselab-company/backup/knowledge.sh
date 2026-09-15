#!/bin/bash
set -euo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export GIT_SSH_COMMAND='ssh -F /etc/leaselab-backup/ssh_config'
exec 9>/var/lib/leaselab-backup/knowledge.lock
flock -n 9 || exit 0
source_home=/var/lib/leaselab-company
repo=/var/lib/leaselab-backup/repo
test -d "$source_home/profiles"
candidate_parent=$(mktemp -d /var/lib/leaselab-backup/staging/knowledge.XXXXXX)
candidate="$candidate_parent/tree"
staged=''
trap 'rm -rf -- "$candidate_parent"; test -z "$staged" || rm -rf -- "$staged"' EXIT
/etc/leaselab-backup/candidate.sh "$source_home" "$candidate"
cd "$repo"
test "$(git branch --show-current)" = main
# A failed earlier push is retried even when the content has not changed.
test "$(git remote get-url origin)" = git@leaselab-github:yangjeep/hermes-leaselab.git
git fetch origin
if git show-ref --verify --quiet refs/remotes/origin/main; then
 git merge --ff-only origin/main >/dev/null
fi
rsync -rt --delete --exclude=.git/ "$candidate/" "$repo/"
git add --all -- README.md .gitignore profiles
# Scan the exact staged tree, including deletions, before committing.
staged=$(mktemp -d /var/lib/leaselab-backup/staging/index.XXXXXX)
git checkout-index --all --prefix="$staged/"
if ! gitleaks detect --no-git --source "$staged" --config /etc/leaselab-backup/gitleaks.toml --redact --no-banner; then
 rm -rf -- "$staged"
 echo 'Staged credential scan failed: no commit or push performed.' >&2
 exit 1
fi
rm -rf -- "$staged"
if ! git diff --cached --quiet; then
 git commit -m "backup: LeaseLab Hermes state $(date -u '+%Y-%m-%d %H:%M UTC')"
fi
# History scan also protects retries of previously unpushed commits.
gitleaks detect --source "$repo" --config /etc/leaselab-backup/gitleaks.toml --log-opts=--all --redact --no-banner
git push -u origin main
echo "Knowledge backup complete: $(git rev-parse HEAD)"
