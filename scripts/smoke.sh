#!/usr/bin/env bash
# Post-deploy smoke test: scripts/smoke.sh <base-url>   e.g. scripts/smoke.sh https://finlit-arug.onrender.com
# Prints PASS/FAIL per check; exits 1 if any failed. Read-only GETs, a few dozen small requests (free-tier friendly).
# Env: MAX_UPDATING_PCT (default 50) share of "report being updated" allowed on the latest declared day that is at least 1 day old;
#      SMALLCAP (default SBFC) a small company that must show a price and a score; MIN_TOTAL (5000) companies in the screener catalog.
set -uo pipefail
BASE="${1:-}"; BASE="${BASE%/}"
[ -n "$BASE" ] || { echo "usage: $0 <base-url>" >&2; exit 2; }
MAX_UPDATING_PCT="${MAX_UPDATING_PCT:-50}"; SMALLCAP="${SMALLCAP:-SBFC}"; MIN_TOTAL="${MIN_TOTAL:-5000}"
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILS=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; FAILS=$((FAILS + 1)); }

# get <path> -> body in $TMP/body, status in $CODE. Waits for a sleeping free instance (up to ~2 min for the first request).
get() {
  CODE=000
  for i in 1 2 3 4; do
    CODE="$(curl -sS -o "$TMP/body" -w '%{http_code}' --max-time 60 -H 'Accept: application/json' "$BASE$1" 2>/dev/null || echo 000)"
    case "$CODE" in 2*|3*|4*) return 0 ;; esac
    sleep $((i * 8))
  done
}
js() { python3 -c "import json,sys
try:
    d=json.load(open('$TMP/body'))
except Exception:
    sys.exit(3)
$1"; }

get /api/health
if [ "$CODE" = 200 ] && js "sys.exit(0 if d.get('ok') is True else 1)"; then pass "/api/health ok"; else fail "/api/health -> HTTP $CODE $(head -c 120 "$TMP/body" 2>/dev/null)"; fi

get /;           [ "$CODE" = 200 ] && pass "home page 200" || fail "home page -> HTTP $CODE"

get /api/screener/catalog
if [ "$CODE" = 200 ] && out="$(js "t,w=d.get('total',0),d.get('withReport',0)
print(t,w)
sys.exit(0 if t>$MIN_TOTAL and 0<=w<=t else 1)")"; then pass "screener catalog total/withReport = $out"; else fail "screener catalog (HTTP $CODE, ${out:-unreadable}; need total > $MIN_TOTAL)"; fi

stock() {  # stock <SYMBOL>: a price and a score (a company still loading answers 202: retry)
  local s="$1" n
  for n in 1 2 3 4 5 6; do
    get "/api/stocks/$s"
    [ "$CODE" = 200 ] && break
    sleep 5
  done
  if [ "$CODE" = 200 ] && out="$(js "q=(d.get('quote') or {}).get('price'); o=(d.get('score') or {}).get('overall')
print('price',q,'score',o)
sys.exit(0 if (q or 0)>0 and o is not None else 1)")"; then pass "$s summary: $out"; else fail "$s summary lacks a price or a score (HTTP $CODE ${out:-})"; fi
}
stock RELIANCE
stock "$SMALLCAP"

get /api/results/quarter
if [ "$CODE" = 200 ]; then
  day="$(js "import datetime
t=d.get('today') or datetime.date.today().isoformat()
days=[x['date'] for x in d.get('days',[]) if x['date']<t]
print(max(days) if days else '')")"
  if [ -n "$day" ]; then
    get "/api/results/quarter?date=$day&limit=1"
    if out="$(js "s=d.get('summary') or {}
c,a=s.get('companies',0),s.get('awaiting',0)
pct=100*a/c if c else 0
print('%s: %d of %d being updated (%.0f%%)'%('$day',a,c,pct))
sys.exit(0 if pct<=$MAX_UPDATING_PCT else 1)")"; then pass "results $out (limit $MAX_UPDATING_PCT%)"; else fail "results ${out:-unreadable} (limit $MAX_UPDATING_PCT%)"; fi
  else pass "results: no declared day older than today yet (nothing to check)"; fi
else fail "quarter results -> HTTP $CODE"; fi

for path in /etfs /funds; do get "$path"; [ "$CODE" = 200 ] && pass "$path 200" || fail "$path -> HTTP $CODE"; done

get "/api/forum/threads?per=5"
if [ "$CODE" = 200 ] && js "sys.exit(0 if isinstance(d,(dict,list)) else 1)"; then pass "forum threads 200"; else fail "forum threads -> HTTP $CODE"; fi

get /glossary
GL="$HERE/../frontend/src/content/glossary.json"
if [ "$CODE" = 200 ]; then
  if [ -f "$GL" ]; then
    n="$(python3 -c "import json;print(len(json.load(open('$GL'))['terms']))")"
    [ "$n" -gt 300 ] && pass "glossary page 200, $n terms in the shipped glossary" || fail "glossary has only $n terms (need > 300)"
  else pass "glossary page 200 (term count not checked: glossary.json not in this checkout)"; fi
else fail "glossary -> HTTP $CODE"; fi

echo "----"
[ "$FAILS" = 0 ] && { echo "SMOKE PASS ($BASE)"; exit 0; } || { echo "SMOKE FAIL: $FAILS check(s) failed ($BASE)"; exit 1; }
