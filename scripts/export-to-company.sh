#!/usr/bin/env bash
# Puts a snapshot of this repository on a NEW branch of the company's repository, inside one folder, so nothing of theirs is overwritten.
#
#   scripts/export-to-company.sh              # dry run: builds the branch in a temporary clone and shows what it would push
#   scripts/export-to-company.sh --push       # the same, then pushes branch "Pranshu"
#
# Environment:  COMPANY_REMOTE (default https://github.com/Yusra-Khan532/Financial-Portfolio.git)
#               BRANCH (default Pranshu)   FOLDER (default finlit-platform)   BASE (default: the company's default branch)
# It needs git access to the company repository (your GitHub login or a token with write access there; never paste a token into a chat).
# It exports only files tracked by git in this repository (no history, no untracked files, no .env), and refuses to push if the
# exported tree contains anything that looks like a secret.
set -euo pipefail
REMOTE="${COMPANY_REMOTE:-https://github.com/Yusra-Khan532/Financial-Portfolio.git}"
BRANCH="${BRANCH:-Pranshu}"
FOLDER="${FOLDER:-finlit-platform}"
PUSH=0; [ "${1:-}" = "--push" ] && PUSH=1
SRC="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

[ -z "$(git -C "$SRC" status --porcelain)" ] || { echo "Commit or stash your changes first: the export uses what is committed (HEAD)." >&2; exit 1; }
HEAD_SHA="$(git -C "$SRC" rev-parse --short HEAD)"

echo "1/5 cloning the company repository ($REMOTE)"
git clone -q "$REMOTE" "$WORK/company"
cd "$WORK/company"
BASE="${BASE:-$(git symbolic-ref --short HEAD)}"
git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1 && { echo "Branch $BRANCH already exists on the company repository: choose another BRANCH." >&2; exit 1; }
git checkout -q -b "$BRANCH" "origin/$BASE"
[ ! -e "$FOLDER" ] || { echo "Folder $FOLDER already exists on $BASE: choose another FOLDER." >&2; exit 1; }

echo "2/5 exporting tracked files of $HEAD_SHA into $FOLDER/"
mkdir "$FOLDER"
git -C "$SRC" archive HEAD | tar -x -C "$FOLDER"

echo "3/5 checking the export for secrets"
BAD=0
if grep -rIlE '(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[abp]-[0-9A-Za-z-]{10,}|ghp_[0-9A-Za-z]{30,}|sk-[A-Za-z0-9]{32,}|mongodb\+srv://[^ "<]+:[^ "<@]+@|postgres(ql)?://[^ "<:]+:[^ "<@$]{12,}@[^ "<]*(neon|aws|render))' "$FOLDER" --exclude-dir=node_modules >"$WORK/hits.txt" 2>/dev/null; then BAD=1; fi
if find "$FOLDER" -name ".env" -o -name "*.pem" -o -name "*.key" | grep -q .; then BAD=1; find "$FOLDER" -name ".env" -o -name "*.pem" -o -name "*.key" >>"$WORK/hits.txt"; fi
if [ "$BAD" = 1 ]; then echo "STOP: possible secrets in the export:" >&2; cat "$WORK/hits.txt" >&2; exit 1; fi

echo "4/5 committing"
git add -A
git -c user.name="${GIT_AUTHOR_NAME:-$(git -C "$SRC" config user.name || echo Pranshu)}" -c user.email="${GIT_AUTHOR_EMAIL:-$(git -C "$SRC" config user.email || echo pranshu@users.noreply.github.com)}" \
  commit -q -m "Add the FinLit platform (research service, website, Prism updates) as $FOLDER/ - snapshot of pranshukesavmishra/finlit-platform at $HEAD_SHA" \
  -m "Nothing outside $FOLDER/ is changed. See $FOLDER/docs/COMPANY-HANDOVER.md for the structure, how it maps to this repository and the changes needed to merge."
git show --stat --oneline HEAD | tail -3
echo "files in $FOLDER/: $(find "$FOLDER" -type f | wc -l)"

if [ "$PUSH" = 1 ]; then
  echo "5/5 pushing $BRANCH"
  git push -u origin "$BRANCH"
  echo "Done. Open a pull request from $BRANCH on GitHub."
else
  echo "5/5 dry run only: nothing was pushed. Run again with --push to push branch $BRANCH."
fi
