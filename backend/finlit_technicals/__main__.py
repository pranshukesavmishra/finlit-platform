"""Command line, for checking the numbers and for the nightly batch.

  python -m finlit_technicals score SAMBHV --data ./prices --cap small        the calculation table and trend alignment
  python -m finlit_technicals peers SAMBHV --data ./prices --cap small        leader / laggard, peers, history
  python -m finlit_technicals fetch-nse --dir ./nse                          download / update NSE's daily files
  python -m finlit_technicals sectors --nse ./nse                             Sector Pulse: every NSE industry's state
  python -m finlit_technicals industry "Ferrous Metals" --nse ./nse           one industry page
  python -m finlit_technicals stock-sector SAMBHV --nse ./nse                 the stock inside its industry
  python -m finlit_technicals batch --nse ./nse --out ./site_data             every stock and industry -> JSON files
Prices come from --nse (NSE's files, kept by fetch-nse: every stock and index, delisted stocks included) or --data
(a CsvFolder: stocks/<SYMBOL>.csv, indices/<CODE>.csv). Add --json to print the JSON the website gets.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from .api import peer_label, score
from .sources import CsvFolder


def _p(x, nd=1, plus=True):
    if x is None:
        return "n/a"
    return (("+" if plus and x > 0 else "") + f"{x:.{nd}f}")


def score_text(d: dict) -> str:
    L = []
    pr = d.get("peers")
    if pr:
        L.append("VS INDUSTRY PEERS (weekly, 12 months)")
        L.append(f"  [{pr['label']}] {pr['status']}" + (f" · {pr['pending']}" if pr["pending"] else ""))
        rr = pr["relative_return_pts"]
        if pr["state"] == 0:
            L.append(f"  vs {pr['benchmarks']['sector']}: 3M {_p(rr['vs_sector_3m'])} · 6M {_p(rr['vs_sector_6m'])} · "
                     f"12M {_p(rr['vs_sector_12m'])} pts   ·   vs {pr['benchmarks']['market']}: 12M {_p(rr['vs_market_12m'])} pts")
        L += [f"  note: {n}" for n in pr["notes"]]
        L.append("")
    L.append(f"{d['symbol']} · {d['date']} · close {d['close']:,.2f} · {d['bars']} daily bars · RS benchmark {d['benchmark']}")
    for part, title in (("short_term", "SHORT-TERM"), ("long_term", "LONG-TERM")):
        s = d[part]
        L.append("")
        L.append(f"{title} SCORE = Σ weight × signal × 100 / {s['divisor']}")
        L.append(f"  {'Component':<24} {'Signal':>6} {'Wt':>3} {'Points':>6}  Reading now")
        for c in s["components"]:
            L.append(f"  {c['name']:<24} {_p(c['signal'], 2) if c['on'] else '-':>6} {c['weight']:>3} "
                     f"{_p(c['points']) if c['on'] else '-':>6}  {c['reading']}")
        L.append(f"  Raw sum {_p(s['raw'])}  × 100 / {s['divisor']}  =  {_p(s.get('uncapped', s['score']))}")
        if s.get("capped"):
            L.append(f"  Stage {s['stage']}: capped at +19 → {_p(s['score'])}")
        L.append(f"  {title} {'+' if s['display'] > 0 else ''}{s['display']}  {s['rating']}")
    v = d["trend_alignment"]
    L.append("")
    L.append(f"TREND ALIGNMENT  {v['label']}")
    L.append(f"  {v['how']}")
    for sb in ("Positive", "Neutral", "Negative"):
        row = [c for c in v["cells"] if c["st_band"] == sb]
        mark = "▶" if any(c["current"] for c in row) else " "
        L.append(f"  {mark} Short-term {sb:<8}: " + " · ".join(f"long-term {c['lt_band']} → {c['label']}" for c in row))
    L += [f"  note: {n}" for n in d["notes"]]
    L.append(d["disclaimer"])
    return "\n".join(L)


def peers_text(d: dict) -> str:
    L = [f"[{d['label']}] {d['symbol']} · {d['status']}"]
    if d["pending"]:
        L.append(f"  {d['pending']}")
    rr = d["relative_return_pts"]
    if d["state"] == 0:
        L.append(f"  vs {d['benchmarks']['sector']}: 3M {_p(rr['vs_sector_3m'])} · 6M {_p(rr['vs_sector_6m'])} · "
                 f"12M {_p(rr['vs_sector_12m'])} pts   ·   vs {d['benchmarks']['market']}: 12M {_p(rr['vs_market_12m'])} pts")
    c = d["runs_last_52"]
    L.append(f"  {('Label since ' + d['since'] + '. ') if d['since'] else ''}Last {c['runs']} weekly runs: "
             f"Leader {c['leader']} · In line {c['in_line']} · Laggard {c['laggard']}")
    L.append(f"  Held here? {d['reliability']}")
    L += [f"  note: {n}" for n in d["notes"]]
    if d.get("table") is not None:
        L.append("")
        L.append(f"Peers · {d['group']['name']} · vs {d['benchmarks']['sector']} · week of {d['week_ranked']}")
        L.append(f"  {'#':>3}  {'Stock':<12} {'Status':<24} {'vs sector 12M':>13} {'3M':>8} {'vs market 12M':>13}")
        for t in d["table"]:
            st = t["status"] + (f" ({t['this_week']} this wk)" if t["status"] != t["this_week"] else "")
            L.append(f"  {t['rank']:>3}  {t['symbol'] + (' ◀' if t['is_self'] else ''):<12} {st:<24} "
                     f"{_p(t['vs_sector_12m']):>13} {_p(t['vs_sector_3m']):>8} {_p(t['vs_market_12m']):>13}")
        if d["table_more"]:
            L.append(f"  … {d['table_more']} more")
        for x in d["not_ranked"]:
            L.append(f"    –  {x['symbol']:<12} not ranked: {x['reason']}")
    if d.get("history"):
        L.append("")
        L.append("  Week ranked   Label     Rank     vs sector 12M  vs market 12M")
        for h in d["history"]:
            rk = f"{h['rank']}/{h['ranked']}" if h["rank"] else "-"
            L.append(f"  {h['week']}    {h['label']:<8}  {rk:<7}  {_p(h['vs_sector_12m']):>13}  {_p(h['vs_market_12m']):>13}")
    L.append(d["disclaimer"])
    return "\n".join(L)


def _row_line(r: dict) -> str:
    b = r["breadth"]
    t = r["last_thrust"]
    tt = f"{t['type']} {t['sessions_ago']} sessions ago" if t else "-"
    return (f"  {r['name'][:34]:<34} {r['state']:<10} {_p(b['above_9'], 0, False):>4}% {_p(b['above_20'], 0, False):>4}% "
            f"{_p(b['above_50'], 0, False):>4}%  {_p(r['index_vs_52w_high']):>6}%  {_p(r['higher_low_share'], 0, False):>4}  "
            f"{tt:<22} {r['leader_flags'] or '-':>3}")


def board_text(d: dict) -> str:
    L = [f"SECTOR PULSE · {d['date']} · {d['groups']} groups ({d['industries']} NSE industries), {d['stocks_counted']} stocks counted",
         "  " + " · ".join(f"{k} {v}" for k, v in d["counts"].items())]
    if d.get("market"):
        m = d["market"]
        L.append(f"  Nifty 50 {m['nifty50']:,.2f}, {_p(m['pct_vs_200d'])}% vs its 200-day average. {m['note']}")
    if d["market_note"]:
        L.append(f"  {d['market_note']}")
    L.append("")
    L.append(f"  {'Group':<34} {'State':<10} {'>9d':>5} {'>20d':>5} {'>50d':>5}  {'vs high':>7}  {'HL%':>4}  {'Last thrust':<22} {'Flg':>3}")
    L += [_row_line(r) for r in d["rows"]]
    if d["leader_flags"]:
        L.append("")
        L.append(f"LEADER FLAGS ({len(d['leader_flags'])} live)")
        for f in d["leader_flags"]:
            L.append(f"  {f['symbol']:<12} {f['group'][:34]:<34} tier {f['tier']:<7} {f['sessions_ago']:>2} sessions ago"
                     + ("  · new today" if f["new_today"] else ""))
    if d.get("too_few_stocks"):
        L.append("")
        L.append("  Too few counted stocks to read: " + ", ".join(f"{x['name']} ({x['stocks_counted']})" for x in d["too_few_stocks"]))
    L.append(d["disclaimer"])
    return "\n".join(L)


def industry_text(d: dict) -> str:
    b = d["breadth"]
    kind = "" if d["kind"] == "industry" else f" (NSE sector group: {', '.join(d['industries'])})"
    L = [f"{d['name'].upper()}{kind} · {d['state']} since {d['since']} · {d['stocks_counted']} stocks counted · {d['date']}", "",
         d["summary"], "",
         f"  Breadth today: {_p(b['above_9'], 0, False)}% / {_p(b['above_20'], 0, False)}% / {_p(b['above_50'], 0, False)}% above the 9 / 20 / 50-day average"
         f" (lowest 50-day reading in 30 sessions: {_p(b['lowest_50_last_30'], 0, False)}%)",
         f"  Index vs 52-week high: {_p(d['index_vs_52w_high'])}%   Higher-low share: {_p(d['higher_low_share'], 0, False)}%",
         f"  Last 60-day low: {d['last_60d_low']['sessions_ago']} sessions ago ({d['last_60d_low']['date']})" if d["last_60d_low"] else "  Last 60-day low: -",
         f"  Last thrust: {d['last_thrust']['type']} on {d['last_thrust']['date']} ({d['last_thrust']['sessions_ago']} sessions ago)" if d["last_thrust"] else "  Last thrust: none",
         "", "  States over the period: " + " → ".join(f"{x['state']} ({x['from']})" for x in d["bands"][-6:]),
         "", f"  Study: {d['study']['state']}" if d["study"]["state"] else "", ""]
    L.append(f"  {'#':>3} {'Stock':<12} {'6M':>7}  {'Quarter':<15} {'Leader flag':<12} Bottom timing")
    for s in d["stocks"]:
        fl = s["leader_flag"]["tier"] if s["leader_flag"] else "-"
        L.append(f"  {s['rank_6m'] or '-':>3} {s['symbol']:<12} {_p(s['return_6m_pct']):>6}%  {s['quarter_name'] or '-':<15} {fl:<12} {s['bottom']}")
    if d["leader_flag_note"]:
        L.append(f"  {d['leader_flag_note']}")
    if d.get("not_counted"):
        L.append("")
        L.append(f"  Not counted ({len(d['not_counted'])}):")
        for x in d["not_counted"][:15]:
            L.append(f"    {x['symbol']:<12} {'; '.join(x['not_counted_because'])}")
        if len(d["not_counted"]) > 15:
            L.append(f"    … {len(d['not_counted']) - 15} more")
    L.append(d["disclaimer"])
    return "\n".join(x for x in L if x is not None)


def stock_sector_text(d: dict) -> str:
    g = d["group"]
    L = [f"{d['symbol']} · NSE industry {d['industry']} · read in {g['name']} · {g['state']} · {g['date']}", "  " + g["summary"]]
    if d["in_group"]:
        L += [f"  6-month return: {_p(d['return_6m_pct'])}% · {d['rank_6m']} of {d['ranked_6m']} · {d['quarter_name']}",
              f"  {d['bottom']}", f"  {d['leader_flag_text']}"]
    else:
        L.append(f"  {d['note']}")
    L.append(d["disclaimer"])
    return "\n".join(L)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "fetch-nse":
        from .fetch import main as fetch_main
        return fetch_main(argv[1:])
    ap = argparse.ArgumentParser(prog="finlit_technicals", description="ST/LT scores and leader / laggard vs peers")
    ap.add_argument("command", choices=["score", "peers", "sectors", "industry", "stock-sector", "batch", "fetch-nse"])
    ap.add_argument("symbol", nargs="?", help="stock symbol, or the industry name for `industry` (quote names with spaces)")
    ap.add_argument("--data", help="price folder: stocks/<SYMBOL>.csv and indices/<CODE>.csv")
    ap.add_argument("--nse", help="NSE folder kept by fetch-nse (bhav_<year>.csv.gz, idx_<year>.csv.gz, ref/, amfi/)")
    ap.add_argument("--mcap", type=float, help="the stock's market cap, Rs crore")
    ap.add_argument("--cap", choices=["large", "mid", "small"])
    ap.add_argument("--bench", default="auto", choices=["auto", "nifty500", "nifty50", "midcap100", "smallcap100"])
    ap.add_argument("--industry")
    ap.add_argument("--sector")
    ap.add_argument("--peers", dest="peer_list", help="your own peer list, comma separated")
    ap.add_argument("--group", choices=["auto", "it", "pharma", "pvtbank", "psubank", "autosector", "industry", "sector", "custom"])
    ap.add_argument("--no-peers", action="store_true", help="score: skip the peer row")
    ap.add_argument("--all", action="store_true", help="peers: every ranked peer in the table")
    ap.add_argument("--weeks", type=int, default=12, help="peers: weekly runs to show")
    ap.add_argument("--json", action="store_true", help="print the JSON the website gets")
    ap.add_argument("--out", help="batch: output folder")
    ap.add_argument("--symbols", help="batch: comma-separated symbols (default: with --nse every classified stock "
                    "that traded on the last day, else every stock in the peer lists)")
    ap.add_argument("--caps", help="batch: CSV with symbol, mcap_cr and/or cap")
    ap.add_argument("--no-sectors", action="store_true", help="batch: skip the sector pages")
    ap.add_argument("--sessions", type=int, default=260, help="industry: sessions of breadth history")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not (a.data or a.nse):
        print("give the prices: --nse NSE_FOLDER (see fetch-nse) or --data PRICE_FOLDER")
        return 2
    if a.nse:
        from .nse import NseHistory
        src = NseHistory(a.nse)
    else:
        src = CsvFolder(a.data)
    if a.command == "batch":
        from .batch import read_caps, run, universe
        if not a.out:
            print("batch needs --out")
            return 2
        if a.symbols:
            syms = [s.strip() for s in a.symbols.split(",") if s.strip()]
        elif a.nse and not a.no_sectors:
            from .batch import nse_symbols
            from .sectors import SectorEngine
            syms = nse_symbols(SectorEngine(src))
        else:
            syms = universe()
        caps = read_caps(a.caps) if a.caps else None
        res = run(syms, src, a.out, caps=caps, bench=a.bench, sectors=not a.no_sectors,
                  progress=lambda i, n, s: print(f"{i}/{n} {s}", file=sys.stderr) if i % 100 == 0 or i == n else None)
        bad = [x for x in res if "error" in x]
        print(f"{len(res) - len(bad)} stocks written to {a.out}, {len(bad)} with errors (see _summary.json)")
        return 0
    if a.command in ("sectors", "industry", "stock-sector"):
        from .sectors import SectorEngine
        eng = SectorEngine(src)
        try:
            if a.command == "sectors":
                d = eng.board()
                print(json.dumps(d, indent=1, ensure_ascii=False) if a.json else board_text(d))
                return 0
            if not a.symbol:
                print(f"usage: {a.command} {'INDUSTRY' if a.command == 'industry' else 'SYMBOL'} --nse FOLDER")
                return 2
            if a.command == "industry":
                d = eng.industry(a.symbol, history_sessions=a.sessions)
                print(json.dumps(d, indent=1, ensure_ascii=False) if a.json else industry_text(d))
            else:
                d = eng.stock(a.symbol)
                print(json.dumps(d, indent=1, ensure_ascii=False) if a.json else stock_sector_text(d))
        except LookupError as e:
            print(str(e))
            return 2
        return 0
    if not a.symbol:
        print(f"usage: {a.command} SYMBOL --nse FOLDER (or --data FOLDER)")
        return 2
    kw = dict(market_cap_cr=a.mcap, cap=a.cap, industry=a.industry, sector=a.sector, peer_list=a.peer_list, group=a.group)
    try:
        if a.command == "score":
            d = score(a.symbol, src, bench=a.bench, peers=not a.no_peers, **kw)
            print(json.dumps(d, indent=1, ensure_ascii=False) if a.json else score_text(d))
        else:
            d = peer_label(a.symbol, src, table="all" if a.all else "top10", history_weeks=a.weeks, **kw)
            print(json.dumps(d, indent=1, ensure_ascii=False) if a.json else peers_text(d))
    except (LookupError, ValueError) as e:
        print(str(e))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
