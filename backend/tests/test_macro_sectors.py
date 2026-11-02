"""Macro backdrop per sector: the owner's spec (1 Nov 2026) reproduced exactly from its own worked example, the company mapping, and the server rules
(Gold only, switched off for members until the owner turns it on, administrators always)."""
import time
from datetime import date, timedelta

import pytest

from finlit import macro, macro_sectors as ms
from test_auth import app, make_admin, new_client, signed_in  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401

# the spec, page 4: score, label and top reasons with the signals of page 2 (crude 0: not on the macro screens)
SPEC_SIGNALS = {"cpi": .89, "wpi_cpi": .88, "rates": 1.0, "growth": .01, "credit": 1.0, "funding": .5, "rupee": -.13, "food": 1.0, "unemployment": 0, "crude": 0}
SPEC_TABLE = {"Private banks": (84, "Strong tailwind", ["Credit +", "Rate hikes +"]), "Metals & mining": (75, "Strong tailwind", ["WPI-CPI +"]),
              "PSU banks": (73, "Strong tailwind", ["Rate hikes +", "Credit +"]), "Agri inputs": (68, "Tailwind", ["Food CPI +"]), "Upstream oil & gas": (62, "Tailwind", ["WPI-CPI +"]),
              "Specialty chemicals": (62, "Tailwind", ["WPI-CPI +"]), "Aviation": (54, "Neutral", ["No strong driver today"]),
              "Oil marketing cos. (OMCs)": (52, "Neutral", ["No strong driver today"]), "IT services": (46, "Neutral", ["No strong driver today"]),
              "Capital goods & infra": (36, "Headwind", ["Rate hikes -", "Credit +"]), "Pharma (export-led)": (34, "Headwind", ["WPI-CPI -"]),
              "Hotels & QSR": (34, "Headwind", ["Food CPI -", "CPI +"]), "Paints": (25, "Strong headwind", ["WPI-CPI -"]), "Real estate": (22, "Strong headwind", ["Rate hikes -", "Credit +"]),
              "Cement": (22, "Strong headwind", ["Rate hikes -", "WPI-CPI -"]), "NBFCs & housing finance": (17, "Strong headwind", ["Rate hikes -", "Credit +"]),
              "Autos": (15, "Strong headwind", ["Rate hikes -", "Credit +"]), "FMCG": (5, "Strong headwind", ["Food CPI -", "WPI-CPI -"])}


def spec_payload():
    """The macro page as the spec read it (page 2): CPI 5.54 (+0.71), WPI 11.39 (+1.47), repo 5.50 (+0.25), real repo -0.29, GDP 7.82 (-0.74), IIP 6.70 (-1.10),
    credit 18.2 and deposits 16.7, rupee 95.37 -> 95.25, food 5.7 -> 7.4, unemployment 5.0 flat."""
    card = lambda k, v, ch=None: {"key": k, "value": v, "change": ch}  # noqa: E731
    return {"today": "2026-11-01", "cards": [card("cpi", 5.54, .71), card("wpi", 11.39, 1.47), card("repo", 5.5, .25), card("real_rate", -.29, -.71), card("gdp", 7.82, -.74),
                                             card("iip", 6.70, -1.10), card("unemployment", 5.0, 0.0), card("credit_yoy", 18.2)],
            "series": {"credit_yoy": {"points": [["2026-10-15", 18.2]]}, "deposits_yoy": {"points": [["2026-10-15", 16.7]]}, "usdinr": {"points": [["2026-10-31", 95.37], ["2026-11-01", 95.25]]}},
            "cpiDivisions": [{"key": "cpi_div_01", "label": "Food and beverages", "points": [["2026-08-31", 5.7], ["2026-09-30", 7.4]]}]}


def test_the_spec_table_comes_out_exactly():
    rows = {r["name"]: r for r in ms.score_sectors(SPEC_SIGNALS)}
    assert len(rows) == 18
    for name, (score, label, reasons) in SPEC_TABLE.items():
        assert (round(rows[name]["score"]), rows[name]["label"], rows[name]["reasons"]) == (score, label, reasons), name


def test_the_signals_come_from_the_macro_page_as_the_spec_works_them_out():
    r = ms.readings(spec_payload())
    got = {k: v["signal"] for k, v in r.items()}
    for k, want in {"cpi": .89, "wpi_cpi": .88, "rates": 1.0, "growth": .01, "credit": 1.0, "funding": .5, "rupee": -.13, "food": 1.0, "unemployment": 0.0}.items():
        assert got[k] == pytest.approx(want, abs=0.006), k
    assert got["crude"] is None and "Brent" in r["crude"]["reason"]                       # no crude history: left out with its reason, never a zero reading
    assert ms.readings(spec_payload(), crude_pct_3m=15.0)["crude"]["signal"] == 1.0           # Brent up 15% in three months = full signal
    out = ms.build(spec_payload(), crude_pct_3m=15.0)
    by = {s["name"]: round(s["score"]) for s in out["sectors"]}
    assert by["Upstream oil & gas"] == 86 and by["Specialty chemicals"] == 30 and by["Oil marketing cos. (OMCs)"] == 22   # the spec's crude example, page 5
    assert "not a recommendation" in out["disclaimer"] and "Information only, not investment advice" in out["disclaimer"]


def test_missing_readings_are_left_out_with_a_reason():
    r = ms.readings({"cards": [], "series": {}})
    assert all(v["signal"] is None and v["reason"] for v in r.values())
    assert {s["score"] for s in ms.score_sectors({k: None for k in ms.KEYS})} == {50.0}           # nothing known: every sector neutral


@pytest.mark.parametrize("name,sector,industry,key", [
    ("HDFC Bank Ltd", "Financial Services", "Private Sector Bank", "private_banks"), ("State Bank of India", "Financial Services", "Public Sector Bank", "psu_banks"),
    ("Punjab National Bank", "Financial Services", "Banks", "psu_banks"), ("Bajaj Finance Ltd", "Financial Services", "Non Banking Financial Company (NBFC)", "nbfc"),
    ("Infosys", "Information Technology", "Computers - Software & Consulting", "it"), ("Asian Paints", "Consumer Durables", "Paints", "paints"),
    ("UltraTech", "Construction Materials", "Cement & Cement Products", "cement"), ("Reliance Industries Ltd", "Energy", "Refineries & Marketing", "omc"),
    ("ONGC", "Energy", "Oil Exploration & Production", "upstream"), ("InterGlobe Aviation", "Services", "Airline", "aviation"), ("Tata Steel", "Metals & Mining", "Iron & Steel", "metals"),
    ("Mazagon Dock", "Capital Goods", "Ship Building & Allied Services", "capital_goods"), ("Maruti", "Automobile and Auto Components", "Passenger Cars & Utility Vehicles", "autos"),
    ("SRF", "Chemicals", "Specialty Chemicals", "chemicals"), ("Coromandel", "Chemicals", "Fertilizers", "agri"), ("Some Holding Co", "Diversified", "Diversified", None), (None, None, None, None)])
def test_a_company_maps_to_its_sector_or_to_none(name, sector, industry, key):
    assert ms.sector_for(name, sector, industry) == key


async def _admin(app):
    from finlit.auth import crypto
    a = await make_admin(app, "macro-admin@example.com")
    secret = (await a.post("/api/me/mfa/setup")).json()["secret"]
    assert (await a.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})).status_code == 200
    return a


@pytest.mark.integration
async def test_the_route_is_off_for_members_until_switched_on_and_gold_only(app):
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE feature_flags SET enabled = false WHERE name = 'macro_sectors'")
        await macro.set_meta(conn, "payload", spec_payload())
        await conn.execute("DELETE FROM companies WHERE symbol IN ('ZZBANK', 'ZZHOLD')")
        await conn.execute("INSERT INTO companies (symbol, name, sector, industry) VALUES ('ZZBANK', 'Zed Bank Ltd', 'Financial Services', 'Private Sector Bank'), ('ZZHOLD', 'Zed Holdings', 'Diversified', 'Diversified')")
    ms._flag["at"] = 0.0
    gold, silver = await signed_in(app, "macro-g@example.com", plan="gold"), await signed_in(app, "macro-s@example.com", plan="silver")
    assert (await gold.get("/api/macro/sectors")).status_code == 404                             # switched off: members see nothing yet
    admin = await _admin(app)
    a = await admin.get("/api/macro/sectors?symbol=zzbank")
    assert a.status_code == 200 and a.json()["switchedOn"] is False                               # the owner can review it first
    body = a.json()
    assert len(body["sectors"]) == 18 and body["company"]["sectorKey"] == "private_banks" and round(body["company"]["sector"]["score"]) == 84
    assert (await admin.put("/api/admin/features/macro_sectors", json={"enabled": True})).status_code == 200
    ms._flag["at"] = 0.0
    g = (await gold.get("/api/macro/sectors?symbol=ZZHOLD")).json()
    assert g["switchedOn"] is True and g["company"]["sector"] is None and "not one of the 18 sectors" in g["company"]["reason"]
    assert (await silver.get("/api/macro/sectors")).status_code == 403                            # the server enforces the plan
    assert (await new_client(app).get("/api/macro/sectors")).status_code == 403
    assert (await gold.get("/api/macro/sectors?symbol=bad%20one")).status_code == 422
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE feature_flags SET enabled = false WHERE name = 'macro_sectors'")
    ms._flag["at"] = 0.0
