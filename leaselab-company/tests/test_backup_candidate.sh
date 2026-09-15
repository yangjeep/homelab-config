#!/bin/bash
set -euo pipefail
policy=${1:?backup directory required}
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT
for profile in chief-of-staff engineer qa-security reviewer sre support growth; do
 profile_home="$fixture/company/profiles/$profile"
 mkdir -p "$profile_home/skills"
 printf 'Durable instructions\n' > "$profile_home/SOUL.md"
 printf 'model: fixture\n' > "$profile_home/config.yaml"
 printf 'DO_NOT_COPY=fixture\n' > "$profile_home/.env"
 printf 'raw state\n' > "$profile_home/state.db"
 printf 'durable skill\n' > "$profile_home/skills/example.md"
 printf 'credential fixture\n' > "$profile_home/skills/auth.json"
done
bash "$policy/candidate.sh" "$fixture/company" "$fixture/clean" >/dev/null 2>&1
test -s "$fixture/clean/profiles/engineer/config.yaml"
test -s "$fixture/clean/profiles/engineer/skills/example.md"
test ! -e "$fixture/clean/profiles/engineer/.env"
test ! -e "$fixture/clean/profiles/engineer/state.db"
test ! -e "$fixture/clean/profiles/engineer/skills/auth.json"
# Synthetic test token, not a real credential.
printf 'github_token = ghp_%s\n' aB3cD4eF5gH6iJ7kL8mN9oP0qR1sT2uV3wX4 > "$fixture/company/profiles/engineer/skills/example.md"
if bash "$policy/candidate.sh" "$fixture/company" "$fixture/secret" >/dev/null 2>&1; then exit 1; fi
if bash "$policy/candidate.sh" "$fixture/company" "$fixture/company/overlap" >/dev/null 2>&1; then exit 1; fi
test ! -e "$fixture/company/overlap"
ln -s "$fixture/company" "$fixture/alias"
if bash "$policy/candidate.sh" "$fixture/alias" "$fixture/symlink" >/dev/null 2>&1; then exit 1; fi
printf 'Backup candidate allowlist, real gitleaks secret rejection, overlap and symlink guards: PASS\n'
