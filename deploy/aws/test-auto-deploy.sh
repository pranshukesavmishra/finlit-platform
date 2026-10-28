#!/usr/bin/env bash
# Tests auto-deploy.sh with a fake repository and a fake deploy.sh (no docker, no network). Run:  bash deploy/aws/test-auto-deploy.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export FINLIT_HOME="$T/home"; mkdir -p "$FINLIT_HOME/src/sub/deploy/aws"
ORIGIN="$T/origin.git"; git init -q --bare "$ORIGIN"
W="$T/work"; git clone -q "$ORIGIN" "$W" 2>/dev/null; git -C "$W" checkout -q -b main
commit() { echo "$1" > "$W/f.txt"; git -C "$W" add f.txt; git -C "$W" -c user.name=t -c user.email=t@t commit -q -m "$1"; git -C "$W" push -q origin main 2>/dev/null; }
commit one
printf 'REPO_URL=%s\nREPO_BRANCH=main\nREPO_SUBDIR=sub\n' "$ORIGIN" > "$FINLIT_HOME/auto-deploy.conf"
# a fake deploy.sh: records what it was asked, and acts as FAKE_MODE says
echo imgA > "$T/image"; : > "$T/calls"
cat > "$FINLIT_HOME/src/sub/deploy/aws/deploy.sh" <<FAKE
#!/usr/bin/env bash
echo "\$1" >> "$T/calls"
case "\$1" in
  backup) exit 0 ;;
  rollback) echo imgA > "$T/image"; exit 0 ;;
  deploy) case "\${FAKE_MODE:-ok}" in
            ok) echo imgB > "$T/image"; exit 0 ;;
            unhealthy) echo imgC > "$T/image"; exit 1 ;;
            early) exit 1 ;;
          esac ;;
esac
FAKE
export DEPLOY_SH="$FINLIT_HOME/src/sub/deploy/aws/deploy.sh" IMAGE_ID_CMD="cat $T/image"
A="$HERE/auto-deploy.sh"
fail=0; ok() { if [ "$2" = "$3" ]; then echo "PASS  $1"; else echo "FAIL  $1 (wanted '$2', got '$3')"; fail=1; fi; }
calls() { tr '\n' ' ' < "$T/calls" | sed 's/ $//'; }
reset() { : > "$T/calls"; }

# 1. nothing deployed yet and the checkout is not at the remote commit: the first run deploys
FAKE_MODE=ok bash "$A" >/dev/null 2>&1;            ok "first new commit is deployed (backup, then deploy)" "backup deploy" "$(calls)"
ok "the deployed commit is recorded" "$(git -C "$W" rev-parse HEAD)" "$(cat "$FINLIT_HOME/state/auto_deployed_sha")"
reset; bash "$A" >/dev/null 2>&1;                  ok "no change: nothing runs" "" "$(calls)"
# 2. a new commit that fails before replacing the build: no rollback, never retried
commit two; reset; FAKE_MODE=early bash "$A" >/dev/null 2>&1; rc=$?
ok "early failure: backup and deploy, no rollback" "backup deploy" "$(calls)"
ok "early failure exits non-zero" "1" "$rc"
reset; FAKE_MODE=ok bash "$A" >/dev/null 2>&1;     ok "the failed commit is not tried again" "" "$(calls)"
# 3. a newer commit is tried; this one starts and is unhealthy: rolled back
commit three; reset; echo imgA > "$T/image"; FAKE_MODE=unhealthy bash "$A" >/dev/null 2>&1
ok "unhealthy new build is rolled back" "backup deploy rollback" "$(calls)"
ok "the image is the old one again" "imgA" "$(cat "$T/image")"
reset; FAKE_MODE=ok bash "$A" >/dev/null 2>&1;     ok "a rolled-back commit is not retried" "" "$(calls)"
# 4. pause stops everything, resume continues
commit four; reset; bash "$A" pause >/dev/null 2>&1; FAKE_MODE=ok bash "$A" >/dev/null 2>&1
ok "paused: nothing deployed" "" "$(calls)"
bash "$A" resume >/dev/null 2>&1; FAKE_MODE=ok bash "$A" >/dev/null 2>&1
ok "resumed: the waiting commit is deployed" "backup deploy" "$(calls)"
ok "failed marker cleared after a success" "none" "$(cat "$FINLIT_HOME/state/auto_failed_sha" 2>/dev/null || echo none)"
# 5. an unreachable repository does nothing and does not fail
printf 'REPO_URL=%s\nREPO_BRANCH=main\nREPO_SUBDIR=sub\n' "$T/missing.git" > "$FINLIT_HOME/auto-deploy.conf"
commit five; reset; bash "$A" >/dev/null 2>&1; rc=$?
ok "unreachable repository: no deploy, exit 0" "0 " "$rc $(calls)"
# 6. two checks at once: the second one leaves quietly
printf 'REPO_URL=%s\nREPO_BRANCH=main\nREPO_SUBDIR=sub\n' "$ORIGIN" > "$FINLIT_HOME/auto-deploy.conf"
exec 8>"$FINLIT_HOME/state/auto_deploy.lock"; flock -n 8; reset; bash "$A" >/dev/null 2>&1
ok "a check is already running: nothing runs" "" "$(calls)"
exit $fail
