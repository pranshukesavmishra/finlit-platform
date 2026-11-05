"""Example web API for the two indicators (Flask). Your team can copy the idea into Django or FastAPI.

Two ways to serve:
  precomputed (recommended): every evening update NSE's files and run the batch; the app then returns
  site_data/<SYMBOL>.json in milliseconds
      python -m finlit_technicals fetch-nse --dir nse
      python -m finlit_technicals batch --nse nse --out site_data
  live: when there is no precomputed file, or the request has ?cap= / ?mcap=, it computes from the prices
      (about half a second per indicator; the first sector request builds the market panel, ~30 s)

Run:  FINLIT_NSE=nse FINLIT_OUT=site_data flask --app examples/flask_app.py run
      (or FINLIT_PRICES=prices for a CsvFolder instead of NSE's files)
  GET /api/technicals/SAMBHV/score          ST/LT scores, components, trend alignment, peer row
  GET /api/technicals/SAMBHV/peers          leader / laggard, peers table, weekly history
  GET /api/technicals/SAMBHV/peers?cap=small&table=all
  GET /api/technicals/SAMBHV/sector         the stock inside its industry (6-month quarter, leader flag ...)
  GET /api/technicals/summary               one line per stock (from the batch), for screeners
  GET /api/sectors                          Sector Pulse: every industry's state, breadth and leader flags
  GET /api/sectors/ferrous-metals           one industry page (slug of the NSE industry or sector group name)
  GET /api/rotation                         Sector rotation: corners, ranking with rank changes, paths, study
  GET /api/rotation/banks                   one group's rotation card (industry page, stock page)
  GET /api/stress/presets                   Stress Lab preset scenarios
  GET /api/stress/ASIANPAINT                Stress Lab page: today + every preset, breaking points, sensitivities
  GET /api/stress/ASIANPAINT/run?preset=2022&rate_bp=300     one scenario, sliders as query parameters
  GET /api/stress/compare?a=ASIANPAINT&b=BERGEPAINT&preset=today
  GET  /api/ownership/RELIANCE/insights     Ownership card: table, facts, signals, headline (from a saved pack)
  POST /api/ownership/insights              same, from {"ownership": <site JSON>, "premium": <premium fundamentals JSON>}
  GET  /api/ownership/rules                 the 21 rules, for the "How we read a filing" page
  GET  /api/company-brief/RELIANCE          the reviewed company brief (only if it passed validate() and check())
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from flask import Flask, abort, jsonify, request

from finlit_technicals import Cached, CsvFolder, NseHistory, SectorEngine, canonical, company_brief, ownership, peer_label, score, stress


def create_app(prices: str | None = None, site_data: str | None = None, nse: str | None = None) -> Flask:
    app = Flask(__name__)
    app.json.sort_keys = False                       # keep the components in the indicator's order
    nse = nse or os.environ.get("FINLIT_NSE")
    src = Cached(NseHistory(nse) if nse else CsvFolder(prices or os.environ.get("FINLIT_PRICES", "prices")))
    out = Path(site_data or os.environ.get("FINLIT_OUT", "site_data"))

    engine = {}

    def sectors() -> SectorEngine:
        # one engine per process: it computes each industry once (restart the app after new prices, or rely on the batch)
        if "e" not in engine:
            engine["e"] = SectorEngine(src)
        return engine["e"]

    def read_json(p: Path):
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def precomputed(symbol: str):
        p = out / f"{canonical(symbol)}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def live_args():
        mcap = request.args.get("mcap", type=float)
        return {"cap": request.args.get("cap"), "market_cap_cr": mcap}

    @app.get("/api/technicals/<symbol>/score")
    def api_score(symbol):
        if not request.args:
            pre = precomputed(symbol)
            if pre:
                return jsonify(pre["score"])
        try:
            return jsonify(score(symbol, src, **live_args()))
        except LookupError as e:
            abort(404, str(e))
        except ValueError as e:
            abort(400, str(e))

    @app.get("/api/technicals/<symbol>/peers")
    def api_peers(symbol):
        if not request.args:
            pre = precomputed(symbol)
            if pre:
                return jsonify(pre["peers"])
        try:
            return jsonify(peer_label(symbol, src, table=request.args.get("table", "top10"),
                                      history_weeks=request.args.get("weeks", 52, type=int), **live_args()))
        except LookupError as e:
            abort(404, str(e))
        except ValueError as e:
            abort(400, str(e))

    @app.get("/api/technicals/<symbol>/sector")
    def api_stock_sector(symbol):
        pre = precomputed(symbol)
        if pre and pre.get("sector"):
            return jsonify(pre["sector"])
        try:
            return jsonify(sectors().stock(symbol))
        except LookupError as e:
            abort(404, str(e))

    @app.get("/api/sectors")
    def api_board():
        pre = read_json(out / "sectors" / "_board.json")
        return jsonify(pre if pre else sectors().board())

    rot = {}

    def rotation():
        from finlit_technicals.rotation import Rotation
        if "r" not in rot:
            rot["r"] = Rotation(sectors())
        return rot["r"]

    @app.get("/api/rotation")
    def api_rotation():
        pre = read_json(out / "rotation" / "_map.json")
        return jsonify(pre if pre else rotation().view())

    @app.get("/api/rotation/<name>")
    def api_rotation_group(name):
        if not re.fullmatch(r"[a-z0-9-]{1,80}", name.lower()):
            abort(404, "unknown group")
        pre = read_json(out / "rotation" / f"{name.lower()}.json")
        if pre:
            return jsonify(pre)
        try:
            return jsonify(rotation().group_view(name))
        except LookupError as e:
            abort(404, str(e))

    @app.get("/api/sectors/<name>")
    def api_industry(name):
        if not re.fullmatch(r"[a-z0-9-]{1,80}", name.lower()):
            abort(404, "unknown industry")
        pre = read_json(out / "sectors" / f"{name.lower()}.json")
        if pre:
            return jsonify(pre)
        try:
            return jsonify(sectors().industry(name, history_sessions=request.args.get("sessions", 260, type=int)))
        except LookupError as e:
            abort(404, str(e))

    @app.get("/api/technicals/summary")
    def api_summary():
        p = out / "_summary.json"
        if not p.exists():
            abort(404, "no batch output yet: run python -m finlit_technicals batch")
        return jsonify(json.loads(p.read_text(encoding="utf-8")))

    # ---- Stress Lab: packs/<SYMBOL>.json and today.json are written by the nightly job (README section 7)
    packs = Path(os.environ.get("FINLIT_STRESS_PACKS", "stress_packs"))
    stress_out = Path(os.environ.get("FINLIT_STRESS_OUT", str(out / "stress")))
    today_file = packs / "_today.json"
    limits = {"crude": (-90, 300), "usdinr": (-30, 50), "cpi": (-5, 15), "wpi": (-10, 25), "rate_bp": (-500, 1000),
              "demand": (-60, 30), "erp_bp": (-300, 600), "metals": (-60, 200), "agri": (-10, 25)}

    def stress_company(symbol: str):
        sym = re.sub(r"[^A-Z0-9&_-]", "", symbol.upper())
        p = packs / f"{sym}.json"
        if not p.exists():
            abort(404, f"no Stress Lab data for {sym}")
        try:
            return stress.company_from_pack(json.loads(p.read_text(encoding="utf-8")))
        except ValueError as e:
            abort(422, str(e))

    def stress_scenario(co):
        name = request.args.get("preset")
        if name == "today":
            if not today_file.exists():
                abort(404, "today's inputs not built yet")
            sc = stress.load_today(str(today_file), co.base_end)
        elif name:
            if name not in stress.PRESETS:
                abort(400, f"unknown preset {name}")
            sc = stress.replace(stress.PRESETS[name])
        else:
            sc = stress.Scenario()
        for k, (lo, hi) in limits.items():
            v = request.args.get(k, type=float)
            if v is not None:
                setattr(sc, k, max(lo, min(hi, v)))
                sc.name = "Custom" if not name else f"{sc.name} (adjusted)"
        rv = request.args.get("rupee", type=float)       # the prototype's slider: rupee value, -8 = 8% weaker
        if rv is not None and request.args.get("usdinr") is None:
            rv = max(-33.0, min(43.0, rv))
            sc.usdinr = (1 / (1 + rv / 100) - 1) * 100
            sc.name = "Custom" if not name else f"{sc.name} (adjusted)"
        if request.args.get("persistence") in ("one_year", "permanent"):
            sc.persistence = request.args["persistence"]
        return sc

    @app.get("/api/stress/presets")
    def api_stress_presets():
        return jsonify({k: stress.scenario_dict(v) for k, v in stress.PRESETS.items()})

    @app.get("/api/stress/<symbol>")
    def api_stress_page(symbol):
        pre = stress_out / f"{symbol.upper()}.json"
        if pre.exists() and not request.args:
            return jsonify(json.loads(pre.read_text(encoding="utf-8")))
        co = stress_company(symbol)
        scs = dict(stress.PRESETS)
        if today_file.exists():
            scs = {"today": stress.load_today(str(today_file), co.base_end), **scs}
        return jsonify(stress.stress_page(co, scs))

    @app.get("/api/stress/<symbol>/run")
    def api_stress_run(symbol):
        co = stress_company(symbol)
        r = stress.run(co, stress_scenario(co))
        r["explain"] = stress.explain(r)
        return jsonify(r)

    @app.get("/api/stress/compare")
    def api_stress_compare():
        a, b = request.args.get("a"), request.args.get("b")
        if not (a and b):
            abort(400, "give ?a=SYMBOL&b=SYMBOL")
        ca, cb = stress_company(a), stress_company(b)
        return jsonify(stress.compare(ca, cb, stress_scenario(ca)))

    # ---- Ownership insights: packs saved by the nightly job (ownership.pack_from_site), or posted live ----
    own_dir = Path(os.environ.get("FINLIT_OWNERSHIP", "ownership_packs"))

    @app.get("/api/ownership/rules")
    def api_ownership_rules():
        return jsonify({"rules_version": ownership.RULES_VERSION, "rules": ownership.rules_table()})

    @app.get("/api/ownership/<symbol>/insights")
    def api_ownership_saved(symbol):
        if not re.fullmatch(r"[A-Za-z0-9&_.-]{1,30}", symbol):
            abort(400, "bad symbol")
        p = own_dir / f"{symbol.upper()}.json"
        if not p.exists():
            abort(404, f"no ownership pack for {symbol.upper()}")
        return jsonify(ownership.analyse(json.loads(p.read_text(encoding="utf-8"))))

    @app.post("/api/ownership/insights")
    def api_ownership_live():
        body = request.get_json(silent=True) or {}
        if not isinstance(body.get("ownership"), dict):
            abort(400, 'send {"ownership": ..., "premium": ...}')
        return jsonify(ownership.analyse(ownership.pack_from_site(body["ownership"], body.get("premium"))))

    # ---- Company brief: JSON files written by the brief job and reviewed by a person ----
    brief_dir = Path(os.environ.get("FINLIT_BRIEFS", "briefs"))

    @app.get("/api/company-brief/<symbol>")
    def api_company_brief(symbol):
        if not re.fullmatch(r"[A-Za-z0-9&_.-]{1,30}", symbol):
            abort(400, "bad symbol")
        p = brief_dir / f"{symbol.upper()}.json"
        if not p.exists():
            abort(404, f"no company brief for {symbol.upper()}")
        brief = json.loads(p.read_text(encoding="utf-8"))
        checks = brief.get("checks") or {}
        if company_brief.validate(brief) or checks.get("passed") != checks.get("citations"):
            abort(409, "brief has not passed its checks")
        return jsonify(brief)

    return app


app = create_app()
