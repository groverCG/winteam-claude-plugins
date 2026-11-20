#!/usr/bin/env bash
# Usage: base.sh <data-dir> <repo> <branch|commit> [--copy "path,path"]
# Checks out the "before" version in a reusable worktree, so the working copy is never touched: for a branch,
# the merge-base of HEAD and origin/<branch>; otherwise the commit given. Prints "<worktree> <sha>".
set -euo pipefail
data="$1"; repo="$2"; ref="$3"; shift 3
copy=""
[ "${1:-}" = --copy ] && copy="${2:-}"
case "$copy" in '${'*) copy="" ;; esac  # an unset plugin option

cd "$repo"
git fetch -q origin
if git rev-parse -q --verify "origin/$ref^{commit}" >/dev/null; then
  sha="$(git merge-base HEAD "origin/$ref")"
else
  sha="$(git rev-parse --verify "$ref^{commit}")"
fi

wt="$data/worktrees/before"
mkdir -p "$data/worktrees"
if git worktree list --porcelain | grep -qx "worktree $wt"; then
  git -C "$wt" checkout -q --detach --force "$sha"
else
  git worktree prune
  git worktree add -q --detach "$wt" "$sha"
fi
# The submodule URL is https; borrow gh's token for this one command (no global git config).
git -C "$wt" -c credential.helper= -c credential.helper='!gh auth git-credential' \
  submodule update -q --init --recursive

IFS=',' read -r -a files <<< "$copy"
for f in ${files[@]+"${files[@]}"}; do
  f="$(echo "$f" | xargs)"
  [ -n "$f" ] && [ -f "$repo/$f" ] && mkdir -p "$(dirname "$wt/$f")" && cp "$repo/$f" "$wt/$f"
done
echo "$wt $sha"
