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
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from flask import Flask, abort, jsonify, request

from finlit_technicals import Cached, CsvFolder, NseHistory, SectorEngine, canonical, peer_label, score


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

    return app


app = create_app()
