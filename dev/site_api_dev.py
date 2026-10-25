"""Run the FinLit site backend (site-api/backend/server.py) locally for frontend work.

    /path/to/site-venv/bin/python dev/site_api_dev.py --backend site-api/backend --port 8001

DEVELOPMENT ONLY. MongoDB is replaced in-process by mongomock-motor (data lives in memory and is lost on
exit), and a dev admin login is created. Production runs the same server.py against a real MongoDB, or without one
(MONGO_URL unset: the blog/CMS and forms answer 503, FinLit Prism still works); --no-mongo runs that way here.

FinLit Prism (the premium reports) without provider keys: --prism-fixtures (the default when FINEDGE_API_KEY is empty
or "dev", or FINEDGE_MODE=fixtures) answers FinEdge from recorded responses for eight companies (RELIANCE, TCS, MARUTI,
NTPC, DLF, HDFCBANK, BAJFINANCE, HDFCLIFE); see dev/prism_fixtures.py. Any other company is "not found".
--no-prism-fixtures uses the real FinEdge API with FINEDGE_API_KEY.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import bcrypt


def _fixtures_by_default() -> bool:
    key = os.environ.get("FINEDGE_API_KEY", "").strip()
    return not key or key == "dev" or os.environ.get("FINEDGE_MODE", "").strip() == "fixtures"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, help="path to site-api/backend")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--no-mongo", action="store_true", help="run without any MongoDB, as production does when MONGO_URL is unset")
    parser.add_argument("--prism-fixtures", action=argparse.BooleanOptionalAction, default=None,
                        help="answer FinEdge from recorded responses (default: on when FINEDGE_API_KEY is empty or 'dev')")
    args = parser.parse_args()
    backend = Path(args.backend).resolve()
    prism_fixtures = _fixtures_by_default() if args.prism_fixtures is None else args.prism_fixtures

    if args.no_mongo:
        os.environ.pop("MONGO_URL", None)
    else:
        os.environ.setdefault("MONGO_URL", "mongodb://in-memory")
    os.environ.setdefault("DB_NAME", "finlit_dev")
    os.environ.setdefault("CMS_ADMIN_EMAIL", "admin@finlit-dev.com")
    os.environ.setdefault("CMS_ADMIN_PASSWORD_HASH", bcrypt.hashpw(b"dev-only-password", bcrypt.gensalt(4)).decode())
    os.environ.setdefault("CMS_JWT_SECRET", "dev-only-secret-" + "x" * 32)

    if not args.no_mongo:
        import motor.motor_asyncio
        from mongomock_motor import AsyncMongoMockClient

        motor.motor_asyncio.AsyncIOMotorClient = lambda *a, **k: AsyncMongoMockClient()  # type: ignore
    sys.path.insert(0, str(backend))
    sys.path.insert(1, str(Path(__file__).resolve().parent))
    os.chdir(backend)
    import server  # noqa: E402  (the real site backend)

    if prism_fixtures:
        import prism_fixtures as fixtures  # noqa: E402

        symbols = fixtures.install(server, backend)
        print(f"[site_api_dev] FinEdge answers from recorded fixtures; Prism companies: {', '.join(symbols)}", flush=True)

    if not args.no_mongo:
        @server.app.on_event("startup")
        async def seed():
            if await server.db.content.count_documents({}):
                return
            now = datetime.now(timezone.utc).isoformat()
            samples = [
                ("Reading a balance sheet in ten minutes", "A practical walk through assets, liabilities and what they say about risk."),
                ("Why cash conversion matters more than profit", "Profit is an opinion; cash is a fact. How to check one against the other."),
                ("Margin of safety in Indian mid-caps", "How we size positions when the range of outcomes is wide."),
            ]
            for i, (title, excerpt) in enumerate(samples):
                await server.db.content.insert_one({
                    "id": str(uuid4()), "title": title, "slug": title.lower().replace(" ", "-"), "excerpt": excerpt,
                    "author": "Nishant Jain", "contentType": "ARTICLE", "articleFormat": "HTML",
                    "articleBody": f"<p>{excerpt}</p><p>Development sample article.</p>",
                    "status": "PUBLISHED", "createdAt": now, "updatedAt": now, "publishedAt": now, "createdBy": "dev",
                })

    import uvicorn
    uvicorn.run(server.app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
