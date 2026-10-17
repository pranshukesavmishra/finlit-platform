"""Serves the built website (frontend/dist) from the same origin as the API.

One host for pages and /api means no cross-site cookies and no CORS, which is what makes a single free container work.
The API keeps its own strict JSON headers; website files get the site's policy instead (same rules as frontend/public/_headers).
Unknown paths fall back to the app shell so client-side routes (/stocks/TCS) work on refresh; /api/* never does.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response

SITE_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
                                "img-src 'self' data: https:; connect-src 'self'; frame-src 'self'; worker-src 'self'; manifest-src 'self'; "
                                "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
}


def _cache_control(rel: str) -> str:
    if rel.startswith("assets/"):
        return "public, max-age=31536000, immutable"  # hashed file names
    if rel in ("index.html", "sw.js", "theme-init.js"):
        return "no-cache"
    return "public, max-age=3600"


def mount_frontend(app: FastAPI, dist: Path) -> bool:
    """Add the catch-all website route. Call last, after every /api route exists. Returns False when there is no build."""
    root = dist.resolve()
    index = root / "index.html"
    if not index.is_file():
        return False

    @app.get("/{path:path}", include_in_schema=False)
    async def website(path: str, request: Request):
        if path == "api" or path.startswith("api/"):
            return JSONResponse({"status": "not_found"}, status_code=404, headers={"Cache-Control": "no-store"})
        target = (root / path).resolve()
        if path and target.is_file() and root in target.parents:
            rel = target.relative_to(root).as_posix()
        else:
            target, rel = index, "index.html"  # app shell; the page itself shows its own "not found"
        response: Response = FileResponse(target)
        response.headers["Cache-Control"] = _cache_control(rel)
        for key, value in SITE_HEADERS.items():
            response.headers[key] = value
        return response

    return True
