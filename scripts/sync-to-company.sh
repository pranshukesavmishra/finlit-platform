#!/usr/bin/env bash
# Brings the NEW work of this repository into the company repository's finlit-platform/ folder, on a new branch, keeping whatever the team has
# changed inside that folder (a three-way patch). Use it after the first delivery (scripts/export-to-company.sh), whenever this repo has moved on.
#
#   scripts/sync-to-company.sh             # dry run: builds the branch in a temporary clone and shows what it would push
#   scripts/sync-to-company.sh --push      # the same, then pushes the branch; open a pull request from it on GitHub
#
# Environment: COMPANY_REMOTE (default https://github.com/Yusra-Khan532/Financial-Portfolio.git)   FOLDER (default finlit-platform)
#              BASE (default: the company's default branch)   BRANCH (default pranshu-sync-<short sha>)
# How it knows where the last delivery stopped: the company repo's last commit whose message ends with "... at <sha>" (the export and this
# script both write that). It patches the difference <that sha> .. HEAD of this repo onto the folder. A conflict stops the script with the
# file names: nothing is pushed. It needs git access to the company repository (your GitHub login; never paste a token into a chat).
set -euo pipefail
REMOTE="${COMPANY_REMOTE:-https://github.com/Yusra-Khan532/Financial-Portfolio.git}"
FOLDER="${FOLDER:-finlit-platform}"
PUSH=0; [ "${1:-}" = "--push" ] && PUSH=1
SRC="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

[ -z "$(git -C "$SRC" status --porcelain)" ] || { echo "Commit or stash your changes first: the sync uses what is committed (HEAD)." >&2; exit 1; }
HEAD_SHA="$(git -C "$SRC" rev-parse --short HEAD)"
BRANCH="${BRANCH:-pranshu-sync-$HEAD_SHA}"

echo "1/6 cloning the company repository ($REMOTE)"
git clone -q "$REMOTE" "$WORK/company"
cd "$WORK/company"
BASE="${BASE:-$(git symbolic-ref --short HEAD)}"
[ -d "$FOLDER" ] || { echo "No $FOLDER/ folder on $BASE: run scripts/export-to-company.sh first (the first delivery)." >&2; exit 1; }
git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1 && { echo "Branch $BRANCH already exists on the company repository: choose another BRANCH." >&2; exit 1; }

echo "2/6 finding where the last delivery stopped"
OLD="$(git log -n 1 --grep='finlit-platform at [0-9a-f]\{7,40\}' --format=%s | sed -n 's/.* at \([0-9a-f]\{7,40\}\)$/\1/p')"
[ -n "$OLD" ] || { echo "Could not find the last delivery (a commit message ending 'at <sha>') on the company repository." >&2; exit 1; }
git -C "$SRC" cat-file -e "$OLD^{commit}" 2>/dev/null || { echo "The last delivered commit $OLD is not in this repository's history: fetch the full history (git fetch --unshallow) and try again." >&2; exit 1; }
[ "$(git -C "$SRC" rev-parse "$OLD")" != "$(git -C "$SRC" rev-parse HEAD)" ] || { echo "Nothing new: the company repository already has $HEAD_SHA."; exit 0; }
echo "    last delivery: $OLD   now: $HEAD_SHA   ($(git -C "$SRC" rev-list --count "$OLD"..HEAD) commits)"

git checkout -q -b "$BRANCH" "origin/$BASE"
echo "3/6 applying the new work to $FOLDER/ (three-way, keeps the team's changes)"
git -C "$SRC" diff --binary --no-color "$OLD" HEAD > "$WORK/new.patch"
if ! git apply --3way --index --directory="$FOLDER" "$WORK/new.patch" 2> "$WORK/apply.log"; then
  echo "STOP: the new work conflicts with changes made in $FOLDER/ on $BASE. Files:" >&2
  grep -E "^(error|Applied patch .* with .* conflict)" "$WORK/apply.log" | head -20 >&2
  git diff --name-only --diff-filter=U >&2 || true
  echo "Nothing was pushed. Ask Pranshu's Claude to merge those files by hand, then run this again." >&2
  exit 1
fi

echo "4/6 checking for secrets"
BAD=0
# real key formats: everywhere; a database address with a password: everywhere except test folders (they use made-up passwords on purpose)
if grep -rIlE '(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[abp]-[0-9A-Za-z-]{10,}|ghp_[0-9A-Za-z]{30,}|sk-[A-Za-z0-9]{32,})' "$FOLDER" > "$WORK/hits.txt" 2>/dev/null; then BAD=1; fi
if grep -rIlE --exclude-dir=tests --exclude-dir=node_modules '(mongodb\+srv://[^ "<]+:[^ "<@]+@|postgres(ql)?://[^ "<:]+:[^ "<@$]{12,}@)' "$FOLDER" >> "$WORK/hits.txt" 2>/dev/null; then BAD=1; fi
if find "$FOLDER" \( -name ".env" -o -name "*.pem" -o -name "*.key" \) | grep -q .; then BAD=1; find "$FOLDER" \( -name ".env" -o -name "*.pem" -o -name "*.key" \) >> "$WORK/hits.txt"; fi
if [ "$BAD" = 1 ]; then echo "STOP: possible secrets:" >&2; cat "$WORK/hits.txt" >&2; exit 1; fi

echo "5/6 committing"
git add -A "$FOLDER"
git -c user.name="${GIT_AUTHOR_NAME:-$(git -C "$SRC" config user.name || echo Pranshu)}" -c user.email="${GIT_AUTHOR_EMAIL:-$(git -C "$SRC" config user.email || echo pranshu@users.noreply.github.com)}" \
  commit -q -m "Sync $FOLDER/ with pranshukesavmishra/finlit-platform: $(git -C "$SRC" rev-list --count "$OLD"..HEAD) commits since the last delivery - finlit-platform at $HEAD_SHA" \
  -m "Applies the difference $OLD..$HEAD_SHA as a three-way patch, so changes made in $FOLDER/ by the team are kept. Nothing outside $FOLDER/ is changed."
git show --stat --oneline HEAD | tail -4
echo "files changed in $FOLDER/: $(git diff --name-only HEAD~1 HEAD | wc -l)"

if [ "$PUSH" = 1 ]; then
  echo "6/6 pushing $BRANCH"
  git push -u origin "$BRANCH"
  echo "Done. Open a pull request from $BRANCH on GitHub."
else
  echo "6/6 dry run only: nothing was pushed. Run again with --push to push branch $BRANCH."
fi
