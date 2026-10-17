import pytest

from finlit.auth import crypto
from finlit.auth.entitlements import LIMITS, has, redact_section, redact_universe, varies_by_plan

RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of "12345678901234567890"


def test_totp_matches_rfc6238_vector():
    assert crypto.totp_code(RFC_SECRET, 59 // 30) == "287082"
    assert crypto.totp_code(RFC_SECRET, 1111111109 // 30) == "081804"


def test_totp_rejects_replay_and_old_codes():
    step = crypto.verify_totp(RFC_SECRET, "287082", 0, now=59)
    assert step == 1
    assert crypto.verify_totp(RFC_SECRET, "287082", step, now=59) is None  # same code cannot be used twice
    assert crypto.verify_totp(RFC_SECRET, "287082", 0, now=59 + 300) is None  # outside the drift window
    assert crypto.verify_totp(RFC_SECRET, "abcdef", 0, now=59) is None


async def test_password_hash_roundtrip_and_rules():
    h = await crypto.hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$")
    assert await crypto.verify_password(h, "correct horse battery staple") is True
    assert await crypto.verify_password(h, "wrong") is False
    assert crypto.password_problem("short", "a@b.com")
    assert crypto.password_problem("password123", "a@b.com")
    assert crypto.password_problem("alicewonder99", "alicewonder@x.com")
    assert crypto.password_problem("a-long-unusual-phrase-42", "a@b.com") is None


def test_email_normalisation():
    assert crypto.normalise_email("  Me@Example.COM ") == "me@example.com"
    for bad in ("", "no-at", "a@b", "a b@c.com", "x" * 300 + "@a.com"):
        assert crypto.normalise_email(bad) is None


def test_secret_encryption_roundtrip():
    key = "k" * 40
    enc = crypto.encrypt_secret(key, RFC_SECRET)
    assert RFC_SECRET not in enc and crypto.decrypt_secret(key, enc) == RFC_SECRET
    assert crypto.decrypt_secret("other" * 10, enc) is None


def test_tokens_are_hashed_and_unique():
    (a, ah), (b, bh) = crypto.new_token(), crypto.new_token()
    assert a != b and len(a) >= 32 and ah == crypto.token_hash(a) and ah != a and len(ah) == 64 and ah != bh


def _summary():
    return {"score": {"overall": 72, "band": {"key": "healthy", "label": "Healthy"},
                      "pillars": [{"id": "q", "score": 70, "band": {"key": "healthy", "label": "Healthy"}}]},
            "thesis": "Strong", "strengths": ["a"], "watchouts": ["b"]}


def test_plan_ranking_and_limits():
    assert has("gold", "silver") and has("silver", "silver") and not has("basic", "silver") and not has("silver", "gold")
    assert LIMITS["basic"]["watchlist_symbols"] == 0 < LIMITS["silver"]["watchlist_symbols"] < LIMITS["gold"]["watchlist_symbols"]


def test_summary_redaction_per_plan():
    basic = redact_section("summary", _summary(), "basic")
    assert basic["score"]["overall"] is None and basic["thesis"] is None and basic["strengths"] == [] and basic["watchouts"] == []
    assert basic["score"]["pillars"][0]["score"] is None
    silver = redact_section("summary", _summary(), "silver")
    assert silver["score"]["overall"] == 72 and silver["thesis"] == "Strong"


def test_ratio_and_price_redaction():
    ratios = {"history": {"rows": {k: [1] for k in ("roe", "roce", "debt_to_equity", "gross_margin")}},
              "valuationHistory": {"rows": {"pe": [1]}, "periods": ["FY24"]}, "latest": {"a": 1},
              "groups": [{"id": "leverage", "keys": ["x", "y", "z"]}], "score": {"overall": 70, "pillars": [{"score": 1, "inputs": [1]}]}}
    silver = redact_section("ratios", __import__("copy").deepcopy(ratios), "silver")
    assert set(silver["history"]["rows"]) == {"roe", "roce", "gross_margin"} and silver["valuationHistory"]["rows"] == {}
    basic = redact_section("ratios", __import__("copy").deepcopy(ratios), "basic")
    assert set(basic["history"]["rows"]) == {"roe", "roce", "gross_margin"} and basic["score"]["overall"] is None
    gold = redact_section("ratios", __import__("copy").deepcopy(ratios), "gold")
    assert "debt_to_equity" in gold["history"]["rows"]
    price = {"technical": {"price": 1, "ema50": 2, "ema200": 3, "rsi": 50, "vsEma200Pct": 1.2}, "series": {"t": [1], "ema200": [1]}}
    out = redact_section("price-1Y", price, "silver")
    assert set(out["technical"]) == {"price", "ema50", "vsEma200Pct"} and "ema200" not in out["series"]
    seg = redact_section("segments", {"segments": {"a": 1}, "latest": [1], "periods": ["x"]}, "silver")
    assert seg["segments"] == {} and seg["periods"] == []


def test_universe_redaction_keeps_showcase():
    rows = [{"symbol": "RELIANCE", "overall": 62, "band": "healthy"}, {"symbol": "TCS", "overall": 80, "band": "strong"}]
    out = redact_universe(rows, "basic", {"RELIANCE"})
    assert out[0]["overall"] == 62 and out[1]["overall"] is None and out[1]["band"] is None
    assert redact_universe(rows, "silver", {"RELIANCE"}) == rows


def test_which_sections_vary():
    assert varies_by_plan("summary") and varies_by_plan("price-5Y") and not varies_by_plan("financials")


def test_price_statistics_are_a_silver_feature():
    assert varies_by_plan("stats")
    basic = redact_section("stats", {"available": True, "monthly": {"years": [2024]}}, "basic")
    assert basic == {"available": False, "locked": True}
    assert redact_section("stats", {"available": True, "monthly": 1}, "silver")["monthly"] == 1


def test_announcements_are_sorted_into_results_documents_and_news():
    from finlit.feed import classify, dedupe_key, rows_from_announcements
    assert classify("Financial Results", "Outcome of board meeting") == "result"
    assert classify("Analyst / Investor Meet", "Presentation to analysts") == "document"
    assert classify("Credit Rating", "informed the Exchange about Credit Rating") == "news"
    a = [{"date": "2026-09-25", "category": "Credit Rating", "description": "Reliance has informed the Exchange about Credit Rating", "link": "https://x.example/a.pdf"}]
    rows = rows_from_announcements("RELIANCE", "Reliance Industries Ltd", a)
    assert rows[0][0] == "news" and rows[0][2] == "RELIANCE" and rows[0][-1] == dedupe_key("RELIANCE", "2026-09-25", a[0]["description"], a[0]["link"])
