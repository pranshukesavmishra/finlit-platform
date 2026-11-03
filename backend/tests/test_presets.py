"""Prebuilt screens: registry rules, percentile maths, every screen's rules on a synthetic universe, chips, closest misses, the theme state machine."""
import json
import re
from datetime import date
from pathlib import Path

import pytest

from finlit.presets import derive, engine, expr, industry, theme_map, themes
from finlit.presets.registry import ADVANCED, ALL, BANNED_WORDS, BY_ID, DISCLAIMER, PRESETS, QUICK_VIEWS
from finlit.screener.data import Table
from finlit.screener.ql import analyze

AS_OF = date(2026, 10, 30)


def row(sym, mcap=5000, ind="Pharmaceuticals", sector="S", **m):
    m.setdefault("market_cap", mcap)
    return {"symbol": sym, "name": sym.title(), "sector": sector, "industry": ind, "band": "mixed", "metrics": json.dumps(m)}


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
    live = [p for p in ADVANCED if p.status == "live"]
    assert len(live) == 15 and [p.id for p in ADVANCED if p.status == "blocked"] == ["rating-upgrades", "psu-stocks"] and len(QUICK_VIEWS) == 3
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
    tops = [BY_ID[f"highest-rated-{k}"] for k in ("large", "mid", "small")]
    assert all(p.limit == 10 and p.top10 and p.sector_cap == 3 and abs(sum(w for _, w in p.rank_score) - 1.0) < 1e-9 for p in tops)
    assert [p.prism_filters["zrmin"] for p in tops] == [50, 50, 60] and all(p.prism_filters["zmin"] == 60 and p.prism_filters["zqmin"] == 50 for p in tops)
    assert all(p.limit == 25 for p in live[3:]) and tops[0].card_text == "The 10 large caps with the strongest mix of Prism rating, valuation, risk and price strength."
    assert [p.id for p in live][3:] == ["momentum-leaders", "at-52-week-high", "both-views-positive", "consistent-growers", "emerging-tech", "sector-themes", "quality-fair-price",
                                         "quality-off-highs", "value-with-quality", "low-risk-compounders", "low-volatility", "higher-risk-list"]
    assert [p.id for p in QUICK_VIEWS] == ["strongsafe", "fairvalue", "weakvalue"] and "Valuation below 50" in BY_ID["weakvalue"].card_text
    for p in PRESETS:     # a blocked card says it in plain words, never a developer's note
        if p.status == "blocked":
            assert not re.search(r"prism_reports|is_psu|one row|flag", p.blocked_reason or "", re.I), p.id


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


# ---------------------------------------------------------------------------------------------------------------- rank score, sector cap, short list
def test_percentile_of_a_value_among_a_bucket_ties_and_non_members():
    arr = [10, 20, 20, 40]
    assert engine._pct_in(arr, 10) == 0.0 and engine._pct_in(arr, 40) == 1.0 and engine._pct_in(arr, 20) == pytest.approx((1 + 2) / 2 / 3)
    assert engine._pct_in(arr, 5) == 0.0 and engine._pct_in(arr, 99) == 1.0 and engine._pct_in([7], 7) == 0.5
    assert engine._pct_in(arr, 30) == pytest.approx(2.5 / 3 - 0.0, abs=0.2)


def uni(extra=()):
    """100 large, 150 mid and 30 small companies of Rs 1,000 Cr or more, each with the figures every Top 10 gate and input reads."""
    def m(mc, i): return dict(market_cap=mc, pct_from_high=10, ret_3m=5 + i % 9, ret_6m=8 + i % 7, ret_1y=15 + i % 11, high_52w=120, low_52w=100)
    rows = [row(f"L{i:03d}", mcap=100000 - i * 100, sector=f"SecL{i % 30}", **m(100000 - i * 100, i)) for i in range(100)]
    rows += [row(f"M{i:03d}", mcap=20000 - i * 10, sector=f"SecM{i % 30}", **m(20000 - i * 10, i)) for i in range(150)]
    rows += [row(f"X{i:03d}", mcap=3000 - i * 10, sector=f"SecX{i % 20}", **m(3000 - i * 10, i)) for i in range(30)]
    return rows + list(extra)


def with_prism(rows, **over):
    prism = {r["symbol"]: pz(final=70, qual=70, risk=70, val=60, st=30, lt=30) for r in rows}
    for k, v in over.items():
        prism[k] = v
    return prism


def test_top_large_gates_each_fail_and_count_text():
    rows = uni()
    bad = {"G_PRISM": pz(final=59), "G_QUAL": pz(qual=49), "G_RISK": pz(risk=49), "G_LT": pz(lt=-20), "G_PROV": pz(status="PROVISIONAL")}
    for i, k in enumerate(bad):
        rows[i]["symbol"] = k
    prism = with_prism(rows, **bad)
    rows[5]["metrics"] = json.dumps({**json.loads(rows[5]["metrics"]), "pct_from_high": 31}); rows[5]["symbol"] = "G_HIGH"; prism["G_HIGH"] = pz()
    body = engine.run(frame(rows, prism), BY_ID["highest-rated-large"])
    got = syms(body)
    assert not set(bad) & set(got) and "G_HIGH" not in got and body["shown"] == 10 and body["listText"] == f"Top 10 of {body['count']} that pass"
    assert all(s.startswith("L") or s in bad or s == "G_HIGH" for s in got)


def test_top_small_risk_floor_is_60():
    rows = uni()
    prism = with_prism(rows)
    prism["X000"] = pz(risk=59); prism["X001"] = pz(risk=60)
    got = syms(engine.run(frame(rows, prism), BY_ID["highest-rated-small"]))
    assert "X000" not in got and all(s.startswith("X") for s in got)


def test_top_rank_is_a_weighted_percentile_mix_so_a_better_long_term_view_wins_a_tie_on_prism():
    rows = uni()
    for r in rows:
        r["metrics"] = json.dumps({**json.loads(r["metrics"]), "ret_3m": 6, "ret_6m": 9, "ret_1y": 20})   # equal returns: only the long-term view differs
    prism = with_prism(rows)
    for i, r in enumerate(rows[:100]):
        prism[r["symbol"]] = pz(final=70, qual=70, risk=70, val=60, st=30, lt=20 + i % 50)
    prism["L040"] = pz(final=70, qual=70, risk=70, val=60, st=30, lt=90)        # same everything, a far stronger long-term view
    body = engine.run(frame(rows, prism), BY_ID["highest-rated-large"])
    first = body["rows"][0]
    assert first["symbol"] == "L040" and first["rank_score"] > body["rows"][-1]["rank_score"]


def test_top_sector_cap_is_three_per_label_and_ties_go_to_quality_then_prism():
    rows = uni()
    for r in rows[:6]:
        r["sector"] = "Same"
    prism = with_prism(rows)
    for i, r in enumerate(rows[:6]):
        prism[r["symbol"]] = pz(final=95 - i, qual=70 + i, risk=70, val=60, st=30, lt=30)
    body = engine.run(frame(rows, prism), BY_ID["highest-rated-large"])
    same = [r["symbol"] for r in body["rows"] if r["symbol"] in {x["symbol"] for x in rows[:6]}]
    assert len(same) == 3 and len(body["rows"]) == 10


def test_a_short_top_list_is_filled_with_names_that_fail_only_the_trend_or_52_week_gate_and_badged():
    rows = uni()[:100]
    prism = {r["symbol"]: pz(final=70, lt=-40) for r in rows}                    # every large cap fails the trend gate...
    for r in rows[:4]:
        prism[r["symbol"]] = pz(final=70, lt=30)                                  # ...except four
    prism["L010"] = pz(final=40, lt=30)                                           # fails the Prism gate too: never a filler
    body = engine.run(frame(rows, prism), BY_ID["highest-rated-large"])
    assert body["count"] == 4 and body["shown"] == 10 and [r["badges"] for r in body["rows"][:4]] == [[]] * 4
    fill = body["rows"][4:]
    assert len(fill) == 6 and all("Trend not confirmed" in r["badges"] for r in fill) and "L010" not in syms(body)


def test_provisional_chip_adds_provisional_names_with_a_badge():
    rows = uni()
    prism = with_prism(rows)
    prism["L000"] = pz(final=99, status="PROVISIONAL", qual=90, risk=90, val=90, st=60, lt=60)
    off = engine.run(frame(rows, prism), BY_ID["highest-rated-large"])
    on = engine.run(frame(rows, prism), BY_ID["highest-rated-large"], ["include-provisional"])
    assert "L000" not in syms(off) and "L000" in syms(on) and next(r for r in on["rows"] if r["symbol"] == "L000")["badges"] == ["Provisional"]


def test_a_blank_technical_view_drops_a_company_and_the_card_says_how_many():
    rows = uni()[:100]
    prism = with_prism(rows)
    for r in rows[:3]:
        z = pz(); z["prism_lt_score"] = None; prism[r["symbol"]] = z
    body = engine.run(frame(rows, prism), BY_ID["highest-rated-large"])
    assert not {"L000", "L001", "L002"} & set(syms(body)) and any("3 rated companies have no long-term technical view" in n for n in body["notes"])


# ---------------------------------------------------------------------------------------------------------------- the other Advanced screens
def mrow(sym, **over):
    m = dict(pct_from_high=8, ret_3m=4, ret_6m=9, ret_1y=20, market_cap=3000, high_52w=110, low_52w=100)
    m.update(over)
    return row(sym, **m)


@pytest.mark.parametrize("field,value", [("pct_from_high", 16), ("ret_3m", 0), ("ret_6m", -2), ("market_cap", 900)])
def test_momentum_each_price_rule_fails(field, value):
    rows = [mrow("OK"), mrow("BAD", **{field: value})] + [mrow(f"F{i}", ret_3m=i, ret_6m=i, ret_1y=i) for i in range(1, 5)]
    prism = {"OK": pz(final=60, st=0, lt=20), "BAD": pz(final=60, st=0, lt=20)}
    body = engine.run(frame(rows, prism), BY_ID["momentum-leaders"])
    assert "OK" in syms(body) and "BAD" not in syms(body)


@pytest.mark.parametrize("z", [pz(final=49, st=0, lt=20), pz(final=60, st=0, lt=19), pz(final=60, st=-1, lt=20)])
def test_momentum_each_prism_rule_fails(z):
    rows = [mrow("OK"), mrow("BAD")] + [mrow(f"F{i}", ret_3m=i, ret_6m=i, ret_1y=i) for i in range(1, 5)]
    body = engine.run(frame(rows, {"OK": pz(final=60, st=0, lt=20), "BAD": z}), BY_ID["momentum-leaders"])
    assert "OK" in syms(body) and "BAD" not in syms(body)


def test_at_52_week_high_needs_5_percent_and_a_positive_short_term_view_no_volume():
    rows = [mrow("OK", pct_from_high=5), mrow("FAR", pct_from_high=5.1), mrow("WEAKST", pct_from_high=1), mrow("LOWPRISM", pct_from_high=1), mrow("NOVOL", pct_from_high=2)]
    prism = {"OK": pz(final=50, st=20), "FAR": pz(final=70, st=40), "WEAKST": pz(final=70, st=19), "LOWPRISM": pz(final=49, st=40), "NOVOL": pz(final=70, st=45)}
    body = engine.run(frame(rows, prism), BY_ID["at-52-week-high"])
    assert syms(body) == ["NOVOL", "OK"]                      # ranked by the short-term view; no volume figure is read


def test_both_views_positive_is_large_and_mid_by_default_and_all_caps_with_the_chip():
    rows = uni()
    prism = {r["symbol"]: pz(final=70, st=25, lt=25) for r in rows}
    fr = frame(rows, prism)
    default = engine.run(fr, BY_ID["both-views-positive"])
    allc = engine.run(fr, BY_ID["both-views-positive"], ["all-caps"])
    assert not any(r["symbol"].startswith("X") for r in default["exportRows"]) and any(r["symbol"].startswith("X") for r in allc["exportRows"]) and default["count"] == 250 and allc["count"] == 280


def test_consistent_growers_use_the_prism_parts_and_the_fast_growers_chip():
    rows = [mrow(s) for s in ("OK", "FAST", "G", "Q", "R", "PROV")]
    prism = {"OK": pz(fund=75, qual=60, risk=50), "FAST": pz(fund=88, qual=70, risk=60), "G": pz(fund=74.9, qual=70, risk=70), "Q": pz(fund=80, qual=59, risk=70), "R": pz(fund=80, qual=70, risk=49),
             "PROV": pz(fund=80, qual=70, risk=70, status="PROVISIONAL")}
    fr = frame(rows, prism)
    body = engine.run(fr, BY_ID["consistent-growers"])
    assert syms(body) == ["FAST", "PROV", "OK"] and next(r for r in body["rows"] if r["symbol"] == "PROV")["badges"] == ["Provisional"]
    assert syms(engine.run(fr, BY_ID["consistent-growers"], ["fast-growers"])) == ["FAST"]


@pytest.mark.parametrize("pid,good,bad", [
    ("quality-fair-price", dict(qual=70, fund=60, val=60), [dict(qual=69), dict(fund=59), dict(val=59)]),
    ("value-with-quality", dict(val=75, qual=60, risk=60, fund=50), [dict(val=74), dict(qual=59), dict(risk=59), dict(fund=49)]),
    ("low-risk-compounders", dict(risk=80, qual=75, fund=65), [dict(risk=79), dict(qual=74), dict(fund=64)]),
])
def test_value_and_safety_screens_use_only_prism_parts(pid, good, bad):
    rows = [mrow("OK")] + [mrow(f"B{i}") for i in range(len(bad))]
    base = dict(final=70, fund=70, qual=80, risk=90, val=80)
    prism = {"OK": pz(**{**base, **good})}
    for i, d in enumerate(bad):
        prism[f"B{i}"] = pz(**{**base, **good, **d})
    assert syms(engine.run(frame(rows, prism), BY_ID[pid])) == ["OK"]


def test_quality_off_highs_keeps_its_rule_and_the_turning_up_chip_reads_the_short_term_view():
    rows = [mrow("UP", pct_from_high=30), mrow("DOWN", pct_from_high=40), mrow("NEAR", pct_from_high=24)]
    prism = {"UP": pz(qual=80, fund=70, risk=60, st=5), "DOWN": pz(qual=80, fund=70, risk=60, st=-5), "NEAR": pz(qual=80, fund=70, risk=60, st=5)}
    fr = frame(rows, prism)
    assert set(syms(engine.run(fr, BY_ID["quality-off-highs"]))) == {"UP", "DOWN"}
    assert syms(engine.run(fr, BY_ID["quality-off-highs"], ["turning-up"])) == ["UP"]
    assert {"prism_st_score", "prism_lt_score"} <= {c["key"] for c in engine.run(fr, BY_ID["quality-off-highs"])["columns"]}


def test_low_volatility_reads_the_52_week_range_not_a_volatility_figure():
    rows = [mrow("OK", high_52w=135, low_52w=100), mrow("WIDE", high_52w=136, low_52w=100)]
    prism = {"OK": pz(final=60, risk=80), "WIDE": pz(final=60, risk=95)}
    assert syms(engine.run(frame(rows, prism), BY_ID["low-volatility"])) == ["OK"]


def test_higher_risk_has_three_ways_in_and_ranks_the_lowest_risk_first():
    rows = [mrow(s) for s in ("RISK", "PRISM", "TREND", "NONE", "DEEPONLY")]
    rows[2] = mrow("TREND", pct_from_high=40); rows[4] = mrow("DEEPONLY", pct_from_high=40)
    prism = {"RISK": pz(final=70, risk=39), "PRISM": pz(final=34, risk=70), "TREND": pz(final=70, risk=70, lt=-50), "NONE": pz(final=70, risk=70), "DEEPONLY": pz(final=70, risk=70, lt=-49)}
    assert syms(engine.run(frame(rows, prism), BY_ID["higher-risk-list"])) == ["RISK", "PRISM", "TREND"]


def test_blocked_and_quick_views_do_not_run():
    for pid in ("rating-upgrades", "psu-stocks", "strongsafe"):
        with pytest.raises(engine.Blocked):
            engine.run(frame([mrow("A")]), BY_ID[pid])


# ---------------------------------------------------------------------------------------------------------------- Emerging tech
def test_theme_map_joins_by_sector_label_named_additions_and_exclusions():
    tags = theme_map.tags_for(["HAL", "HAVELLS", "KAYNES", "PERSISTENT", "ZZZ", "AMARAJABAT"], ["Aerospace & Defense", "Consumer Electronics", "Capital Goods", "Information Technology", "Pharma", "Auto Components"])
    assert tags["HAL"] == ["Defence, aerospace and shipbuilding"] and "HAVELLS" not in tags
    assert tags["KAYNES"] == ["Electronics, EMS and semiconductors"] and tags["PERSISTENT"] == ["Software products, AI and data"] and "ZZZ" not in tags
    assert tags["AMARAJABAT"] == ["EV and batteries"]                      # the old symbol still counts while only it is listed
    assert len(theme_map.subthemes()) == 8 and theme_map.subthemes()[0] == "Defence, aerospace and shipbuilding"


def test_emerging_tech_gates_order_and_unrated_below():
    rows = [mrow("GOOD", sector="Aerospace & Defense"), mrow("GOOD2", sector="Aerospace & Defense"), mrow("SLOW", sector="Aerospace & Defense"), mrow("RISKY", sector="Aerospace & Defense"),
            mrow("SMALLCAP", sector="Aerospace & Defense", market_cap=900), mrow("UNR", sector="Aerospace & Defense", market_cap=2500), mrow("OTHER", sector="Banks"), mrow("UNR2", sector="Aerospace & Defense", market_cap=2000)]
    prism = {"GOOD": pz(final=70, fund=60, risk=60), "GOOD2": pz(final=80, fund=60, risk=60), "SLOW": pz(final=80, fund=49, risk=60), "RISKY": pz(final=80, fund=60, risk=39),
             "SMALLCAP": pz(final=80, fund=60, risk=60), "OTHER": pz(final=90, fund=90, risk=90)}
    tags = theme_map.tags_for([r["symbol"] for r in rows], [r["sector"] for r in rows])
    fr = frame(rows, prism, tags=tags)
    body = engine.run(fr, BY_ID["emerging-tech"])
    assert syms(body) == ["GOOD2", "GOOD", "UNR", "UNR2"]                     # rated first by the rank score; unrated below by market cap; no trend gate
    assert all("Defence, aerospace and shipbuilding" in str(r["sub_theme"]) for r in body["rows"])
    every = engine.run(fr, BY_ID["emerging-tech"], ["show-all-theme"])
    assert {"SLOW", "RISKY"} <= set(syms(every)) and "SMALLCAP" not in syms(every)
    one = engine.run(fr, BY_ID["emerging-tech"], ["defence-aerospace-and-shipbuilding"])
    assert set(syms(one)) == set(syms(body))


# ---------------------------------------------------------------------------------------------------------------- empty result and chips
def test_closest_misses_when_nothing_qualifies():
    rows = [mrow("NEAR1"), mrow("FAR")]
    prism = {"NEAR1": pz(final=70, fund=74, qual=70, risk=60), "FAR": pz(final=30, fund=20, qual=20, risk=20)}
    body = engine.run(frame(rows, prism), BY_ID["consistent-growers"])
    assert body["count"] == 0 and body["closestMisses"][0]["symbol"] == "NEAR1" and "No company meets every rule" in body["emptyText"]


def test_chip_resolution_and_unknown_chip():
    p = BY_ID["highest-rated-large"]
    assert engine.resolve_chips(p, None) == [] and engine.resolve_chips(p, ["include-provisional"]) == ["include-provisional"] and engine.resolve_chips(p, ["none"]) == []
    with pytest.raises(engine.UnknownChip):
        engine.resolve_chips(p, ["nope"])
    assert engine.chip_key([]) == "none" and engine.chip_key(["b", "a"]) == "a,b"


# ---------------------------------------------------------------------------------------------------------------- Sector themes in play
def test_in_play_rule_and_states():
    assert themes.in_play(60, None, 6, 40) and not themes.in_play(60, None, 4.9, 40) and not themes.in_play(54, None, 6, 40)      # 15 points above the market's breadth
    assert not themes.in_play(39, None, 9, 10)                         # the 40% floor
    hist = [{"b50": 20, "in_play": False}] * 20
    assert themes.classify(45, None, 1, 30, None, hist) == "emerging"  # up 25 points over 20 sessions, 15 above the market
    assert themes.classify(45, None, 1, 30, None, hist[:19]) == "none"  # not enough history: never guessed
    assert themes.classify(45, None, -1, 30, None, hist) == "none"
    played = [{"b50": 50, "in_play": True}] + [{"b50": 50, "in_play": False}] * 5
    assert themes.classify(40, None, -1, 30, None, played) == "fading" and themes.classify(33, None, 3, 30, None, played) == "fading"
    assert themes.classify(60, None, 8, 30, None, played) == "in_play"
    old = [{"b50": 50, "in_play": True}] + [{"b50": 50, "in_play": False}] * 25
    assert themes.classify(40, None, -1, 30, None, old) == "none"      # in play more than 20 sessions ago
    assert themes.median([1, 2, 3, 4]) == 2.5 and themes.FLOOR == 1000 and themes.NEAR_HIGH == 15


def theme_universe(n_up=10):
    rows = []
    for i in range(n_up):    # a hot sector: close to its highs, rising
        rows.append(row(f"H{i}", mcap=2000, ind="Hot", ret_3m=20 + i, pct_from_high=5))
    for i in range(10):
        rows.append(row(f"C{i}", mcap=2000, ind="Cold", ret_3m=-10, pct_from_high=30))
    for i in range(6):       # a small group, also hot
        rows.append(row(f"S{i}", mcap=2000, ind="Tiny", ret_3m=30, pct_from_high=5))
    for i in range(10):
        rows.append(row(f"G{i}", mcap=2000, ind="Capital Goods", ret_3m=40, pct_from_high=1))
    for i in range(40):      # the rest of the market
        rows.append(row(f"M{i}", mcap=2000, ind=f"Ind{i // 8}", ret_3m=-5, pct_from_high=40))
    return rows


def test_breadth_is_the_share_near_the_52_week_high_not_moving_averages():
    rows = theme_universe()
    t = Table(rows, {}, {})
    ind = {r["symbol"]: r["industry"] for r in rows}
    ev = themes.evaluate(t, lambda i: ind[t.symbols[i]], [])
    hot = ev.industries["Hot"]
    assert hot["b50"] == 100.0 and ev.industries["Cold"]["b50"] == 0.0 and hot["rs3"] > 5 and ev.market.b50 is not None


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
    closest = [c for c in body["themes"] if c["state"] == "closest"]            # fewer than 3 in play: up to 3 closest, breadth above the market, highest RS3 first
    assert all(c["breadth"] > ev.market.b50 and c["leaders"] == [] for c in closest) and len(closest) <= 3
    for r in body["rows"]:                                                       # leaders: within 15% of the high, 3-month return above the sector median
        assert r["pct_from_high"] <= 15 and r["vs_industry_3m"] > 0
    rows_back = themes.stored_rows(AS_OF, ev)
    assert rows_back[0][1] == "*" and any(r[1] == "Hot" and r[8] for r in rows_back) and all(r[4] is None for r in rows_back)


def test_history_roundtrip_ignores_rows_written_by_the_old_moving_average_breadth():
    stored = themes.history_from_rows([{"as_of": date(2026, 10, d), "industry": "Hot", "b50": 20, "b200": None, "rs3": 0, "in_play": d == 5} for d in range(1, 6)]
                                      + [{"as_of": date(2026, 9, 1), "industry": "Hot", "b50": 99, "b200": 70, "rs3": 9, "in_play": True}])
    assert len(stored) == 5 and stored[-1]["Hot"]["in_play"] is True and all(h["Hot"]["b50"] == 20 for h in stored)


# ---------------------------------------------------------------------------------------------------------------- the Basic tab
def buni(n_large=100, n_mid=60):
    """Large and mid caps of Rs 1,000 Cr or more with FinLit scores, no Prism ratings at all (the Basic tab never needs them)."""
    def m(mc, i): return dict(market_cap=mc, pct_from_high=10, ret_3m=5 + i % 9, ret_6m=8 + i % 7, ret_1y=15 + i % 11, fundamental_score=70 + i % 10, pillar_technical=60 + i % 10, pillar_quality=60,
                              pillar_growth=60, pillar_profitability=60, pillar_balance=60, overall=70, is_bank=0)
    rows = [row(f"L{i:03d}", sector=f"SecL{i % 30}", **m(100000 - i * 100, i)) for i in range(n_large)]
    rows += [row(f"M{i:03d}", sector=f"SecM{i % 30}", **m(20000 - i * 10, i)) for i in range(n_mid)]
    return rows


def edit(r, **kw):
    r["metrics"] = json.dumps({**json.loads(r["metrics"]), **kw})
    return r


def test_basic_registry_has_the_fourteen_cards_all_on_the_basic_tab():
    basic = [p for p in PRESETS if p.tab == "basic"]
    assert [p.id for p in basic] == ["basic-top-large", "basic-top-mid", "basic-top-small", "basic-strong-both", "basic-strong-business-lagging", "basic-strong-trend-weaker-business",
                                     "basic-strong-all-four", "basic-growth-leaders", "basic-profitable-debt-light", "basic-quality-compounders", "basic-momentum-leaders", "basic-near-high",
                                     "basic-quality-off-highs", "basic-emerging-tech", "basic-sector-themes", "basic-caution-list"]
    assert all(p.status == "live" for p in basic) and sum(1 for p in basic if p.top10) == 3
    for p in basic:
        text = " ".join(p.how_it_works).lower()
        assert "prism" not in text and "prism" not in p.card_text.lower(), p.id       # the Basic tab never names a Prism field


def test_basic_top_gates_sector_cap_and_the_bank_balance_sheet_blank():
    rows = buni()
    edit(rows[0], fundamental_score=64)                       # fails the Growth & Profitability gate
    edit(rows[1], pillar_technical=44)
    edit(rows[2], pillar_quality=49)
    edit(rows[3], pillar_balance=44)
    edit(rows[4], pct_from_high=31)
    edit(rows[5], pillar_balance=None)                        # blank, not a bank: out
    edit(rows[6], pillar_balance=None, is_bank=1)             # blank bank: in
    body = engine.run(frame(rows), BY_ID["basic-top-large"])
    got = syms(body)
    assert all(s not in got for s in ("L000", "L001", "L002", "L003", "L004", "L005"))
    assert body["listText"] == f"Top 10 of {body['count']} that pass" and body["count"] == 94 and body["shown"] == 10
    secs = [r["sector"] for r in body["rows"]]
    assert max(secs.count(s) for s in set(secs)) <= 3 and body["rows"][0]["rank_score"] >= body["rows"][-1]["rank_score"]
    allrows = engine.run(frame(rows), BY_ID["basic-top-large"])["exportRows"]
    assert allrows[0]["symbol"] and all(c["key"] != "prism_final" for c in body["columns"])
    mids = engine.run(frame(rows), BY_ID["basic-top-mid"])
    assert all(s.startswith("M") for s in syms(mids)) and mids["count"] == 60


def test_basic_small_cap_needs_a_balance_sheet_of_55_and_one_thousand_crore():
    rows = buni(100, 150)
    smalls = [row(f"X{i:03d}", sector=f"SecX{i}", market_cap=3000 - i * 10, pct_from_high=10, ret_3m=5, ret_6m=8, ret_1y=15, fundamental_score=70 + i % 5, pillar_technical=60, pillar_quality=60,
                  pillar_growth=60, pillar_profitability=60, pillar_balance=55 if i else 54, overall=70, is_bank=0) for i in range(20)]
    smalls.append(row("MICRO", sector="Other", market_cap=400, pct_from_high=10, ret_3m=5, ret_6m=8, ret_1y=15, fundamental_score=90, pillar_technical=90, pillar_quality=90, pillar_growth=90,
                      pillar_profitability=90, pillar_balance=90, overall=90, is_bank=0))
    body = engine.run(frame(rows + smalls), BY_ID["basic-top-small"])
    assert body["count"] == 19 and "X000" not in body["exportRows"][0]["symbol"] and "MICRO" not in [r["symbol"] for r in body["exportRows"]]


def test_basic_two_sided_cards_blank_allowed_and_cautions():
    def one(sym, **kw):
        base = dict(market_cap=5000, fundamental_score=80, pillar_technical=80, pillar_quality=80, pillar_growth=80, pillar_profitability=80, pillar_balance=80, overall=80, pct_from_high=3,
                    ret_3m=4, ret_6m=9, ret_1y=20, is_bank=0)
        base.update(kw)
        return row(sym, **base)
    rows = [one("BOTH"), one("LAG", pillar_technical=40, pct_from_high=35), one("TREND", fundamental_score=40, pillar_quality=40), one("NOBAL", pillar_balance=None),
            one("SMALLMC", market_cap=1500), one("RISKY", overall=40, pct_from_high=50, pillar_technical=20), one("DEEP", pct_from_high=30, fundamental_score=75)]

    def ids(pid): return set(syms(engine.run(frame(rows), BY_ID[pid])))
    assert ids("basic-strong-both") == {"BOTH", "NOBAL", "SMALLMC"}
    assert ids("basic-strong-business-lagging") == {"LAG", "RISKY"} and ids("basic-strong-trend-weaker-business") == {"TREND"}
    assert "NOBAL" not in ids("basic-strong-all-four") and "NOBAL" in ids("basic-growth-leaders") and "SMALLMC" not in ids("basic-growth-leaders")     # blank balance sheet allowed there; floor Rs 2,000 Cr
    assert ids("basic-caution-list") >= {"RISKY"} and "BOTH" not in ids("basic-caution-list")
    assert ids("basic-quality-off-highs") == {"LAG", "RISKY", "DEEP"}
    assert ids("basic-near-high") >= {"BOTH"} and "LAG" not in ids("basic-near-high") and "SMALLMC" not in ids("basic-near-high")
    pb = engine.run(frame(rows), BY_ID["basic-profitable-debt-light"])
    assert pb["rows"][0]["profit_plus_balance"] == 160


def test_a_stock_that_ran_over_300_percent_in_a_year_stays_out_of_top_10_and_momentum_lists():
    rows = buni()
    edit(rows[0], ret_1y=450)
    edit(rows[1], ret_1y=None)                  # not enough price history: not a reason to drop it
    for pid in ("basic-top-large", "basic-momentum-leaders"):
        body = engine.run(frame(rows), BY_ID[pid])
        got = [r["symbol"] for r in body["exportRows"]]
        assert "L000" not in got, pid
    assert engine.run(frame(rows), BY_ID["basic-top-large"])["count"] == 99       # only the 450% run is out; the blank one still passes
