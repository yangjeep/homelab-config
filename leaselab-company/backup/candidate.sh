#!/bin/bash
set -euo pipefail
umask 077
source_home=${1:?source root required}
candidate=${2:?new empty destination required}
policy=$(cd -- "$(dirname -- "$0")" && pwd)
test -d "$source_home/profiles"
test ! -L "$source_home"
test ! -L "$source_home/profiles"
test "$(realpath "$source_home")" = "$source_home"
# Refuse source overlap and existing destinations before writing.
case "$(realpath -m "$candidate")/" in "$source_home/"*) exit 1;; esac
mkdir -m 700 "$candidate"
cp "$policy/templates/README.md" "$policy/templates/.gitignore" "$candidate/"
homes=()
names=()
if test -d "$source_home/profiles"; then
 for profile in "$source_home"/profiles/*; do
  test -d "$profile" || continue
  test ! -L "$profile" || { echo 'Symlink profile refused' >&2; exit 1; }
  homes+=("$profile"); names+=("$(basename "$profile")")
 done
fi
for index in "${!homes[@]}"; do
 home=${homes[$index]}
 target="$candidate/profiles/${names[$index]}"
 mkdir -p "$target"
 for subtree in notes memory memories skills; do
  test ! -L "$home/$subtree" || { echo 'Symlink source refused' >&2; exit 1; }
  if test -d "$home/$subtree"; then
   mkdir -p "$target/$subtree"
   rsync -rt --no-links --exclude-from="$policy/excludes" \
    --include='*/' --include='*.md' --include='*.txt' --include='*.rst' \
    --include='*.py' --include='*.sh' --include='*.js' --include='*.mjs' --include='*.cjs' --include='*.ts' \
    --include='*.json' --include='*.yaml' --include='*.yml' --include='*.toml' \
    --include='*.csv' --include='*.html' --include='*.css' --include='LICENSE' \
    --exclude='*' --prune-empty-dirs "$home/$subtree/" "$target/$subtree/"
  fi
 done
 for instruction in SOUL.md AGENTS.md config.yaml profile.yaml; do
  test ! -L "$home/$instruction" || { echo 'Symlink instruction refused' >&2; exit 1; }
  if test -f "$home/$instruction"; then cp "$home/$instruction" "$target/"; fi
 done
done
for profile in chief-of-staff engineer qa-security reviewer sre support growth; do
 test -s "$candidate/profiles/$profile/SOUL.md"
 test -s "$candidate/profiles/$profile/config.yaml"
done
# Fixed installed policy, never configuration from the copied candidate.
gitleaks detect --no-git --source "$candidate" --config "$policy/gitleaks.toml" --redact --no-banner
