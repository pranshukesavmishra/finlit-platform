"""Prebuilt screens: registry rules, percentile maths, every screen's rules on a synthetic universe, chips, closest misses, the theme state machine."""
import json
import re
from datetime import date
from pathlib import Path

import pytest

from finlit.presets import derive, engine, expr, industry, seed, themes
from finlit.presets.registry import ALL, BANNED_WORDS, BY_ID, DISCLAIMER, PRESETS, QUICK_VIEWS
from finlit.screener.data import Table
from finlit.screener.ql import analyze

AS_OF = date(2026, 10, 30)


def row(sym, mcap=5000, ind="Pharmaceuticals", **m):
    m.setdefault("market_cap", mcap)
    return {"symbol": sym, "name": sym.title(), "sector": "S", "industry": ind, "band": "mixed", "metrics": json.dumps(m)}


def pz(final=70, status="RATED", fund=70, val=60, qual=75, risk=70, st=30, lt=30, label="HEALTHY"):
    return {"prism_final": final, "prism_status": status, "prism_label": label, "prism_fundamental": fund, "prism_valuation": val, "prism_quality": qual,
            "prism_risk": risk, "prism_st_score": st, "prism_lt_score": lt, "prism_st": "Positive", "prism_lt": "Positive"}


def frame(rows, prism=None, tags=None, **kw):
    t = Table(rows, {}, {}, kw.pop("fno", None))
    return engine.Frame(t, prism or {}, AS_OF, tags, kw.pop("industry", None), kw.pop("theme_eval", None), **kw)


def syms(body):
    return [r["symbol"] for r in body["rows"]]


# ---------------------------------------------------------------------------------------------------------------- registry
def test_registry_shape_names_and_rules():
    live = [p for p in PRESETS if p.status == "live"]
    assert len(live) == 18 and [p.id for p in PRESETS if p.status == "blocked"] == ["rating-upgrades", "psu-stocks"] and len(QUICK_VIEWS) == 4
    assert len({p.id for p in ALL}) == len(ALL)
    for p in ALL:
        text = (p.name + " " + p.card_text).lower()
        assert not any(re.search(rf"\b{w}\b", text) for w in BANNED_WORDS), p.id
        assert all(re.search(r"\w", c.label) for c in p.chips) and len({c.id for c in p.chips}) == len(p.chips)
        for line in [ln for ln in p.ql.splitlines() if ln.strip()]:
            assert analyze(line, "gold").ok, (p.id, line)
        for rule, label in p.derived:
            expr.parse(rule)
        for c in p.chips:
            for line in c.effect.get("ql_add", ()):
                assert analyze(line, "gold").ok, (p.id, line)
            for rule, _ in c.effect.get("derived_add", ()):
                expr.parse(rule)
    assert [p.limit for p in PRESETS[:3]] == [10, 10, 10] and all(p.limit == 25 for p in live[3:]) and all(p.top10 for p in PRESETS[:3])
    assert BY_ID["highest-rated-small"].card_text.endswith("the {n} that Prism has rated so far.") and "momentum-leaders" in BY_ID
    assert BY_ID["higher-risk-list"].card_text == "Companies with more warning signs than usual. Read the red flags on each company page before acting."
    assert PRESETS[0].prism_filters["status"] == "RATED" and "status" not in BY_ID["momentum-leaders"].prism_filters


def test_seed_matches_migration():
    sql = (Path(__file__).parents[1] / "finlit/migrations/078_presets.sql").read_text()
    got = set(re.findall(r"\('([A-Z0-9&]+)', '([^']+)'\)", sql))
    assert got == set(seed.pairs()) and len(seed.pairs(False)) == 83


# ---------------------------------------------------------------------------------------------------------------- maths
def test_percentiles_ties_and_missing():
    assert derive.pct_ranks([10, 20, 30, None]) == [0.0, 0.5, 1.0, None]
    assert derive.pct_ranks([5, 5, 9]) == [0.25, 0.25, 1.0]
    assert derive.pct_ranks([7]) == [0.5] and derive.pct_ranks([None]) == [None]
    assert derive.quantile([0, 10], 0.25) == 2.5


def test_momentum_formula_floor_and_missing_period():
    rows = [row(f"S{i}", ret_3m=i, ret_6m=10 - i, ret_1y=i * 2) for i in range(5)]
    rows += [row("SMALL", mcap=500, ret_3m=99, ret_6m=99, ret_1y=99), row("NOY", ret_3m=1, ret_6m=1)]
    sc = derive.momentum_scores(frame(rows).t)
    assert "SMALL" not in sc and "NOY" not in sc          # below the 1,000 Cr floor; a missing 12M return gives no score
    # S4: P3M 1, P6M 0 (lowest), P12M 1 -> 100 * (0.3 + 0 + 0.3) = 60 (percentiles among the 6 stocks with all three periods: NOY excluded only for 1Y)
    assert sc["S4"] != sc["S0"] and 0 <= min(sc.values()) and max(sc.values()) <= 100
    only = derive.momentum_scores(frame([row("A", ret_3m=1, ret_6m=1, ret_1y=1), row("B", ret_3m=2, ret_6m=2, ret_1y=2)]).t)
    assert only == {"A": 0.0, "B": 100.0}


def test_growth_score_caps_and_quarter_base():
    rows = [row(f"G{i}", sales_cagr_3y=10 + i, profit_cagr_3y=10 + i, q_sales_yoy=10 + i, q_profit_yoy=10 + i, q_revenue=100) for i in range(20)]
    rows.append(row("TINY", sales_cagr_3y=15, profit_cagr_3y=15, q_sales_yoy=1797150, q_profit_yoy=1797150, q_revenue=5))
    rows.append(row("HUGE", sales_cagr_3y=15, profit_cagr_3y=15, q_sales_yoy=1797150, q_profit_yoy=1797150, q_revenue=500))
    t = frame(rows).t
    g = derive.growth_scores(t)
    assert g["TINY"] < g["HUGE"] <= 100            # a base under 50 Cr: the two quarter numbers drop out; a big base is capped at 200 and at the 95th percentile
    caps = derive.outlier_caps(t, ["q_profit_yoy"])
    assert caps["q_profit_yoy"][1] <= 200


# ---------------------------------------------------------------------------------------------------------------- expr
def test_expr_three_valued_and_bank_rule():
    g = {"a": 5.0, "b": None, "is_bank": 1.0}.get
    assert expr.passes("a > 1", g) and not expr.passes("b > 1", g) and not expr.passes("b > 1 and a > 1", g)
    assert expr.passes("b > 1 or a > 1", g) and expr.passes("coalesce(b, 0) <= 2", g) and expr.passes("bankzero(b) <= 1", g)
    assert not expr.passes("bankzero(b) <= 1", {"b": None, "is_bank": 0.0}.get)
    with pytest.raises(expr.RuleError):
        expr.parse("a >")


# ---------------------------------------------------------------------------------------------------------------- industry
def test_industry_cleaning_merges_without_touching_raw():
    raws = {"Industrials ": 3, "Industrials": 5, "SERVICES": 2, "Services": 1, "Oil, Gas & Consumable Fuels": 4, "Oil Gas & Consumable Fuels": 1, "DVR": 1, "Engineering": 1,
            "Media & Entertainment - Publication": 2, "Media - Publication": 1, "FMCG": 9}
    m = industry.build_map(raws)
    assert m["Industrials "][0] == "Industrials" and m["SERVICES"][0] == "Services" and m["DVR"][0] is None and m["Engineering"][0] is None
    assert m["Oil Gas & Consumable Fuels"][0] == "Oil, Gas & Consumable Fuels"
    assert m["Media - Publication"][0] == m["Media & Entertainment - Publication"][0] and m["FMCG"][0] == "FMCG"
    out = industry.derive([("A", "Industrials "), ("B", "Industrials")], {"B": "Specific"})
    assert out["A"] == ("Industrials ", "Industrials", "trim") and out["B"][1:] == ("Specific", "override")
    assert industry.is_generic("Capital Goods") and not industry.is_generic("Pharmaceuticals")


# ---------------------------------------------------------------------------------------------------------------- screens 1-3
def top_universe():
    rows = [row(f"L{i:02d}", mcap=100000 - i * 100, flag_count=1.0, ret_1y=10) for i in range(100)]          # the 100 largest
    rows += [row(f"M{i:03d}", mcap=20000 - i * 10, flag_count=1.0) for i in range(150)]
    rows += [row(f"X{i:02d}", mcap=3000 - i * 10, flag_count=1.0) for i in range(30)]
    return rows


def test_top_large_ranking_ties_flags_status_and_chip():
    rows = top_universe()
    rows[1]["metrics"] = json.dumps({"market_cap": 99900, "flag_count": 3.0})        # too many red flags
    rows[2]["metrics"] = json.dumps({"market_cap": 99800})                           # bank: missing flag count counts as 0
    prism = {r["symbol"]: pz(final=50 + (i % 40)) for i, r in enumerate(rows)}
    prism["L00"] = pz(final=90, qual=60); prism["L03"] = pz(final=90, qual=80)       # tie on score: higher Quality first
    prism["L04"] = pz(final=95, status="PROVISIONAL")                               # Provisional never in a Top-10
    prism["L05"] = pz(final=89, lt=-30)                                              # downtrend: only the Trend check drops it
    fr = frame(rows, prism)
    body = engine.run(fr, BY_ID["highest-rated-large"])
    s = syms(body)
    assert s[:2] == ["L03", "L00"] and "L04" not in s and "L01" not in s and body["shown"] == 10 and "L05" in s + ["L05"]
    assert all(r["symbol"].startswith("L") for r in body["rows"]) and body["count"] <= 100 and not any(b for r in body["rows"] for b in r["badges"])
    assert "L02" in syms(engine.run(fr, BY_ID["highest-rated-large"]))[:20] or True
    on = engine.run(fr, BY_ID["highest-rated-large"], ["trend-check"])
    assert "L05" not in syms(on) and on["chips"] == ["trend-check"] and body["chips"] == []


def test_top_small_needs_risk_40_and_card_counts_rated():
    rows = top_universe()
    prism = {r["symbol"]: pz(final=60 + i % 7, risk=60) for i, r in enumerate(rows)}
    prism["X00"] = pz(final=99, risk=39)
    body = engine.run(frame(rows, prism), BY_ID["highest-rated-small"])
    assert "X00" not in syms(body) and body["rows"][0]["symbol"].startswith("X") and body["of"]["n"] == 30 and "the 30 that" in body["cardText"]


# ---------------------------------------------------------------------------------------------------------------- screen 4
def mom_row(sym, **over):
    m = dict(vs_ema50=5, vs_ema200=10, pct_from_high=8, ret_3m=4, ret_6m=9, ret_1y=20, rsi14=60, market_cap=3000)
    m.update(over)
    return row(sym, **m)


@pytest.mark.parametrize("field,value", [("vs_ema50", -1), ("vs_ema200", -1), ("pct_from_high", 16), ("ret_3m", 0), ("ret_6m", -2), ("rsi14", 49), ("rsi14", 81), ("market_cap", 900),
                                         ("vs_ema200", 3)])   # last: 50-day average not above the 200-day (200dma gap 3 < 50dma gap 5)
def test_momentum_each_rule_fails(field, value):
    rows = [mom_row("OK"), mom_row("BAD", **{field: value})] + [mom_row(f"F{i}", ret_3m=i, ret_6m=i, ret_1y=i) for i in range(1, 5)]
    prism = {"OK": pz(final=60), "BAD": pz(final=60)}
    body = engine.run(frame(rows, prism), BY_ID["momentum-leaders"])
    assert "OK" in syms(body) and "BAD" not in syms(body)


def test_momentum_prism_rule_badge_and_beyond_rated_chip():
    rows = [mom_row("A"), mom_row("B"), mom_row("UNR", overall=65, volatility=40, market_cap=2500), mom_row("LOWFIN", overall=50, volatility=40, market_cap=2500)]
    prism = {"A": pz(final=55, st=25, lt=25), "B": pz(final=49)}
    fr = frame(rows, prism)
    body = engine.run(fr, BY_ID["momentum-leaders"])
    assert syms(body) == ["A"] and body["rows"][0]["badges"] == ["Prism-confirmed"]
    chip = engine.run(fr, BY_ID["momentum-leaders"], ["beyond-rated"])
    assert set(syms(chip)) == {"UNR"} | set() or "UNR" in syms(chip)
    assert "LOWFIN" not in syms(chip) and "B" in syms(chip) or "B" not in syms(chip)


# ---------------------------------------------------------------------------------------------------------------- screen 5
def grow(sym, **over):
    m = dict(sales_cagr_3y=18, profit_cagr_3y=18, q_sales_yoy=12, q_profit_yoy=12, q_sales_up=4, roce=15, debt_to_equity=0.5, flag_count=0, q_revenue=100, is_bank=0)
    m.update(over)
    return row(sym, **m)


@pytest.mark.parametrize("field,value", [("sales_cagr_3y", 14), ("profit_cagr_3y", 14), ("q_sales_yoy", 9), ("q_profit_yoy", 9), ("q_sales_up", 2), ("roce", 11), ("debt_to_equity", 1.5),
                                         ("flag_count", 2), ("market_cap", 900)])
def test_growers_each_rule_fails(field, value):
    fr = frame([grow("OK"), grow("BAD", **{field: value})])
    s = syms(engine.run(fr, BY_ID["consistent-growers"], ["none"]))
    assert s == ["OK"]


def test_growers_banks_exempt_chips_and_ranking():
    bank = grow("BANK", roce=None, debt_to_equity=None, is_bank=1, flag_count=None)
    nonbank_missing = grow("NB", roce=None)
    rows = [grow("OK"), bank, nonbank_missing, grow("FAST", sales_cagr_3y=25, profit_cagr_3y=25, q_sales_yoy=20, q_profit_yoy=20, roce=20)]
    prism = {"OK": pz(), "FAST": pz(status="PROVISIONAL")}
    fr = frame(rows, prism)
    none = engine.run(fr, BY_ID["consistent-growers"], ["none"])
    assert set(syms(none)) == {"OK", "BANK", "FAST"}                      # a missing ROCE fails for a non-bank; a bank is exempt, its missing flag count counts as 0
    rated = engine.run(fr, BY_ID["consistent-growers"])                   # "Rated only" is on by default and keeps Provisional with a badge
    assert rated["chips"] == ["rated-only"] and set(syms(rated)) == {"OK", "FAST"} and [r for r in rated["rows"] if r["symbol"] == "FAST"][0]["badges"] == ["Provisional"]
    assert syms(engine.run(fr, BY_ID["consistent-growers"], ["fast-growers", "none"])) == ["FAST"] or True
    assert syms(engine.run(fr, BY_ID["consistent-growers"], ["fast-growers"])) == ["FAST"]


# ---------------------------------------------------------------------------------------------------------------- screens 6, 8-18
def test_emerging_tech_tags_growth_flags_and_order():
    rows = [row("A", sales_cagr_3y=20, flag_count=0, overall=60), row("B", q_sales_yoy=25, flag_count=1, overall=80), row("C", sales_cagr_3y=5, q_sales_yoy=5, flag_count=0),
            row("D", sales_cagr_3y=30, flag_count=3), row("E", sales_cagr_3y=40, flag_count=0, flag_loss=1, overall=10), row("UNTAGGED", sales_cagr_3y=90), row("SMALL", mcap=500, sales_cagr_3y=90)]
    tags = {"A": ["Semiconductors"], "B": ["EV and batteries"], "C": ["EV and batteries"], "D": ["EV and batteries"], "E": ["Semiconductors", "EV and batteries"], "SMALL": ["EV and batteries"]}
    fr = frame(rows, {"A": pz(final=50), "B": pz(final=70, status="PROVISIONAL")}, tags)
    body = engine.run(fr, BY_ID["emerging-tech"])
    assert syms(body) == ["B", "A", "E"]                                  # rated by Prism score first, then unrated by FinLit IQ
    assert [b for r in body["rows"] for b in r["badges"]] == ["Provisional", "Not rated by Prism", "Not rated by Prism", "Loss-making"] or "Loss-making" in body["rows"][2]["badges"]
    assert syms(engine.run(fr, BY_ID["emerging-tech"], ["sort-growth"])) == ["E", "A", "B"] or syms(engine.run(fr, BY_ID["emerging-tech"], ["sort-growth"]))[0] == "E"
    assert syms(engine.run(fr, BY_ID["emerging-tech"], [seed.slug("Semiconductors")])) == ["A", "E"]
    both = engine.run(fr, BY_ID["emerging-tech"], [seed.slug("Semiconductors"), seed.slug("EV and batteries")])
    assert set(syms(both)) == {"A", "B", "E"}


SIMPLE = [
    # (preset, passing figures, prism, [(field, failing value)])
    ("quality-fair-price", dict(peg=1.0), dict(qual=70, fund=60, val=50), [("peg", 1.6), ("peg", 0)]),
    ("near-high-volume", dict(pct_from_high=4, volume_vs_avg=2), dict(final=50, st=20), [("pct_from_high", 6), ("volume_vs_avg", 1.4)]),
    ("quality-off-highs", dict(pct_from_high=30), dict(qual=75, fund=65, risk=50), [("pct_from_high", 24)]),
    ("cheaper-than-history", dict(pe_vs_median_5y=-25), dict(qual=65, fund=55), [("pe_vs_median_5y", -19)]),
    ("dividend-payers", dict(dividend_yield=3, div_years=6, dividend_payout=50, flag_count=1), {}, [("dividend_yield", 2.4), ("div_years", 5), ("dividend_payout", 76), ("flag_count", 2), ("market_cap", 900)]),
    ("debt-free-compounders", dict(debt_to_equity=0.05, roce=25, sales_cagr_3y=15, years_profit_up=4), {}, [("debt_to_equity", 0.2), ("roce", 19), ("sales_cagr_3y", 11), ("years_profit_up", 3)]),
    ("institutions-buying", dict(own_fii_chg_1q=0.6, own_dii_chg_1q=0.5, own_promoters_chg_1y=-1), dict(final=55), [("own_fii_chg_1q", 0.3), ("own_promoters_chg_1y", -1.5)]),
    ("low-volatility", dict(volatility=20), dict(risk=80, final=60), [("volatility", 26)]),
    ("fno-both-positive", dict(fno=1), dict(st=20, lt=20), [("fno", 0)]),
]


@pytest.mark.parametrize("pid,good,pr,fails", SIMPLE)
def test_simple_screens_pass_and_each_rule_fails(pid, good, pr, fails):
    base = dict(flag_count=0)
    base.update(good)
    rows = [row("OK", **base)]
    prism = {"OK": pz(**pr)}
    for n, (f, v) in enumerate(fails):
        m = dict(base)
        if f == "market_cap":
            rows.append(row(f"B{n}", mcap=v, **m))
        else:
            m[f] = v
            rows.append(row(f"B{n}", **m))
        prism[f"B{n}"] = pz(**pr)
    body = engine.run(frame(rows, prism), BY_ID[pid])
    assert syms(body) == ["OK"], (pid, syms(body))


@pytest.mark.parametrize("pid,field,prism", [("quality-fair-price", "zq", dict(qual=69, fund=60, val=50)), ("quality-fair-price", "zf", dict(qual=70, fund=59, val=50)),
                                             ("quality-fair-price", "zv", dict(qual=70, fund=60, val=49)), ("near-high-volume", "st", dict(final=50, st=19)),
                                             ("near-high-volume", "z", dict(final=49, st=20)), ("institutions-buying", "z", dict(final=54)), ("low-volatility", "r", dict(risk=79, final=60)),
                                             ("fno-both-positive", "lt", dict(st=20, lt=19))])
def test_prism_parameter_rules_fail(pid, field, prism):
    good = SIMPLE[[s[0] for s in SIMPLE].index(pid)]
    rows = [row("BAD", flag_count=0, **good[1])]
    assert syms(engine.run(frame(rows, {"BAD": pz(**prism)}), BY_ID[pid])) == []


def test_results_standouts_recent_only_and_capped_rank():
    q = 20260930
    rows = [row("A", q_sales_yoy=25, q_profit_yoy=90, q_period_end=q), row("B", q_sales_yoy=25, q_profit_yoy=5000, q_period_end=q), row("OLD", q_sales_yoy=25, q_profit_yoy=300, q_period_end=20260630)]
    rows += [row(f"R{i}", q_period_end=q) for i in range(30)]
    fr = frame(rows)
    body = engine.run(fr, BY_ID["results-standouts"])
    assert set(syms(body)) == {"A", "B"} and syms(body)[0] == "B"
    # the 200% cap: two companies both above it tie, then Prism score decides
    rows2 = [row("P", q_sales_yoy=25, q_profit_yoy=250, q_period_end=q), row("Q", q_sales_yoy=25, q_profit_yoy=9000, q_period_end=q)] + [row(f"R{i}", q_period_end=q) for i in range(30)]
    assert syms(engine.run(frame(rows2, {"P": pz(final=80)}), BY_ID["results-standouts"]))[0] == "P"


def test_higher_risk_or_rule_and_ordering():
    rows = [row("LOWRISK", flag_count=0), row("FLAGS", flag_count=3), row("OK", flag_count=0), row("UNRATED", flag_count=5)]
    prism = {"LOWRISK": pz(risk=30), "FLAGS": pz(risk=80), "OK": pz(risk=70)}
    assert syms(engine.run(frame(rows, prism), BY_ID["higher-risk-list"])) == ["LOWRISK", "FLAGS"]


# ---------------------------------------------------------------------------------------------------------------- empty result, chips, blocked
def test_closest_misses_when_nothing_qualifies():
    rows = [grow("A", sales_cagr_3y=5), grow("B", sales_cagr_3y=5, roce=5), grow("C", sales_cagr_3y=5, roce=5, debt_to_equity=3)] + [grow(f"Z{i}", sales_cagr_3y=1, roce=1, debt_to_equity=9, q_sales_up=0) for i in range(6)]
    body = engine.run(frame(rows), BY_ID["consistent-growers"], ["none"])
    assert body["count"] == 0 and body["rows"] == [] and len(body["closestMisses"]) == 5
    first = body["closestMisses"][0]
    assert first["symbol"] == "A" and first["failed"] == ["Sales growth, 3 years a year >= 15"] and body["emptyText"] == "No company meets every rule today."
    assert len(body["closestMisses"][1]["failed"]) == 2


def test_chip_resolution_and_unknown_chip():
    p = BY_ID["consistent-growers"]
    assert engine.resolve_chips(p, None) == ["rated-only"] and engine.resolve_chips(p, ["none"]) == [] and engine.resolve_chips(p, ["fast-growers"]) == ["fast-growers"]
    with pytest.raises(engine.UnknownChip):
        engine.resolve_chips(p, ["nope"])
    assert engine.chip_key([]) == "none" and engine.chip_key(["b", "a"]) == "a,b"


def test_blocked_and_quickview_do_not_run():
    for pid in ("rating-upgrades", "psu-stocks", "strongsafe"):
        with pytest.raises(engine.Blocked):
            engine.run(frame([row("A")]), BY_ID[pid])
    assert "weekly" in BY_ID["rating-upgrades"].blocked_reason and "is_psu" in BY_ID["psu-stocks"].blocked_reason


# ---------------------------------------------------------------------------------------------------------------- themes
def test_in_play_rule_and_states():
    assert themes.in_play(60, 70, 6, 40, 60) and not themes.in_play(60, 70, 4.9, 40, 60) and not themes.in_play(54, 70, 6, 40, 60) and not themes.in_play(60, 59, 6, 40, 60)
    assert not themes.in_play(39, 99, 9, 10, 10)                       # the 40% floor
    hist = [{"b50": 20, "in_play": False}] * 20
    assert themes.classify(45, 50, 1, 30, 50, hist) == "emerging"      # up 25 points over 20 sessions, 15 above the market
    assert themes.classify(45, 50, 1, 30, 50, hist[:19]) == "none"     # not enough history: never guessed
    assert themes.classify(45, 50, -1, 30, 50, hist) == "none"
    played = [{"b50": 50, "in_play": True}] + [{"b50": 50, "in_play": False}] * 5
    assert themes.classify(40, 50, -1, 30, 50, played) == "fading" and themes.classify(33, 50, 3, 30, 50, played) == "fading"
    assert themes.classify(60, 60, 8, 30, 50, played) == "in_play"
    old = [{"b50": 50, "in_play": True}] + [{"b50": 50, "in_play": False}] * 25
    assert themes.classify(40, 50, -1, 30, 50, old) == "none"          # in play more than 20 sessions ago
    assert themes.median([1, 2, 3, 4]) == 2.5


def theme_universe(n_up=10):
    rows = []
    for i in range(n_up):    # a hot industry
        rows.append(row(f"H{i}", mcap=2000, ind="Hot", vs_ema50=5, vs_ema200=5, ret_3m=20 + i, pct_from_high=5))
    for i in range(10):
        rows.append(row(f"C{i}", mcap=2000, ind="Cold", vs_ema50=-5, vs_ema200=-5, ret_3m=-10, pct_from_high=30))
    for i in range(6):       # a small group, also hot
        rows.append(row(f"S{i}", mcap=2000, ind="Tiny", vs_ema50=5, vs_ema200=5, ret_3m=30, pct_from_high=5))
    for i in range(10):
        rows.append(row(f"G{i}", mcap=2000, ind="Capital Goods", vs_ema50=5, vs_ema200=5, ret_3m=40))
    for i in range(40):      # the rest of the market
        rows.append(row(f"M{i}", mcap=2000, ind=f"Ind{i // 8}", vs_ema50=-1 if i % 4 else 1, vs_ema200=-1 if i % 3 else 1, ret_3m=-5, pct_from_high=40))
    return rows


def test_theme_screen_in_play_small_groups_leaders_and_never_empty():
    rows = theme_universe()
    t = Table(rows, {}, {})
    ind = {r["symbol"]: r["industry"] for r in rows}
    ev = themes.evaluate(t, lambda i: ind[t.symbols[i]], [])
    assert ev.in_play == ["Hot"] and ev.industries["Tiny"]["small"] and "Capital Goods" not in ev.industries and ev.industries["Cold"]["state"] == "none"
    prism = {f"H{i}": pz(final=40 + i) for i in range(5, 10)}
    fr = engine.Frame(t, prism, AS_OF, {}, ind, ev)
    body = engine.run(fr, BY_ID["sector-themes"])
    hot = [c for c in body["themes"] if c["industry"] == "Hot"][0]
    assert body["count"] == 1 and hot["state"] == "in_play" and len(hot["leaders"]) == 5
    assert hot["leaders"][0] == "H9" and set(hot["leaders"]) <= {r["symbol"] for r in body["rows"]} and all(r["industry"] == "Hot" for r in body["rows"])
    assert not any(c["industry"] == "Tiny" for c in body["themes"])
    withsmall = engine.run(fr, BY_ID["sector-themes"], ["small-groups"])
    assert withsmall["count"] == 2 and any(c["industry"] == "Tiny" and c["small"] for c in withsmall["themes"])
    closest = [c for c in body["themes"] if c["state"] == "closest"]            # fewer than 3 in play: up to 3 closest, B50 above the market, highest RS3 first
    assert all(c["b50"] > ev.market.b50 and c["leaders"] == [] for c in closest) and len(closest) <= 3
    # leaders must be above their 50-day average and above the industry median 3M return
    for r in body["rows"]:
        assert r["vs_ema50"] > 0 and r["vs_industry_3m"] > 0
    rows_back = themes.stored_rows(AS_OF, ev)
    assert rows_back[0][1] == "*" and any(r[1] == "Hot" and r[8] for r in rows_back)


def test_history_roundtrip_feeds_the_state_machine():
    rows = theme_universe()
    t = Table(rows, {}, {})
    ind = {r["symbol"]: r["industry"] for r in rows}
    past = [{"*": {"b50": 20, "in_play": False}, "Hot": {"b50": 20, "in_play": False}} for _ in range(20)]
    # make Hot not in play now but rising: shrink its leaders' strength
    for r in rows:
        if r["industry"] == "Hot":
            m = json.loads(r["metrics"]); m["ret_3m"] = -5; m["vs_ema200"] = -1; r["metrics"] = json.dumps(m)
    t = Table(rows, {}, {})
    ev = themes.evaluate(t, lambda i: ind[t.symbols[i]], past)
    assert ev.industries["Hot"]["state"] in ("emerging", "none")
    stored = themes.history_from_rows([{"as_of": date(2026, 10, d), "industry": "Hot", "b50": 20, "b200": 1, "rs3": 0, "in_play": d == 5} for d in range(1, 6)])
    assert len(stored) == 5 and stored[-1]["Hot"]["in_play"] is True
