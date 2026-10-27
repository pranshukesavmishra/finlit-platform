#!/usr/bin/env bash
# Checks a running FinLit MCP server over plain HTTP: initialize, tools/list, get_stock_quote, search_stocks (and the 405 on GET).
# Usage: scripts/mcp-check.sh <base-url> [SYMBOL] [SEARCH TEXT]      e.g. scripts/mcp-check.sh https://finlitventures.com RELIANCE reli
# Needs curl and python3. Prints PASS or FAIL for each step with the real values; exits 1 if any step failed. Sends no key and no cookie.
set -u
BASE="${1:-}"; SYMBOL="${2:-RELIANCE}"; QUERY="${3:-reli}"
if [ -z "$BASE" ]; then echo "usage: $0 <base-url> [SYMBOL] [SEARCH TEXT]" >&2; exit 2; fi
BASE="${BASE%/}"; URL="$BASE/mcp"; FAILS=0; TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
post() { curl -sS --max-time 40 -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -H 'MCP-Protocol-Version: 2025-06-18' -d "$1" -o "$TMP" -w '%{http_code}' "$URL" 2>"$TMP.err" || echo "000"; }
pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; FAILS=$((FAILS + 1)); }
# py <code>: runs python on the saved response ($TMP) and prints what the code prints; the code gets the parsed JSON in `r`
py() { python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); '"$1" "$TMP" 2>&1; }

echo "FinLit MCP check: $URL"

code="$(post '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"mcp-check","version":"1"}}}')"
out="$(py 'x=r["result"]; print(x["serverInfo"]["name"], x["serverInfo"]["version"], "protocol", x["protocolVersion"])')"
if [ "$code" = 200 ] && [ "${out#finlit }" != "$out" ]; then pass "initialize (HTTP $code): $out"; else fail "initialize (HTTP $code): ${out:-no answer} $(head -c 200 "$TMP.err" 2>/dev/null)"; fi

code="$(post '{"jsonrpc":"2.0","id":2,"method":"tools/list"}')"
out="$(py 't=r["result"]["tools"]; names=[x["name"] for x in t]; ro=all(x.get("annotations",{}).get("readOnlyHint") for x in t); assert "get_stock_quote" in names and "search_stocks" in names and ro; print(len(t), "tools, all read-only:", ", ".join(names))')"
if [ "$code" = 200 ] && echo "$out" | grep -q "tools, all read-only"; then pass "tools/list (HTTP $code): $out"; else fail "tools/list (HTTP $code): ${out:-no answer}"; fi

code="$(post "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"get_stock_quote\",\"arguments\":{\"symbol\":\"$SYMBOL\"}}}")"
out="$(py 'x=r["result"]; assert not x["isError"], x["content"][0]["text"]; s=x["structuredContent"]; q=s["data"]["quote"]; assert q and q.get("price") is not None and s["disclaimer"] and "source" in s and "asOf" in s; print("%s %s: price %s, change %s%%, volume %s, asOf %s, source: %s" % (s["data"]["symbol"], s["data"]["name"], q["price"], q["changePct"], q["volume"], s["asOf"], s["source"][:60]))')"
if [ "$code" = 200 ] && echo "$out" | grep -q "price "; then pass "get_stock_quote $SYMBOL (HTTP $code): $out"; else fail "get_stock_quote $SYMBOL (HTTP $code): ${out:-no answer}"; fi

code="$(post "{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"tools/call\",\"params\":{\"name\":\"search_stocks\",\"arguments\":{\"query\":\"$QUERY\",\"limit\":3}}}")"
out="$(py 'x=r["result"]; assert not x["isError"], x["content"][0]["text"]; s=x["structuredContent"]; c=s["data"]["companies"]; assert c, "no company matched"; assert s["disclaimer"] and "asOf" in s; print("%d match(es), first: %s" % (s["data"]["matches"], "; ".join("%s (%s)" % (i["symbol"], i["name"]) for i in c)))')"
if [ "$code" = 200 ] && echo "$out" | grep -q "match(es)"; then pass "search_stocks '$QUERY' (HTTP $code): $out"; else fail "search_stocks '$QUERY' (HTTP $code): ${out:-no answer}"; fi

code="$(curl -sS --max-time 20 -H 'Accept: text/event-stream' -o /dev/null -D "$TMP.h" -w '%{http_code}' "$URL" 2>/dev/null || echo 000)"
allow="$(grep -i '^allow:' "$TMP.h" 2>/dev/null | tr -d '\r' | head -1)"
if [ "$code" = 405 ] && echo "$allow" | grep -qi 'POST'; then pass "GET /mcp is refused (HTTP 405, $allow)"; else fail "GET /mcp expected 405 with Allow: POST, got HTTP $code ${allow:-}"; fi
rm -f "$TMP.h" "$TMP.err"

if [ "$FAILS" -eq 0 ]; then echo "ALL PASS"; else echo "$FAILS step(s) FAILED"; exit 1; fi
