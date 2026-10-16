"""Run the existing FinLit site backend (Financial-Portfolio/backend/server.py) locally for frontend work.

    /path/to/venv/bin/python dev/site_api_dev.py --backend ../financial-portfolio/backend --port 8001

DEVELOPMENT ONLY. MongoDB is replaced in-process by mongomock-motor (data lives in memory and is lost on
exit), and a dev admin login is created. Production runs the same server.py against a real MongoDB.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import bcrypt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, help="path to Financial-Portfolio/backend")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    backend = Path(args.backend).resolve()

    os.environ.setdefault("MONGO_URL", "mongodb://in-memory")
    os.environ.setdefault("DB_NAME", "finlit_dev")
    os.environ.setdefault("CMS_ADMIN_EMAIL", "admin@finlit-dev.com")
    os.environ.setdefault("CMS_ADMIN_PASSWORD_HASH", bcrypt.hashpw(b"dev-only-password", bcrypt.gensalt(4)).decode())
    os.environ.setdefault("CMS_JWT_SECRET", "dev-only-secret-" + "x" * 32)

    import motor.motor_asyncio
    from mongomock_motor import AsyncMongoMockClient

    motor.motor_asyncio.AsyncIOMotorClient = lambda *a, **k: AsyncMongoMockClient()  # type: ignore
    sys.path.insert(0, str(backend))
    os.chdir(backend)
    import server  # noqa: E402  (the real site backend)

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
