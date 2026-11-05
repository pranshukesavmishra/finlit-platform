"""Macro & Sector Outlook: the engine (PRD sections 4 to 6), provenance and revisions (3, 8), the stored snapshots (8, 9), the routes (10), the admin (12) and
the acceptance criteria AC01 to AC16 and QA scenarios of section 14. Fixtures only: no test reaches a network."""
import json
import random
import socket
import time
from datetime import date, datetime, timedelta, timezone

import pytest

from finlit import macro
from finlit.macro_outlook import engine as E
from finlit.macro_outlook import seed as SEED
from finlit.macro_outlook import store as ST
from finlit.macro_outlook import views as V
from test_auth import app, make_admin, new_client, signed_in  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401
from test_macro import fake_sites

CFG = E.ModelConfig(1, 3.0, 5.0, 0.70, tuple((float(m), l) for m, l in E.DEFAULT_BANDS), 48)
D = date


def res(code, signal, name=None, value=1.0, unit="%", status="Available", obs=D(2026, 9, 30)):
    return E.IndicatorResult(code, name or code, status if signal is not None else (status if status != "Available" else "Missing"), value, unit, obs, obs, "x", 1, None, None, signal, signal, signal)


def obs(day, v, pub=None, rev=1, status="Available"):
    return E.Obs(day, pub or day, v, rev, status, "x")


# ------------------------------------------------------------------------------------------------------------ AC03: signals stay in [-1, 1]
@pytest.mark.parametrize("seed", range(5))
def test_signals_are_always_between_minus_one_and_one(seed):
    rnd = random.Random(seed)
    for ind in SEED.INDICATORS:
        norm, stale = ind[9], ind[6]
        for _ in range(40):
            base = D(2026, 1, 1)
            series = [obs(base + timedelta(days=30 * i), rnd.uniform(-1e4, 1e4) if rnd.random() < .3 else rnd.uniform(ind[7] or 0, ind[8] or 100)) for i in range(30)]
            r = E.indicator_result(ind[0], ind[1], ind[3], norm, 10 ** 6, series, series[-1].observation_date)
            for v in (r.level, r.momentum, r.signal):
                assert v is None or -1.0 <= v <= 1.0, (ind[0], v)


def test_threshold_level_and_momentum_average():
    norm = {"level": {"method": "threshold", "neutral": 4.0, "scale": 2.0}, "momentum": {"method": "change", "lookback_days": 91, "scale": 1.0}}
    s = [obs(D(2026, 6, 30), 5.0), obs(D(2026, 9, 30), 6.0)]
    r = E.indicator_result("CPI", "CPI", "%", norm, 100, s, D(2026, 10, 15))
    assert r.level == 1.0 and r.momentum == 1.0 and r.signal == 1.0
    s = [obs(D(2026, 6, 30), 6.0), obs(D(2026, 9, 30), 5.0)]                                        # elevated but easing: half the level, falling momentum
    r = E.indicator_result("CPI", "CPI", "%", norm, 100, s, D(2026, 10, 15))
    assert r.level == 0.5 and r.momentum == -1.0 and r.signal == pytest.approx(-0.25)


def test_a_missing_momentum_uses_the_level_alone_and_says_so():
    norm = {"level": {"method": "threshold", "neutral": 4.0, "scale": 2.0}, "momentum": {"method": "change", "lookback_days": 91, "scale": 1.0}}
    r = E.indicator_result("CPI", "CPI", "%", norm, 100, [obs(D(2026, 9, 30), 5.0)], D(2026, 10, 15))
    assert r.momentum is None and r.signal == 0.5 and "level alone" in r.reason


def test_credit_overheating_is_not_better_than_healthy_growth():
    norm = SEED.INDICATORS[5][9]
    sig = lambda x: E.level_signal(norm, [obs(D(2026, 9, 30), x)])   # noqa: E731
    assert sig(12) == 0 and sig(18) == 1.0 and sig(21) < sig(18) and sig(26) < 0 and sig(60) == -1.0


def test_repo_level_and_policy_action_are_separate_indicators():
    codes = {i[0]: i for i in SEED.INDICATORS}
    assert "REPO_RATE" in codes and "REPO_ACTION" in codes and codes["REPO_ACTION"][9]["momentum"] == {"method": "none"}


# ------------------------------------------------------------------------------------------------------------ no look-ahead, revisions
def test_no_look_ahead_only_what_was_published_by_the_as_of_date():
    rows = [obs(D(2026, 8, 31), 4.0, pub=D(2026, 9, 12)), obs(D(2026, 9, 30), 6.0, pub=D(2026, 10, 12))]
    assert [o.value for o in E.known_series(rows, D(2026, 10, 1))] == [4.0]                      # September CPI exists but is not public yet
    assert [o.value for o in E.known_series(rows, D(2026, 10, 12))] == [4.0, 6.0]
    assert E.known_series(rows, D(2026, 9, 1)) == []


def test_revised_data_keeps_the_original_for_earlier_as_of_dates():
    rows = [obs(D(2026, 9, 30), 5.5, pub=D(2026, 10, 12)), obs(D(2026, 9, 30), 5.9, pub=D(2026, 10, 30), rev=2, status="Revised")]
    assert E.known_series(rows, D(2026, 10, 20))[-1].value == 5.5
    last = E.known_series(rows, D(2026, 11, 2))[-1]
    assert last.value == 5.9 and E.indicator_result("CPI", "CPI", "%", {"level": {"method": "threshold", "neutral": 4, "scale": 2}}, 100, [last], D(2026, 11, 2)).status == "Revised"


def test_invalid_rows_are_never_used():
    assert E.known_series([obs(D(2026, 9, 30), 999.0, status="Invalid")], D(2026, 10, 1)) == []


def test_stale_and_missing_indicators_get_no_signal():
    norm = {"level": {"method": "threshold", "neutral": 4, "scale": 2}}
    old = E.indicator_result("CPI", "CPI", "%", norm, 100, [obs(D(2026, 1, 31), 5.0)], D(2026, 10, 1))
    assert old.status == "Stale" and old.signal is None and not old.valid
    gone = E.indicator_result("CPI", "CPI", "%", norm, 100, [], D(2026, 10, 1))
    assert gone.status == "Missing" and gone.signal is None


# ------------------------------------------------------------------------------------------------------------ AC04 to AC07: the score
def test_formula_sensitivity_weight_and_score():
    rules = [E.Rule("A", -0.5, 2.0), E.Rule("B", 1.0, 1.0)]
    out = E.score_sector("x", rules, {"A": res("A", 0.8), "B": res("B", 0.4)}, CFG)
    by = {c.indicator: c for c in out.contributions}
    assert by["A"].contribution == pytest.approx(-0.8) and by["B"].contribution == pytest.approx(0.4)          # signal x sensitivity x weight
    assert out.weighted_signal == pytest.approx(5.0 * (-0.4) / 3.0, abs=1e-6)                                  # scale x sum / sum of weights
    import math
    assert out.score == pytest.approx(round(50 + 50 * math.tanh(out.weighted_signal / 3.0), 2))
    assert 0 <= out.score <= 100 and out.status == "ok"


@pytest.mark.parametrize("score,label", [(100, "Strong Tailwind"), (80, "Strong Tailwind"), (79.4, "Tailwind"), (65, "Tailwind"), (64.4, "Neutral"), (45, "Neutral"), (44.4, "Headwind"),
                                         (25, "Headwind"), (24.4, "Strong Headwind"), (0, "Strong Headwind"), (79.5, "Strong Tailwind")])
def test_sentiment_bands(score, label):
    assert E.band_of(score, CFG.bands) == label


def test_zero_contributions_give_fifty_and_neutral():
    out = E.score_sector("x", [E.Rule("A", 0.5, 1), E.Rule("B", -0.5, 1)], {"A": res("A", 0.0), "B": res("B", 0.0)}, CFG)
    assert out.score == 50.0 and out.label == "Neutral" and out.status == "ok" and out.drivers == []


def test_score_is_bounded_even_for_extreme_inputs():
    rules = [E.Rule(c, 1.0, 1.0) for c in "ABC"]
    hi = E.score_sector("x", rules, {c: res(c, 1.0) for c in "ABC"}, CFG)
    lo = E.score_sector("x", rules, {c: res(c, -1.0) for c in "ABC"}, CFG)
    assert 0 <= lo.score < 25 and 80 < hi.score <= 100 and abs(hi.score + lo.score - 100) < 0.02


def test_missing_cpi_is_excluded_and_coverage_recalculated():
    rules = [E.Rule("CPI", -0.5, 1.0), E.Rule("CREDIT", 0.75, 2.0), E.Rule("GDP", 0.5, 1.0), E.Rule("X", 0.5, 1.0)]
    r = {"CPI": res("CPI", None), "CREDIT": res("CREDIT", 0.6), "GDP": res("GDP", 0.4), "X": res("X", 0.2)}
    out = E.score_sector("x", rules, r, CFG)
    assert out.coverage == 0.8 and out.status == "ok" and "CPI" in out.missing
    cpi = next(c for c in out.contributions if c.indicator == "CPI")
    assert not cpi.counted and cpi.contribution is None and cpi.signal is None                                # excluded, never zero-filled
    weight_valid = 2.0 + 1.0 + 1.0
    assert out.weighted_signal == pytest.approx(5.0 * (0.6 * .75 * 2 + 0.4 * .5 + 0.2 * .5) / weight_valid, abs=1e-6)


def test_below_minimum_coverage_is_insufficient_data_never_a_score():
    rules = [E.Rule("A", 0.5, 1.0), E.Rule("B", 0.5, 1.0), E.Rule("C", 0.5, 1.0)]
    out = E.score_sector("x", rules, {"A": res("A", 0.9), "B": res("B", None), "C": res("C", None)}, CFG)
    assert out.status == "insufficient_data" and out.score is None and out.label == "Insufficient Data" and out.weighted_signal is None
    assert "coverage 33%" in out.reason and "70%" in out.reason


def test_a_missing_critical_indicator_blocks_the_score_even_with_enough_coverage():
    rules = [E.Rule("BRENT", -1.0, 1.0, critical=True)] + [E.Rule(c, .5, 1.0) for c in "ABCDEFGHI"]
    r = {c: res(c, .3) for c in "ABCDEFGHI"}
    r["BRENT"] = res("BRENT", None, name="Brent crude")
    out = E.score_sector("aviation", rules, r, CFG)
    assert out.coverage == 0.9 and out.status == "insufficient_data" and out.critical_missing == ["BRENT"]
    assert out.reason.startswith("missing critical: Brent crude") or "missing critical: Brent crude" in out.reason


def test_top_two_drivers_by_absolute_contribution_with_a_deterministic_tie_break():
    rules = [E.Rule("A", 1.0, 1.0), E.Rule("B", -1.0, 1.0), E.Rule("C", 1.0, 1.0), E.Rule("D", .25, 1.0)]
    r = {"A": res("A", .5, obs=D(2026, 9, 1)), "B": res("B", .5, obs=D(2026, 9, 30)), "C": res("C", .5, obs=D(2026, 9, 30)), "D": res("D", 1.0)}
    prio = {"A": 30, "B": 20, "C": 10}
    first = E.score_sector("x", rules, r, CFG, prio)
    assert [c.indicator for c in first.drivers] == ["C", "B"]                       # equal size: priority 10 before 20 before 30
    for _ in range(10):
        shuffled = rules[:]
        random.shuffle(shuffled)
        assert [c.indicator for c in E.score_sector("x", shuffled, r, CFG, prio).drivers] == ["C", "B"]
    prio = {"A": 10, "B": 10, "C": 10}                                              # same priority: the fresher observation, then the code
    assert [c.indicator for c in E.score_sector("x", rules, r, CFG, prio).drivers] == ["B", "C"]


def test_the_score_is_reproducible_from_stored_contributions():
    rules = [E.Rule("A", -0.5, 2.0), E.Rule("B", 1.0, 1.0), E.Rule("C", .25, 1.5)]
    out = E.score_sector("x", rules, {"A": res("A", .8), "B": res("B", .4), "C": res("C", -.3)}, CFG)
    stored = [{"contribution": c.contribution, "weight": c.weight, "counted": c.counted} for c in out.contributions]
    assert E.recompute_from_stored(stored, CFG) == (out.weighted_signal, out.score)


# ------------------------------------------------------------------------------------------------------------ QA scenarios
def _seeded(sector, signals):
    rules = [E.Rule(i, c, w, k) for s, i, c, w, k in SEED.sensitivity_rows() if s == sector]
    return E.score_sector(sector, rules, {r.indicator: res(r.indicator, signals.get(r.indicator, 0.0)) for r in rules}, CFG)


def test_scenario_real_estate_rates_and_costs_negative_credit_positive():
    out = _seeded("real_estate", {"REPO_RATE": .8, "REPO_ACTION": .8, "WPI": .9, "BANK_CREDIT": .7})
    by = {c.indicator: c.contribution for c in out.contributions}
    assert by["REPO_RATE"] < 0 and by["WPI"] < 0 and by["BANK_CREDIT"] > 0
    assert out.status == "ok" and out.score < 45


def test_scenario_private_banks_credit_positive_funding_effects_are_separate():
    out = _seeded("private_banks", {"BANK_CREDIT": .8, "DEPOSIT_GROWTH": -.5, "REPO_RATE": .4, "REPO_ACTION": .5})
    by = {c.indicator: c.contribution for c in out.contributions}
    assert by["BANK_CREDIT"] > 0 and by["DEPOSIT_GROWTH"] < 0 and by["REPO_RATE"] < 0 and {"REPO_RATE", "REPO_ACTION", "DEPOSIT_GROWTH"} <= set(by)


def test_scenario_fmcg_cost_pressure_negative_and_demand_assessed_separately():
    out = _seeded("fmcg", {"FOOD_CPI": .9, "WPI": .7, "IIP_NONDURABLES": -.5, "GDP": -.3})
    by = {c.indicator: c.contribution for c in out.contributions}
    assert by["FOOD_CPI"] < 0 and by["WPI"] < 0 and by["IIP_NONDURABLES"] < 0 and by["GDP"] < 0
    assert out.status == "ok" and out.score < 45


def test_scenario_aviation_fuel_and_fx_negative_demand_positive():
    out = _seeded("aviation", {"BRENT": .8, "USDINR": .6, "GDP": .7})
    by = {c.indicator: c.contribution for c in out.contributions}
    assert by["BRENT"] < 0 and by["USDINR"] < 0 and by["GDP"] > 0


def test_every_sector_has_critical_flags_that_exist_and_weights_positive():
    codes = {i[0] for i in SEED.INDICATORS}
    assert len(SEED.SECTORS) == 35
    for s, i, c, w, k in SEED.sensitivity_rows():
        assert i in codes and -1 <= c <= 1 and w > 0
    for s, _n, _d in SEED.SECTORS:
        assert any(r[0] == s for r in SEED.sensitivity_rows()), s


# ------------------------------------------------------------------------------------------------------------ mapping rules
RULES = [{"label_kind": k, "match_type": m, "pattern": p, "sector_code": s, "priority": pr} for k, m, p, s, pr, _n in SEED.LABEL_RULES]


@pytest.mark.parametrize("sym,sector,industry,want", [
    ("HDFCBANK", "Private Sector Bank", "Banks", "private_banks"), ("SBIN", "Banks", "Banks", "psu_banks"), ("BANKBARODA", "Public Sector Bank", "Banks", "psu_banks"),
    ("RELIANCE", "Refineries & Marketing", "Petroleum Products", "oil_marketing"), ("INFY", "Computers - Software & Consulting", "IT - Software", "it_services"),
    ("BAJFINANCE", "Non Banking Financial Company (NBFC)", "Finance", "nbfc"), ("DLF", "Residential, Commercial Projects", "Realty", "real_estate"),
    ("INDIGO", "Airline", "Transport Services", "aviation"), ("ASIANPAINT", "Paints", "Consumer Durables", "paints"), ("ONGC", "Oil Exploration & Production", "Oil", "upstream_oil_gas"),
    ("X", "Some Unseen Fertiliser Label", None, "fertilisers"), ("Y", None, "Cement & Cement Products", "cement")])
def test_label_map_resolves_sector_then_industry_then_wording(sym, sector, industry, want):
    got = ST.resolve(RULES, sym, sector, industry)
    assert got and got[0] == want, got


def test_a_company_no_rule_matches_is_unmapped():
    assert ST.resolve(RULES, "ZZ", "Zzyzx Holdings Quark", "Qwerty") is None
    assert ST.resolve(RULES, "ZZ", None, None) is None


def test_segment_weights_use_reported_revenue_only_and_need_enough_mapped_share():
    latest = [{"name": "Oil to Chemicals", "revenue": 600.0}, {"name": "Digital Services", "revenue": 300.0}, {"name": "Oil and Gas", "revenue": 100.0}]
    w, why = ST.segment_weights(latest, RULES)
    assert w["oil_marketing"]["weight"] == 0.6 and w["telecom"]["weight"] == 0.3 and w["upstream_oil_gas"]["weight"] == 0.1 and "100%" in why
    assert sum(e["weight"] for e in w.values()) == pytest.approx(1.0)
    none, why = ST.segment_weights([{"name": "Retail", "revenue": 500.0}, {"name": "Digital Services", "revenue": 500.0}], RULES)
    assert none is None and "50%" in why                                         # half the revenue maps to no covered sector: no weights are invented
    none, why = ST.segment_weights([{"name": "Everything", "revenue": 100.0}], RULES)
    assert none is None


# ------------------------------------------------------------------------------------------------------------ wording
FORBIDDEN = ("buy", "sell", "hold", "reduce", "avoid", "accumulate", "target", "best", "multibagger", "top pick")


def test_wording_describes_and_never_advises():
    texts = [json.dumps(V.DISCLAIMER), SEED.MODEL_NOTE, json.dumps([i[10] for i in SEED.INDICATORS]), json.dumps([s[2] for s in SEED.SECTORS])]
    res_ = {c: res(c, .8, name=c) for c in "AB"}
    out = E.score_sector("x", [E.Rule("A", .5, 1), E.Rule("B", -.5, 1)], res_, CFG)
    texts.append(json.dumps(E.explain(out.label, "Sector", out.contributions, [E.Rule("A", .5, 1), E.Rule("B", -.5, 1)], {"A": "A", "B": "B"})))
    blob = " ".join(texts).lower()
    import re
    for w in FORBIDDEN:
        assert not re.search(r"\b" + w + r"\b", blob), w
    assert "not a company-specific assessment, forecast, or investment recommendation" in V.DISCLAIMER


def test_stale_warning_logic():
    now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
    fresh = {"lastOk": (now - timedelta(hours=5)).isoformat(), "lastStatus": "ok", "staleAfterHours": 48}
    assert V.stale_state(fresh, now)["isStale"] is False
    old = {**fresh, "lastOk": (now - timedelta(hours=60)).isoformat()}
    assert V.stale_state(old, now)["isStale"] and "Not refreshed" in V.stale_state(old, now)["message"]
    failed = {**fresh, "lastStatus": "failed"}
    assert V.stale_state(failed, now)["reason"] == "refresh_failed"
    assert V.stale_state({"lastOk": None}, now)["isStale"]


# ------------------------------------------------------------------------------------------------------------ database
MO_TABLES = ("macro_audit_log, macro_run_log, sector_macro_contributions, sector_macro_scores, macro_indicator_signals, company_macro_unmapped, company_sector_mapping, macro_label_map, "
             "sector_sensitivity, sector_master, macro_indicators, macro_indicator_history, macro_indicator_defs, macro_model_configuration, macro_points, macro_meta, commodity_snapshots")


@pytest.fixture
async def mo(store):  # noqa: F811
    await store.migrate()
    async with store.pool.acquire() as conn:
        await conn.execute(f"TRUNCATE {MO_TABLES} RESTART IDENTITY CASCADE")
    await store.redis.flushdb()
    yield store


async def load_macro(st):
    macro.PAUSE = 0
    r = await macro.refresh(st, transport=fake_sites(), today=D(2026, 10, 23), full=True)
    assert r["status"] in ("ok", "partial")


@pytest.mark.integration
async def test_migration_creates_the_prd_tables_with_numeric_types_and_keys(mo):
    async with mo.pool.acquire() as conn:
        tables = {r["table_name"] for r in await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
        for t in ("macro_indicators", "macro_indicator_history", "macro_indicator_signals", "sector_master", "sector_sensitivity", "company_sector_mapping", "sector_macro_scores",
                  "sector_macro_contributions", "macro_model_configuration"):
            assert t in tables, t
        types = {(r["table_name"], r["column_name"]): r["data_type"] for r in await conn.fetch(
            "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_name IN ('sector_macro_scores', 'sector_sensitivity', 'macro_indicators', 'sector_macro_contributions')")}
        for k in (("sector_macro_scores", "score"), ("sector_macro_scores", "coverage"), ("sector_sensitivity", "coefficient"), ("sector_sensitivity", "weight"), ("macro_indicators", "value"),
                  ("sector_macro_contributions", "contribution")):
            assert types[k] == "numeric", k
        idx = {r["indexname"] for r in await conn.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")}
        assert {"macro_hist_code_obs", "sms_sector_date", "csm_symbol", "csm_sector", "macro_model_one_active"} <= idx


@pytest.mark.integration
async def test_ac02_observations_keep_source_units_and_both_dates(mo):
    await load_macro(mo)
    out = await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    assert out["ingest"]["new"] > 300
    async with mo.pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM macro_indicator_history WHERE indicator_code = 'CPI' ORDER BY observation_date DESC LIMIT 3")
        cur = {r["indicator_code"]: r for r in await conn.fetch("SELECT * FROM macro_indicators")}
    assert rows and all(r["source"] == "MoSPI" and r["unit"] == "%" and r["frequency"] == "Monthly" and r["publication_date"] and r["observation_date"] and r["retrieved_at"] for r in rows)
    assert cur["CPI"]["status"] == "Available" and float(cur["CPI"]["value"]) == 5.54 and cur["CPI"]["pub_date_basis"]
    # a publication date we do not have is recorded as the observation date and says so; the repo series is derived from dated announcements
    assert cur["CPI"]["publication_date"] == cur["CPI"]["observation_date"] and cur["CPI"]["pub_date_basis"] == ST.ASSUMED
    assert cur["REPO_RATE"]["pub_date_basis"] == ST.ANNOUNCED and cur["BANK_CREDIT"]["pub_date_basis"] in (ST.SOURCE, ST.ASSUMED)


@pytest.mark.integration
async def test_indicators_without_a_source_are_missing_with_a_reason(mo):
    await load_macro(mo)
    await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    async with mo.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status, value, detail FROM macro_indicators WHERE indicator_code = 'BRENT'")
    assert row["status"] == "Missing" and row["value"] is None and "source key not set" in row["detail"] and "vendor feed" in row["detail"]


@pytest.mark.integration
async def test_a_changed_source_value_is_a_new_revision_and_old_snapshots_stay(mo):
    await load_macro(mo)
    await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    async with mo.pool.acquire() as conn:
        before = await conn.fetch("SELECT id, score, inputs_hash FROM sector_macro_scores ORDER BY id")
        await conn.execute("UPDATE macro_points SET v = 6.40 WHERE series = 'cpi' AND d = '2026-09-30'")
    out = await ST.run(mo, "test", today=D(2026, 10, 24), reconstruct_months=0)
    assert out["ingest"]["revised"] >= 1
    async with mo.pool.acquire() as conn:
        revs = await conn.fetch("SELECT revision_number, value, status, publication_date FROM macro_indicator_history WHERE indicator_code = 'CPI' AND observation_date = '2026-09-30' ORDER BY revision_number")
        after = await conn.fetch("SELECT id, score, inputs_hash FROM sector_macro_scores WHERE id <= $1 ORDER BY id", before[-1]["id"])
        cur = await conn.fetchrow("SELECT status, value FROM macro_indicators WHERE indicator_code = 'CPI'")
        by_date = await conn.fetchval("SELECT count(*) FROM sector_macro_scores WHERE snapshot_date = '2026-10-24'")
    assert [(r["revision_number"], float(r["value"]), r["status"]) for r in revs] == [(1, 5.54, "Available"), (2, 6.4, "Revised")] and revs[1]["publication_date"] == D(2026, 10, 24)
    assert [tuple(r) for r in after] == [tuple(r) for r in before]                      # the original snapshots are untouched
    assert cur["status"] == "Revised" and float(cur["value"]) == 6.4 and by_date == 35
    # the as-of rule: on 23 October the original figure is still what was known
    async with mo.pool.acquire() as conn:
        hist = await ST.load_history(mo.pool and conn)
    assert E.known_series(hist["CPI"], D(2026, 10, 23))[-1].value == 5.54 and E.known_series(hist["CPI"], D(2026, 10, 24))[-1].value == 6.4


@pytest.mark.integration
async def test_snapshots_contributions_and_audit_rows_are_immutable(mo):
    await load_macro(mo)
    await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    import asyncpg
    async with mo.pool.acquire() as conn:
        for sql in ("UPDATE sector_macro_scores SET score = 1", "DELETE FROM sector_macro_scores", "UPDATE sector_macro_contributions SET contribution = 1",
                    "DELETE FROM sector_macro_contributions", "UPDATE macro_audit_log SET actor = 'x'", "DELETE FROM macro_audit_log"):
            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(sql)


@pytest.mark.integration
async def test_ac05_a_stored_snapshot_recomputes_to_the_same_score_and_runs_are_idempotent(mo):
    await load_macro(mo)
    await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    async with mo.pool.acquire() as conn:
        cfg, _ = await ST.load_config(conn)
        snaps = await conn.fetch("SELECT id, score, weighted_signal, status, coverage FROM sector_macro_scores")
        ok = [s for s in snaps if s["status"] == "ok"]
        assert ok and len(snaps) == 35
        for s in ok:
            rows = [dict(r) for r in await conn.fetch("SELECT contribution, weight, counted, signal, coefficient FROM sector_macro_contributions WHERE score_id = $1", s["id"])]
            ws, score = E.recompute_from_stored(rows, cfg)
            assert score == float(s["score"]) and ws == pytest.approx(float(s["weighted_signal"]), abs=1e-6)
            assert 0 <= float(s["score"]) <= 100
            for r in rows:                                                              # contribution = signal x coefficient x weight, as stored
                if r["counted"]:
                    assert abs(float(r["signal"])) <= 1 and float(r["contribution"]) == pytest.approx(float(r["signal"]) * float(r["coefficient"]) * float(r["weight"]), abs=1e-7)
        for s in snaps:
            assert (s["status"] == "ok") == (s["score"] is not None)
    again = await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=0)
    assert again["calc"]["created"] == 0                                               # identical inputs: nothing new is stored


@pytest.mark.integration
async def test_history_is_reconstructed_month_ends_labelled_and_never_looks_ahead(mo):
    await load_macro(mo)
    out = await ST.run(mo, "test", today=D(2026, 10, 23), reconstruct_months=6)
    assert out["reconstructed"] == 6 * 35
    async with mo.pool.acquire() as conn:
        cfg, _ = await ST.load_config(conn)
        h = await V.history(conn, "private_banks", "ALL", cfg.version)
        sep = await conn.fetchrow("SELECT s.id, s.as_of FROM sector_macro_scores s JOIN sector_master m ON m.id = s.sector_id WHERE m.sector_code = 'private_banks' AND s.snapshot_date = '2026-09-30'")
        used = await conn.fetch("SELECT publication_date FROM sector_macro_contributions WHERE score_id = $1 AND counted", sep["id"])
    assert h["midpoint"] == 50 and {p["basis"] for p in h["points"]} == {"reconstructed", "live"} and len(h["points"]) == 7
    assert all(r["publication_date"] <= D(2026, 9, 30) for r in used)               # nothing published after the snapshot date was used
    async with mo.pool.acquire() as conn:
        short = await V.history(conn, "private_banks", "1M", cfg.version)
    assert 1 <= len(short["points"]) < 7


@pytest.mark.integration
async def test_every_company_gets_a_primary_sector_or_an_explicit_reason(ingested):
    st = ingested
    await st.migrate()
    async with st.pool.acquire() as conn:
        await conn.execute(f"TRUNCATE {MO_TABLES} RESTART IDENTITY CASCADE")
        await SEED.ensure_seed(conn)
        res_ = await ST.sync_mappings(conn, D(2026, 11, 5))
        total = await conn.fetchval("SELECT count(*) FROM companies")
        mapped = await conn.fetchval("SELECT count(*) FROM company_sector_mapping WHERE is_primary AND effective_to IS NULL")
        unmapped = await conn.fetch("SELECT symbol, reason FROM company_macro_unmapped")
        rel = await conn.fetchrow("SELECT s.sector_code, m.basis_label FROM company_sector_mapping m JOIN sector_master s ON s.id = m.sector_id WHERE m.symbol = 'RELIANCE'")
        again = await ST.sync_mappings(conn, D(2026, 11, 6))
    assert mapped + len(unmapped) == total and all(u["reason"] for u in unmapped)
    assert rel["sector_code"] == "oil_marketing" and "Refineries" in rel["basis_label"]                                   # AC01
    assert again["changed"] == 0                                                                                           # a second run changes nothing
    print("mapped", mapped, "of", total)


# ------------------------------------------------------------------------------------------------------------ routes
async def _admin(app):
    from finlit.auth import crypto
    a = await make_admin(app, "macro-boss@example.com")
    secret = (await a.post("/api/me/mfa/setup")).json()["secret"]
    assert (await a.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})).status_code == 200
    return a


@pytest.fixture
async def seeded(app):  # noqa: F811
    st = app.state.store
    await st.migrate()
    async with st.pool.acquire() as conn:
        await conn.execute(f"TRUNCATE {MO_TABLES} RESTART IDENTITY CASCADE")
        await conn.execute("DELETE FROM companies WHERE symbol IN ('ZZBANK', 'ZZUNK')")
        await conn.execute("INSERT INTO companies (symbol, name, sector, industry) VALUES ('ZZBANK', 'Zed Bank Ltd', 'Private Sector Bank', 'Banks'), ('ZZUNK', 'Zed Unknown', 'Quark Holdings', 'Qwerty')")
    await st.redis.flushdb()
    await load_macro(st)
    today = ST.today_ist()
    await ST.run(st, "test", today=today, reconstruct_months=3)
    return app


@pytest.mark.integration
async def test_ac01_ac06_ac08_ac09_company_page_endpoint(seeded, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("the company page must not touch the network")
    monkeypatch.setattr(socket.socket, "connect", no_network)                      # AC16: any outbound connection from the endpoint fails the test
    import httpx
    real = httpx.AsyncClient.send

    async def no_http(self, *a, **k):
        raise AssertionError("the company page must not call an external source")
    monkeypatch.setattr(httpx.AsyncClient, "send", no_http)
    async with new_client(seeded) as c:
        monkeypatch.setattr(httpx.AsyncClient, "send", real)                          # the test client itself is httpx: allow it, then block real sockets only
        r = await c.get("/api/stocks/ZZBANK/macro-outlook")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["status"] == "ok" and b["mapping"]["sector"] == "private_banks" and b["mapping"]["basis"] == "primary"       # AC01
        assert 0 <= b["score"] <= 100 and b["label"] in {x[1] for x in E.DEFAULT_BANDS} and b["tone"]                          # AC06
        assert E.band_of(b["score"], tuple((float(m), l) for m, l in E.DEFAULT_BANDS)) == b["label"]
        assert len(b["drivers"]) == 2 and abs(b["drivers"][0]["contribution"]) >= abs(b["drivers"][1]["contribution"]) and b["drivers"][0]["sign"] in "+-"      # AC07
        assert b["coverage"] >= 0.7 and b["modelVersion"] == 1 and b["asOf"] and b["snapshotDate"] and b["stale"]["isStale"] is False
        assert "not a company-specific assessment" in b["disclaimer"]
        inds = {i["code"]: i for i in b["indicators"]}
        assert len(inds) == 19 and inds["CPI"]["value"] == 5.54 and inds["CPI"]["unit"] == "%" and inds["CPI"]["source"] == "MoSPI" and inds["CPI"]["observationDate"] and inds["CPI"]["signal"] is not None     # AC09
        assert inds["BRENT"]["status"] == "Missing" and inds["BRENT"]["signal"] is None and inds["BRENT"]["value"] is None
        assert inds["BANK_CREDIT"]["sensitivity"]["coefficient"] == 0.75 and inds["BANK_CREDIT"]["sensitivity"]["critical"] is True                                       # AC04
        assert b["explanation"]["supporting"] is not None and "headline" in b["explanation"]
        u = (await c.get("/api/stocks/ZZUNK/macro-outlook")).json()
        assert u["status"] == "not_mapped" and "no label-map rule" in u["reason"]
        assert (await c.get("/api/stocks/NOSUCHCO/macro-outlook")).status_code == 404
        assert (await c.get("/api/stocks/bad%20symbol/macro-outlook")).status_code == 400
        assert (await c.get("/api/companies/ZZBANK/macro-outlook")).status_code == 200
        r2 = await c.get("/api/stocks/ZZBANK/macro-outlook", headers={"If-None-Match": r.headers["etag"]})
        assert r2.status_code == 304


@pytest.mark.integration
async def test_ac08_sector_impact_lists_all_sectors_sorted_with_filters(seeded):
    async with new_client(seeded) as c:
        b = (await c.get("/api/macro/sector-impact")).json()
        assert b["count"] == 35 and len(b["sectors"]) == 35
        scores = [s["score"] for s in b["sectors"] if s["score"] is not None]
        assert scores == sorted(scores, reverse=True)
        first_none = next(i for i, s in enumerate(b["sectors"]) if s["score"] is None)
        assert all(s["score"] is None for s in b["sectors"][first_none:])             # Insufficient Data sorts after every scored sector
        ins = next(s for s in b["sectors"] if s["status"] == "insufficient_data")
        assert ins["label"] == "Insufficient Data" and ins["score"] is None and ins["reason"]
        asc = (await c.get("/api/macro/sector-impact?order=asc")).json()["sectors"]
        assert [s["score"] for s in asc if s["score"] is not None][0] == scores[-1]
        nm = (await c.get("/api/macro/sector-impact?sort=name&order=asc")).json()["sectors"]
        assert [s["sector"]["name"].lower() for s in nm] == sorted(s["sector"]["name"].lower() for s in nm)
        assert (await c.get("/api/macro/sector-impact?q=bank")).json()["count"] == 2
        assert (await c.get("/api/macro/sector-impact?sort=bogus")).status_code == 422


@pytest.mark.integration
async def test_sector_indicator_history_and_methodology_routes(seeded):
    async with new_client(seeded) as c:
        d = (await c.get("/api/macro/sectors/real_estate/indicators")).json()
        assert d["sector"]["code"] == "real_estate" and len(d["contributions"]) == 8 and d["stale"]["isStale"] is False
        row = next(x for x in d["contributions"] if x["code"] == "REPO_RATE")
        assert row["coefficient"] == -1.0 and row["weight"] == 2.0 and row["critical"] is True and row["publicationDate"] and row["dateBasis"]
        async with seeded.state.store.pool.acquire() as conn:
            sid = await conn.fetchval("SELECT id FROM sector_master WHERE sector_code = 'real_estate'")
        assert (await c.get(f"/api/macro/sectors/{sid}/indicators")).json()["sector"]["code"] == "real_estate"
        assert (await c.get("/api/macro/sectors/nope/indicators")).status_code == 404
        h = (await c.get("/api/macro/sectors/real_estate/history?period=6M")).json()
        assert h["midpoint"] == 50 and h["points"] and set(h["points"][0]) >= {"date", "score", "label", "basis"}
        assert (await c.get("/api/macro/sectors/real_estate/history?period=9Y")).status_code == 422
        m = (await c.get("/api/macro/methodology")).json()
        assert m["modelVersion"] == 1 and len(m["formula"]) == 4 and "tanh" in m["formula"][2] and len(m["indicators"]) == 19 and "not validated" in m["assumptionsNote"]
        assert [b["label"] for b in m["bands"]][0] == "Strong Tailwind" and m["limitations"] and "recommendation" in m["disclaimer"]


@pytest.mark.integration
async def test_source_outage_serves_the_last_snapshot_with_a_stale_warning(seeded):
    st = seeded.state.store
    async with new_client(seeded) as c:
        fresh = (await c.get("/api/stocks/ZZBANK/macro-outlook")).json()
        async with st.pool.acquire() as conn:
            await conn.execute("INSERT INTO macro_run_log (trigger, status, error, finished_at) VALUES ('job', 'failed', 'source outage', now())")
        await st.redis.flushdb()
        b = (await c.get("/api/stocks/ZZBANK/macro-outlook")).json()
    assert b["stale"]["isStale"] and b["stale"]["reason"] == "refresh_failed" and "last successful snapshot" in b["stale"]["message"]
    assert b["score"] == fresh["score"] and b["snapshotDate"] == fresh["snapshotDate"]                  # the old score, with its own date, not presented as current


@pytest.mark.integration
async def test_a_failed_run_is_recorded_and_leaves_snapshots(seeded, monkeypatch):
    st = seeded.state.store

    async def boom(*a, **k):
        raise RuntimeError("source tables unreadable")
    monkeypatch.setattr(ST, "collect", boom)
    with pytest.raises(RuntimeError):
        await ST.run(st, "test", reconstruct_months=0)
    async with st.pool.acquire() as conn:
        last = await conn.fetchrow("SELECT status, error FROM macro_run_log ORDER BY id DESC LIMIT 1")
        n = await conn.fetchval("SELECT count(*) FROM sector_macro_scores")
    assert last["status"] == "failed" and "unreadable" in last["error"] and n >= 35


@pytest.mark.integration
async def test_ac12_diversified_company_is_revenue_weighted_only_where_data_is_reliable(seeded):
    st = seeded.state.store
    async with st.pool.acquire() as conn:
        await conn.execute("DELETE FROM companies WHERE symbol IN ('ZZDIV', 'ZZDIV2')")
        await conn.execute("INSERT INTO companies (symbol, name, sector, industry) VALUES ('ZZDIV', 'Zed Conglomerate', 'Diversified', 'Diversified'), ('ZZDIV2', 'Zed Retail Mix', 'Diversified', 'Diversified')")
        seg = lambda items: json.dumps({"latest": [{"name": n, "revenue": r} for n, r in items]})   # noqa: E731
        for sym, items in (("ZZDIV", [("Oil to Chemicals", 700.0), ("Digital Services", 200.0), ("Oil and Gas", 100.0)]), ("ZZDIV2", [("Retail", 500.0), ("Digital Services", 500.0)])):
            await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) VALUES ($1,'consolidated','segments',$2,'e',now()) ON CONFLICT DO NOTHING", sym, seg(items))
        await ST.sync_mappings(conn, ST.today_ist())
        n = await ST.sync_segments(conn, ST.today_ist())
    assert n["segmentRows"] == 3
    await st.redis.flushdb()
    async with new_client(seeded) as c:
        a = (await c.get("/api/stocks/ZZDIV/macro-outlook")).json()
        b = (await c.get("/api/stocks/ZZDIV2/macro-outlook")).json()
    assert a["mapping"]["basis"] == "revenue_weighted" and {s["sector"]: s["weight"] for s in a["segments"]} == {"oil_marketing": 0.7, "telecom": 0.2, "upstream_oil_gas": 0.1}
    assert a["status"] == "insufficient_data" and a["score"] is None                       # the oil sectors lack Brent: a weighted score would need 70% of revenue weight scored
    assert b["mapping"]["basis"] == "primary" and "not used" in b["mapping"]["note"] and b["status"] == "ok"                 # retail has no covered sector: no weights invented


# ------------------------------------------------------------------------------------------------------------ admin
@pytest.mark.integration
async def test_ac13_ac14_admin_edits_create_a_new_version_with_an_audit_trail(seeded):
    st = seeded.state.store
    anon = new_client(seeded)
    assert (await anon.post("/api/admin/macro/sector-sensitivity", json={"changes": [], "note": "x"})).status_code in (401, 403, 422)
    user = await signed_in(seeded, "macro-user@example.com")
    assert (await user.get("/api/admin/macro/overview")).status_code == 403
    assert (await user.post("/api/admin/macro/sector-sensitivity", json={"changes": [{"sector": "real_estate", "indicator": "WPI", "coefficient": -0.25}], "note": "test"})).status_code == 403
    admin = await _admin(seeded)
    async with new_client(seeded) as c:
        before = (await c.get("/api/stocks/ZZBANK/macro-outlook")).json()
    # validation
    bad = {"changes": [{"sector": "real_estate", "indicator": "WPI", "coefficient": 1.5}], "note": "too big"}
    assert (await admin.post("/api/admin/macro/sector-sensitivity", json=bad)).status_code == 422
    assert (await admin.post("/api/admin/macro/sector-sensitivity", json={"changes": [{"sector": "nope", "indicator": "WPI", "coefficient": .5}], "note": "unknown"})).status_code == 422
    # CSRF / Origin like every admin write
    no_csrf = new_client(seeded, headers={k: v for k, v in admin.headers.items() if k.lower() != "x-csrf-token"}, cookies=admin.cookies)
    assert (await no_csrf.post("/api/admin/macro/sector-sensitivity", json={"changes": [{"sector": "private_banks", "indicator": "GDP", "coefficient": .75}], "note": "no csrf"})).status_code == 403
    r = await admin.post("/api/admin/macro/sector-sensitivity", json={"changes": [{"sector": "private_banks", "indicator": "GDP", "coefficient": 1.0, "weight": 3.0}], "note": "raise GDP link"})
    assert r.status_code == 200 and r.json()["version"] == 2, r.text
    async with st.pool.acquire() as conn:
        act = await conn.fetch("SELECT model_version FROM macro_model_configuration WHERE active")
        v1 = await conn.fetchrow("SELECT x.coefficient, x.weight FROM sector_sensitivity x JOIN sector_master s ON s.id = x.sector_id WHERE x.model_version = 1 AND s.sector_code = 'private_banks' AND x.indicator_code = 'GDP'")
        v2 = await conn.fetchrow("SELECT x.coefficient, x.weight FROM sector_sensitivity x JOIN sector_master s ON s.id = x.sector_id WHERE x.model_version = 2 AND s.sector_code = 'private_banks' AND x.indicator_code = 'GDP'")
        audit = await conn.fetch("SELECT actor, action, entity_key, old_value, new_value, model_version, at FROM macro_audit_log WHERE action = 'sensitivity_change'")
        old_snap = await conn.fetchval("SELECT count(*) FROM sector_macro_scores WHERE model_version = 1")
        new_snap = await conn.fetchval("SELECT count(*) FROM sector_macro_scores WHERE model_version = 2")
    assert [a["model_version"] for a in act] == [2] and (float(v1["coefficient"]), float(v1["weight"])) == (0.5, 1.0) and (float(v2["coefficient"]), float(v2["weight"])) == (1.0, 3.0)
    assert len(audit) == 1 and audit[0]["actor"] == "macro-boss@example.com" and json.loads(audit[0]["old_value"])["coefficient"] == 0.5 and json.loads(audit[0]["new_value"])["coefficient"] == 1.0
    assert audit[0]["entity_key"] == "private_banks/GDP" and audit[0]["at"]
    assert old_snap > 0 and new_snap >= 35                                              # version 1 snapshots are untouched; version 2 has its own
    async with new_client(seeded) as c:
        after = (await c.get("/api/stocks/ZZBANK/macro-outlook")).json()
    assert after["modelVersion"] == 2 and before["modelVersion"] == 1 and after["score"] != before["score"]
    ov = (await admin.get("/api/admin/macro/overview")).json()
    assert [v["model_version"] for v in ov["versions"]] == [2, 1] and len(ov["health"]) == 19 and {h["status"] for h in ov["health"]} >= {"Available", "Missing"}
    # rollback keeps both versions, creates an audit row
    rb = await admin.post("/api/admin/macro/activate-version", json={"version": 1, "note": "rollback test"})
    assert rb.status_code == 200
    async with new_client(seeded) as c:
        assert (await c.get("/api/stocks/ZZBANK/macro-outlook")).json()["modelVersion"] == 1
    au = (await admin.get("/api/admin/macro/audit")).json()["events"]
    assert {"sensitivity_change", "model_version_created", "model_version_activated"} <= {e["action"] for e in au}


@pytest.mark.integration
async def test_admin_config_bands_k_coverage_mapping_and_label_rules(seeded):
    st = seeded.state.store
    admin = await _admin(seeded)
    assert (await admin.post("/api/admin/macro/config", json={"k": -1, "note": "bad"})).status_code == 422
    assert (await admin.post("/api/admin/macro/config", json={"bands": [{"min": 10, "label": "Only"}, {"min": 50, "label": "Two"}], "note": "no zero band"})).status_code == 422
    r = await admin.post("/api/admin/macro/config", json={"k": 2.5, "min_coverage": 0.5, "note": "calibration trial"})
    assert r.status_code == 200 and r.json()["version"] == 2
    async with st.pool.acquire() as conn:
        cfg, _ = await ST.load_config(conn)
        logs = {x["entity_key"] for x in await conn.fetch("SELECT entity_key FROM macro_audit_log WHERE action = 'config_change'")}
    assert cfg.version == 2 and cfg.k == 2.5 and cfg.min_coverage == 0.5 and {"k", "minCoverage"} <= logs
    ov = (await admin.get("/api/admin/macro/overview")).json()
    assert ov["config"]["k"] == 2.5
    # mapping
    assert (await admin.post("/api/admin/macro/mapping", json={"symbol": "ZZUNK", "sector": "nope"})).status_code == 422
    assert (await admin.post("/api/admin/macro/mapping", json={"symbol": "ZZUNK", "sector": "cement", "note": "reviewed"})).status_code == 200
    assert (await admin.post("/api/admin/macro/mapping", json={"symbol": "ZZUNK", "sector": "cement", "segments": [{"sector": "cement", "weight": .5}], "note": "bad weights"})).status_code == 422
    async with new_client(seeded) as c:
        b = (await c.get("/api/stocks/ZZUNK/macro-outlook")).json()
    assert b["mapping"]["sector"] == "cement" and b["mapping"]["source"] == "admin"
    await admin.post("/api/admin/macro/mapping", json={"symbol": "ZZUNK", "sector": None, "note": "back to rules"})
    # label rule
    lr = await admin.post("/api/admin/macro/label-map", json={"kind": "sector", "match": "exact", "pattern": "Quark Holdings", "sector": "telecom", "note": "review"})
    assert lr.status_code == 200 and lr.json()["pattern"] == "quark holdings"
    async with new_client(seeded) as c:
        assert (await c.get("/api/stocks/ZZUNK/macro-outlook")).json()["mapping"]["sector"] == "telecom"
    m = (await admin.get("/api/admin/macro/mapping?q=zz")).json()
    assert any(x["symbol"] == "ZZUNK" for x in m["rows"])
    con = (await admin.get("/api/admin/macro/contributions?sector=aviation")).json()
    assert con["snapshot"]["sector"]["code"] == "aviation" and con["contributions"] and con["recent"]
    rc = await admin.post("/api/admin/macro/recalculate")
    assert rc.status_code == 200 and rc.json()["status"] in ("ok", "partial")


@pytest.mark.integration
async def test_job_is_registered_never_switchable_off_and_has_a_freshness_dataset():
    from finlit.jobs import registry
    from finlit.jobs import freshness
    j = registry.by_name({})["macro-outlook"]
    assert j.args == ("refresh-macro-outlook",) and j.gate is None and j.sla.kind == "hours" and "macro" in j.prerequisites and j.probe == "macro-outlook" and j.owns == ("macro_outlook",)
    f = freshness.evaluate_facts({"macro_outlook_run": datetime.now(timezone.utc) - timedelta(hours=80), "expected": D(2026, 11, 5)}, datetime.now(timezone.utc))
    ds = {d["key"]: d for d in f["datasets"]}
    assert ds["macro_outlook"]["status"] == "stale"
