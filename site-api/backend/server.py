from fastapi import FastAPI, APIRouter, HTTPException, Depends, File, UploadFile, Query, Request, BackgroundTasks
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator
from typing import Any, Dict, List, Optional
from typing import Literal
import uuid
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from time import monotonic, time, sleep
from urllib.parse import quote, urlparse
import asyncio
import base64
import contextvars
import copy
import threading
import zlib
import bcrypt
from functools import lru_cache
import hashlib
import secrets
import jwt
import nh3
import re
import json
import math
import requests
import csv
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from html import escape
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import FileResponse, JSONResponse, Response
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from starlette.concurrency import run_in_threadpool
try:
    from backend.email_service import send_lead_emails, send_service_enquiry_email, EmailNotConfigured
    from backend.portfolio_report import read_current_portfolio_report, save_portfolio_upload
    from backend.market_data import ENDPOINTS as MARKET_ENDPOINTS, market_params, normalize_market_payload
    from backend import mcp_tools
except ModuleNotFoundError:
    from email_service import send_lead_emails, send_service_enquiry_email, EmailNotConfigured
    from portfolio_report import read_current_portfolio_report, save_portfolio_upload
    from market_data import ENDPOINTS as MARKET_ENDPOINTS, market_params, normalize_market_payload
    import mcp_tools

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')
CONTENT_STORAGE_DIR = ROOT_DIR / "content_uploads"
CONTENT_STORAGE_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _env_int(name, default, low, high):
    """A whole-number setting from the environment, clamped to [low, high]; blank or invalid means the default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return min(high, max(low, int(raw)))
    except ValueError:
        logger.warning("%s is not a whole number; using %s", name, default)
        return default


# MongoDB connection. Optional: without MONGO_URL the server still starts, because FinLit Prism (the premium reports), the
# fundamentals tools and the market data need no database. Every database call then fails at once with MongoNotConfigured,
# which the handler below turns into a 503 (no connection attempt, no 5-second server-selection wait).
class MongoNotConfigured(ServerSelectionTimeoutError):
    """MONGO_URL is not set. A ServerSelectionTimeoutError, so routes that already degrade when MongoDB is unreachable degrade the same way."""


class _UnconfiguredCollection:
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        def unavailable(*_args, **_kwargs):
            raise MongoNotConfigured(f"MONGO_URL is not set (collection {self._name}.{attr})")
        return unavailable


class _UnconfiguredDatabase:
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _UnconfiguredCollection(name)

    __getitem__ = __getattr__


class _UnconfiguredClient:
    def __getitem__(self, _name):
        return _UnconfiguredDatabase()

    def close(self):
        pass


mongo_url = os.environ.get('MONGO_URL', '').strip()
if mongo_url:
    client = AsyncIOMotorClient(
        mongo_url,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    db = client[os.environ['DB_NAME']]
else:
    logger.warning("MONGO_URL is not set: blog/CMS, portfolio uploads and forms answer 503; premium reports and market data still work")
    client = _UnconfiguredClient()
    db = client[os.environ.get('DB_NAME') or 'finlit']

app = FastAPI()
api_router = APIRouter(prefix="/api")


@app.exception_handler(ConnectionFailure)
async def database_unavailable(_request: Request, exc: ConnectionFailure):
    """MongoDB not configured (MONGO_URL unset) or not reachable: a clear 503 instead of a 500."""
    configured = not isinstance(exc, MongoNotConfigured)
    if configured:
        logger.warning("MongoDB is unavailable: %s", type(exc).__name__)
    detail = ("This part of the site is temporarily unavailable. Please try again shortly." if configured
              else "This part of the site is not available: its content database is not connected.")
    return JSONResponse({"detail": detail}, status_code=503,
                        headers={"Cache-Control": "no-store", "Retry-After": "30", "X-CMS-Content-Store": "unavailable"})

# Kept on the server so provider symbols and credentials never reach the browser.
NIFTY_50_CONSTITUENTS_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv"
FINEDGE_BASE_URL = "https://data.finedgeapi.com/api/v1"
MARKET_TICKER_INDEX_INSTRUMENTS = [
    {"name": "NIFTY 50", "symbol": "NIFTY 50", "instrument_key": "NSE_INDEX|Nifty 50", "category": "Index", "currency": "INR"},
]
MARKET_TICKER_CACHE_SECONDS = 60
NIFTY_50_CONSTITUENTS_CACHE_SECONDS = 60 * 60 * 6
STOCK_FUNDAMENTALS_CACHE_SECONDS = 60 * 15
# Resolved provider data per symbol/basis/period (each premium report adds 2-4). Bounded, so a day of reports on many companies
# cannot fill a small (512 MB) host; STOCK_FUNDAMENTALS_CACHE_ENTRIES changes the bound.
STOCK_FUNDAMENTALS_CACHE_ENTRIES = _env_int("STOCK_FUNDAMENTALS_CACHE_ENTRIES", 32, 4, 2000)
_market_ticker_cache = {"items": None, "fetched_at": 0.0}
_nifty_50_constituents_cache = {"items": None, "fetched_at": 0.0}
_stock_fundamentals_cache = {}
_stock_search_cache = {}
_public_market_cache = {}
_finedge_symbol_cache = {"items": None, "fetched_at": 0.0}

# Content CMS configuration. Admin identities are provisioned via environment
# variables only; there is deliberately no registration endpoint.
CONTENT_TYPES = {"ARTICLE", "PDF", "SPREADSHEET", "IMAGE", "FILE"}
CONTENT_STATUSES = {"DRAFT", "PUBLISHED"}
UPLOAD_TYPES = {
    ".pdf": {"application/pdf"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".xls": {"application/vnd.ms-excel"},
    ".csv": {"text/csv", "text/plain", "application/csv", "application/vnd.ms-excel"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
RESOURCE_MIME_TYPES = {
    "PDF": UPLOAD_TYPES[".pdf"],
    "SPREADSHEET": UPLOAD_TYPES[".xlsx"] | UPLOAD_TYPES[".xls"] | UPLOAD_TYPES[".csv"],
    "IMAGE": UPLOAD_TYPES[".png"] | UPLOAD_TYPES[".jpg"] | UPLOAD_TYPES[".jpeg"] | UPLOAD_TYPES[".webp"],
    "FILE": set().union(*UPLOAD_TYPES.values()),
}
ADMIN_TOKEN_TTL_SECONDS = 60 * 60 * 8
MIN_JWT_SECRET_BYTES = 32
ADMIN_MAX_LOGIN_ATTEMPTS = 5
ADMIN_LOGIN_WINDOW_SECONDS = 15 * 60
ADMIN_LOGIN_LOCK_SECONDS = 5 * 60
FORM_MAX_REQUESTS_PER_HOUR = 8
FORM_RATE_WINDOW_SECONDS = 60 * 60
DUMMY_ADMIN_PASSWORD_HASH = b"$2b$12$6rJnDqVrVjleCmwVwqpAtuZd0nrne.uqw48RnqI7PX7LS60kFIY1C"
_login_attempts = {}
_chat_attempts = {}
_form_attempts = {}
bearer_scheme = HTTPBearer(auto_error=False)


# ---------- Models ----------
class ContactMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: EmailStr
    phone: Optional[str] = None
    investment_size: Optional[str] = None
    subject: Optional[str] = None
    message: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContactCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr = Field(max_length=320)
    phone: Optional[str] = Field(default=None, max_length=30)
    investment_size: Optional[str] = Field(default=None, max_length=100)
    subject: Optional[str] = Field(default=None, max_length=200)
    message: str = Field(default="", max_length=5000)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None or not value.strip():
            return value
        digits = re.findall(r"\d", value)
        if not re.fullmatch(r"\+?[\d\s\-()]+", value) or not 7 <= len(digits) <= 15:
            raise ValueError("Enter a valid mobile number.")
        return value


ServiceName = Literal[
    "0 → 1 Investing",
    "Wealth Planning",
    "Family Financial Planning",
    "Global Investing",
    "Portfolio Review & Stock Selection",
]


class ServiceEnquiry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: EmailStr
    phone: str
    services: List[str]
    message: str = ""
    source: str = "Services Page"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ServiceEnquiryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr = Field(max_length=320)
    phone: str = Field(min_length=7, max_length=30)
    services: List[ServiceName] = Field(max_length=5)
    message: str = Field(default="", max_length=5000)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        digits = re.findall(r"\d", value)
        if not re.fullmatch(r"\+?[\d\s\-()]+", value) or not 7 <= len(digits) <= 15:
            raise ValueError("Enter a valid mobile number.")
        return value


class AdminLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: List[ChatTurn] = Field(default_factory=list, max_length=12)


class ChatResponse(BaseModel):
    response: str


class ContentInput(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    slug: Optional[str] = Field(default=None, max_length=200)
    excerpt: str = Field(default="", max_length=500)
    contentType: Literal["ARTICLE", "PDF", "SPREADSHEET", "IMAGE", "FILE"]
    articleBody: str = Field(default="", max_length=100_000)
    articleFormat: Literal["MARKDOWN", "HTML"] = "MARKDOWN"
    coverImageUrl: Optional[str] = Field(default=None, max_length=1000)
    coverImageKey: Optional[str] = Field(default=None, max_length=255)
    inlineImageKeys: List[str] = Field(default_factory=list, max_length=100)
    fileKey: Optional[str] = Field(default=None, max_length=255)
    author: str = Field(default="Nishant Jain", max_length=120)
    status: Literal["DRAFT", "PUBLISHED"] = "DRAFT"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:180] or "untitled"


def content_public_view(doc):
    result = {key: doc.get(key) for key in (
        "id", "title", "slug", "excerpt", "contentType", "articleBody", "coverImageUrl",
        "fileUrl", "originalFileName", "mimeType", "fileSize", "author", "status",
        "publishedAt", "createdAt", "updatedAt",
    )}
    if doc.get("coverImageKey"):
        result["coverImageUrl"] = f"/api/content/assets/{doc['coverImageKey']}"
    return result


def content_admin_view(doc):
    result = content_public_view(doc)
    result["fileKey"] = doc.get("fileKey")
    result["coverImageKey"] = doc.get("coverImageKey")
    result["coverImageUrl"] = doc.get("coverImageUrl")
    result["inlineImageKeys"] = doc.get("inlineImageKeys") or []
    result["articleFormat"] = doc.get("articleFormat") or "MARKDOWN"
    if result["contentType"] == "ARTICLE":
        result["articleHtml"] = article_rendered_html(doc)
    return result


ARTICLE_TAGS = {
    "p", "h1", "h2", "h3", "strong", "em", "u", "ul", "ol", "li",
    "blockquote", "a", "img", "hr", "br",
}
ARTICLE_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
}


def sanitize_article_html(html: str) -> str:
    """Allow only the editorial HTML emitted by the CMS rich-text editor."""
    return nh3.clean(
        html,
        tags=ARTICLE_TAGS,
        clean_content_tags={"script", "style", "iframe", "object", "embed"},
        attributes=ARTICLE_ATTRIBUTES,
        set_tag_attribute_values={"a": {"target": "_blank"}},
        link_rel="noopener noreferrer",
        url_schemes={"https"},
        strip_comments=True,
    )


def article_rendered_html(doc) -> str:
    body = doc.get("articleBody") or ""
    if doc.get("articleFormat") == "HTML":
        return sanitize_article_html(body)
    return markdown_to_safe_html(body)


def validate_external_cover_url(url: Optional[str]):
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(status_code=400, detail="External cover images require a valid HTTPS URL.")


def rich_article_is_empty(html: str) -> bool:
    readable = re.sub(r"<[^>]+>", "", html).replace("&nbsp;", " ").strip()
    return not readable and "<img" not in html


def markdown_to_safe_html(markdown: str) -> str:
    """Small, deliberately limited Markdown renderer; all input is escaped first."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    rendered, in_list = [], False
    for line in lines:
        raw = escape(line.strip())
        if raw.startswith("- ") or raw.startswith("* "):
            if not in_list:
                rendered.append("<ul>")
                in_list = True
            rendered.append(f"<li>{raw[2:]}</li>")
            continue
        if in_list:
            rendered.append("</ul>")
            in_list = False
        if not raw:
            continue
        if raw.startswith("### "):
            rendered.append(f"<h3>{raw[4:]}</h3>")
        elif raw.startswith("## "):
            rendered.append(f"<h2>{raw[3:]}</h2>")
        elif raw.startswith("# "):
            rendered.append(f"<h1>{raw[2:]}</h1>")
        else:
            raw = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", raw)
            raw = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", raw)
            raw = re.sub(r"\[([^\]]+)\]\((https://[^\s)]+)\)", r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', raw)
            rendered.append(f"<p>{raw}</p>")
    if in_list:
        rendered.append("</ul>")
    return "".join(rendered)


def token_secret():
    secret = os.environ.get("CMS_JWT_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="CMS authentication is not configured.")
    if len(secret.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
        logger.error("CMS_JWT_SECRET is shorter than %s bytes", MIN_JWT_SECRET_BYTES)
        raise HTTPException(status_code=503, detail="CMS authentication is not securely configured.")
    return secret


def client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def hashed_identifier(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def rate_limit_exceeded(bucket: Dict[str, List[float]], key: str, now: float, limit: int, window_seconds: int) -> bool:
    recent = [stamp for stamp in bucket.get(key, []) if now - stamp < window_seconds]
    if len(recent) >= limit:
        bucket[key] = recent
        return True
    recent.append(now)
    bucket[key] = recent
    if len(bucket) > 5000:
        for item_key, stamps in list(bucket.items()):
            if not stamps or now - stamps[-1] >= window_seconds:
                bucket.pop(item_key, None)
    return False


def login_rate_limit_key(email: str, request: Request) -> str:
    return hashed_identifier(email.strip().lower(), client_identifier(request))


def form_rate_limit_key(form_name: str, request: Request) -> str:
    return hashed_identifier(form_name, client_identifier(request))


def chat_rate_limit_exceeded(client_ip: str, now: float) -> bool:
    return rate_limit_exceeded(_chat_attempts, client_ip, now, CHAT_MAX_REQUESTS_PER_MINUTE, CHAT_RATE_WINDOW_SECONDS)


async def require_admin(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Administrator authentication is required.")
    try:
        payload = jwt.decode(credentials.credentials, token_secret(), algorithms=["HS256"], options={"require": ["exp", "iat", "sub"]})
        if payload.get("role") != "admin" or not payload.get("sub"):
            raise ValueError("Invalid role")
        return payload
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Administrator session is invalid or expired.")


@api_router.get("/")
async def root():
    return {"message": "FinLit Ventures site API"}


@api_router.get("/content")
async def public_content(content_type: Optional[str] = None):
    query = {"status": "PUBLISHED"}
    if content_type:
        normalized = content_type.upper()
        if normalized not in CONTENT_TYPES:
            raise HTTPException(status_code=400, detail="Unknown content type.")
        query["contentType"] = normalized
    try:
        docs = await db.content.find(query, {"_id": 0, "fileKey": 0}).sort("publishedAt", -1).to_list(200)
    except ServerSelectionTimeoutError:
        # Local development may start before MongoDB is installed/running. The
        # public index has no seeded content, so degrade to its valid empty state
        # while exposing the condition through a response header and server log.
        # Other database exceptions still surface as genuine API failures.
        logger.warning("CMS content store is unavailable; returning an empty public collection")
        return JSONResponse(
            content=[],
            status_code=200,
            headers={"X-CMS-Content-Store": "unavailable"},
        )
    return [content_public_view(doc) for doc in docs]


@api_router.get("/content/{slug}")
async def public_content_detail(slug: str):
    doc = await db.content.find_one({"slug": slug, "status": "PUBLISHED"}, {"_id": 0, "fileKey": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Published content was not found.")
    result = content_public_view(doc)
    if result["contentType"] == "ARTICLE":
        result["articleHtml"] = article_rendered_html(doc)
    return result


async def current_portfolio_report():
    """The latest uploaded report (kept in MongoDB so a restart cannot revert it); falls back to the file shipped with the code."""
    try:
        saved = await db.portfolio_state.find_one({"_id": "current"})
    except MongoNotConfigured:  # no database at all: the shipped file is the current report (nothing can have been uploaded)
        saved = None
    return saved["report"] if saved else read_current_portfolio_report()


@api_router.get("/portfolio/report")
async def public_portfolio_report():
    return await current_portfolio_report()


@lru_cache(maxsize=1)
def cms_password_hash_from_plain() -> str:
    """Convenience for hosts where generating a bcrypt hash is awkward: CMS_ADMIN_PASSWORD (plain) is hashed once, in memory."""
    plain = os.environ.get("CMS_ADMIN_PASSWORD", "")
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode() if plain else ""


def cms_password_login_enabled() -> bool:
    """The password-only CMS sign-in is off unless CMS_PASSWORD_LOGIN=1. The website gets CMS tokens from the research API
    (POST /api/me/cms-token), which requires the administrator's authenticator code; this route would skip that second step."""
    return os.environ.get("CMS_PASSWORD_LOGIN", "").strip().lower() in ("1", "true", "yes", "on")


@api_router.post("/content/admin/login")
async def admin_login(payload: AdminLogin, request: Request):
    if not cms_password_login_enabled():
        raise HTTPException(status_code=404, detail="Sign in on the website: administrators reach the content tools from their account.")
    now = monotonic()
    attempt_key = login_rate_limit_key(payload.email, request)
    attempt = _login_attempts.get(attempt_key, {"stamps": [], "until": 0})
    if attempt["until"] > now:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    admin_email = os.environ.get("CMS_ADMIN_EMAIL", "").strip().lower()
    password_hash = os.environ.get("CMS_ADMIN_PASSWORD_HASH", "").strip() or cms_password_hash_from_plain()
    if not admin_email or not password_hash:
        raise HTTPException(status_code=503, detail="CMS administrator is not configured.")
    email_matches = payload.email.lower() == admin_email
    hash_to_check = password_hash.encode() if email_matches else DUMMY_ADMIN_PASSWORD_HASH
    try:
        password_matches = bcrypt.checkpw(payload.password.encode(), hash_to_check)
    except ValueError:
        logger.error("CMS admin password hash is invalid")
        raise HTTPException(status_code=503, detail="CMS administrator is not configured.")
    valid = email_matches and password_matches
    if not valid:
        stamps = [stamp for stamp in attempt.get("stamps", []) if now - stamp < ADMIN_LOGIN_WINDOW_SECONDS]
        stamps.append(now)
        _login_attempts[attempt_key] = {
            "stamps": stamps,
            "until": now + ADMIN_LOGIN_LOCK_SECONDS if len(stamps) >= ADMIN_MAX_LOGIN_ATTEMPTS else 0,
        }
        raise HTTPException(status_code=401, detail="Invalid administrator credentials.")
    _login_attempts.pop(attempt_key, None)
    issued_at = int(time())
    token = jwt.encode(
        {"sub": admin_email, "role": "admin", "iat": issued_at, "exp": issued_at + ADMIN_TOKEN_TTL_SECONDS},
        token_secret(),
        algorithm="HS256",
    )
    return {"token": token, "expiresIn": ADMIN_TOKEN_TTL_SECONDS}


@api_router.get("/portfolio/admin/report")
async def admin_portfolio_report(_admin=Depends(require_admin)):
    return await current_portfolio_report()


@api_router.post("/portfolio/admin/upload")
async def admin_upload_portfolio_report(file: UploadFile = File(...), _admin=Depends(require_admin)):
    report = await save_portfolio_upload(file)
    await db.portfolio_state.replace_one({"_id": "current"}, {"_id": "current", "report": report}, upsert=True)
    return report


@api_router.get("/stocks/admin/fundamentals/search")
async def admin_stock_fundamentals_search(
    query: str = Query(..., min_length=2, max_length=80),
    _admin=Depends(require_admin),
):
    instruments = await asyncio.to_thread(_search_finedge_stocks, query)
    return JSONResponse({"items": instruments[:10]}, headers={"Cache-Control": "no-store"})


@api_router.get("/stocks/admin/fundamentals/browse")
async def admin_stock_classification_search(
    group: Literal["sector", "industry"],
    value: str = Query(..., min_length=1, max_length=120),
    _admin=Depends(require_admin),
):
    items = await asyncio.to_thread(_search_finedge_classification, group, value)
    return JSONResponse({"items": items, "total": len(items), "group": group, "value": value.strip()}, headers={"Cache-Control": "no-store"})


@api_router.get("/stocks/admin/fundamentals")
async def admin_stock_fundamentals(
    query: str = Query(..., min_length=2, max_length=80),
    statement_type: Literal["consolidated", "standalone"] = "consolidated",
    period: Literal["yearly", "quarterly"] = "yearly",
    _admin=Depends(require_admin),
):
    data = await asyncio.to_thread(_fetch_stock_fundamentals, query, statement_type, period)
    return JSONResponse(data, headers={"Cache-Control": "no-store"})


SUPPLIED_CANDLES_MAX_BYTES = 1_500_000      # about 3x what the research API sends (a stock and four indices, six years); the 4 MB `inputs` cap is separate


class PremiumReportRequest(BaseModel):
    query: str = Field(min_length=2, max_length=80)
    statement_type: Literal["consolidated", "standalone"] = "consolidated"
    delivery: Literal["background", "inline"] = "background"
    # inline calculations only. "background" (the nightly pre-calculation) gives way to a member waiting: it is turned away
    # with 429 while any interactive calculation is running and is asked to come back in a few seconds.
    priority: Literal["interactive", "background"] = "interactive"
    inputs: Optional[str] = Field(default=None, max_length=4_000_000)         # model inputs kept from an earlier calculation (premium_cache.pack)
    observations: Optional[Dict[str, Any]] = None                                # peer observations kept from earlier calculations
    cache: bool = False                                                          # add a "cache" block to the answer (never part of the signed snapshot)
    keep: bool = True                                                            # ...and in it the packed inputs of a fresh fetch, for the caller to keep
    # FinLit addition: Dhan daily candles from the research API (premium_supplied_candles.py); validated there, a bad value just means the usual providers.
    suppliedCandles: Optional[Dict[str, Any]] = None

    @field_validator("suppliedCandles", mode="before")
    @classmethod
    def _supplied_candles_only_if_an_object(cls, value):
        """A bad extra source must never refuse the whole request: anything but an object is ignored (and logged), and the usual providers run."""
        if value is not None and not isinstance(value, dict):
            logger.warning("suppliedCandles ignored: expected an object, got %s", type(value).__name__)
            return None
        return value


class PremiumSnapshotPDFRequest(BaseModel):
    report: Dict[str, Any]
    receipt: str = Field(min_length=16, max_length=2048)


def _generation_slots_setting():
    """PREMIUM_GENERATION_SLOTS (1-4, default 2): premium reports calculated at once in this process."""
    return _env_int("PREMIUM_GENERATION_SLOTS", 2, 1, 4)


_premium_generation_slots = asyncio.Semaphore(_generation_slots_setting())
_premium_interactive = 0      # interactive calculations queued or running; the background pre-calculation waits while this is above zero
# Transient generation state only: no report collection, persistence or history API.
_PREMIUM_JOB_TTL_SECONDS = 30 * 60
_PREMIUM_JOB_LIMIT = 20
_premium_jobs = {}


def _prune_premium_jobs():
    now = monotonic()
    for key, job in list(_premium_jobs.items()):
        if job["expires"] <= now:
            _premium_jobs.pop(key, None)


PREMIUM_PREFETCH_WORKERS = _env_int("PREMIUM_PREFETCH_WORKERS", 12, 1, 24)


def _premium_prefetch_requests(symbol, statement_type, now):
    """Every provider request the model's inputs always need, as (path, params): the resolver below asks for these one after another, so
    they are asked for together first and its calls are then answered from memory. A request not listed here (a standalone fallback, say)
    is simply made when the resolver reaches it."""
    path, year = _stock_symbol_path(symbol), now.year
    wanted = [(f"/company-profile/{path}", None)]
    bases = ["c", "s"] if statement_type == "consolidated" else ["s"]
    for code, period in (("pl", "annual"), ("bs", "annual"), ("cf", "annual"), ("pl", "quarterly"), ("bs", "quarterly"), ("cf", "quarterly")):
        wanted.append((f"/financials/{path}", {"statement_type": bases[0], "statement_code": code, "period": period}))
    if statement_type == "consolidated":   # the resolver compares revenue with the standalone statements, and bank asset quality may use them
        wanted += [(f"/financials/{path}", {"statement_type": "s", "statement_code": "pl", "period": period}) for period in ("annual", "quarterly")]
    typ = bases[0]
    wanted += [(f"/ratios/{path}", {"statement_type": typ, "ratio_type": kind}) for kind in ("ef", "le", "li", "pr")]
    wanted += [(f"/financial-metrics/{path}", {"statement_type": typ, "ratio_type": kind}) for kind in ("cu", "gr", "av")]
    wanted += [(f"/basic-financials/{path}", {"statement_type": typ, "statement_code": "pl"}),
               (f"/daily-price-ratios/{path}", {"statement_type": typ, "from": str(year), "to": str(year)}),
               (f"/daily-price-ratios/{path}", {"statement_type": typ, "from": str(year - 5), "to": str(year)}),
               ("/quote", {"symbol": symbol}),
               (f"/daily-quotes/{path}", {"from": str(year - 6), "to": str(year)}),
               (f"/peers/{path}", {"group": "industry"})]
    wanted += [(f"/shareholdings/{kind}/{path}", {"period": "quarterly"}) for kind in ("summary", "distribution", "declaration")]
    return wanted


def _premium_prefetch(memo, symbol, statement_type, now, observations=None):
    """Ask for all of `_premium_prefetch_requests` at once. Once the quote and the industry list are in, start looking up the peers' price
    ratios too (the longest part of a report), so that they run while the statements are still being resolved."""
    context = contextvars.copy_context()
    results = {}

    def one(request):
        path, params = request
        try:
            results[(path, json.dumps(params or {}, sort_keys=True))] = context.copy().run(_finedge_get, path, params)
        except Exception:
            pass   # the resolver asks again and handles the failure as it always did

    def warm_peers():
        if observations is None:
            return
        try:
            quote_payload = results.get(("/quote", json.dumps({"symbol": symbol}, sort_keys=True)))
            peers = results.get((f"/peers/{_stock_symbol_path(symbol)}", json.dumps({"group": "industry"}, sort_keys=True)))
            stamp = _quote_from_finedge_quote(quote_payload or {}, symbol).get("timestamp")
            as_of = min(date.fromisoformat(str(stamp or "")[:10]), now.date())
            try:
                from backend.premium_benchmarks import peer_benchmark
            except ImportError:
                from premium_benchmarks import peer_benchmark
            # the metrics the report will most likely ask for; a different set simply misses and is looked up then
            peer_benchmark(_finedge_get, peers or {}, statement_type, as_of, None, ["pe", "pb"], observations=observations)
        except Exception:
            pass

    pool = ThreadPoolExecutor(max_workers=PREMIUM_PREFETCH_WORKERS)
    try:
        requests_ = _premium_prefetch_requests(symbol, statement_type, now)
        early = [r for r in requests_ if r[0] in ("/quote",) or r[0].startswith("/peers/")]
        futures = [pool.submit(one, r) for r in early]
        later = [pool.submit(one, r) for r in requests_ if r not in early]
        for f in futures:
            f.result()
        warmer = threading.Thread(target=warm_peers, daemon=True)
        warmer.start()
        for f in later:
            f.result()
        return warmer
    finally:
        pool.shutdown(wait=True)


def _premium_dashboard_inputs(symbol, statement_type, now, supplied_candles=None, observations=None):
    """Use exactly the dashboard's resolved provider data, including its cache. The calls are shared and made together (see _CallMemo), and
    the extras the model never reads are skipped (see `lean` in _fetch_stock_fundamentals); what the model receives is the same."""
    memo = _CallMemo()
    token = _call_memo.set(memo)
    try:
        def in_dashboard_cache(period):
            entry = _stock_fundamentals_cache.get(f"finedge:{symbol}:{statement_type}:{period}")
            return bool(entry and entry.get("model_inputs") is not None and monotonic() - entry["fetched_at"] < STOCK_FUNDAMENTALS_CACHE_SECONDS)
        if not (in_dashboard_cache("yearly") and in_dashboard_cache("quarterly")):    # otherwise the dashboard's own cache answers, with no call
            _premium_prefetch(memo, symbol, statement_type, now, observations)
        return _premium_dashboard_inputs_resolved(symbol, statement_type, now, supplied_candles=supplied_candles)
    finally:
        _call_memo.reset(token)


def _technical_candle_date(now):
    """The last completed daily session for the technical indicators: an unfinished session (before 16:00 IST) is excluded."""
    ist = now.astimezone(ZoneInfo("Asia/Kolkata"))
    return ist.date() if (ist.hour, ist.minute) >= (16, 0) else ist.date() - timedelta(days=1)


def _premium_kept_with_current_technical(kept, now, supplied_candles):
    """The raw inputs kept from an earlier calculation, with the technical candles made as current as a fresh fetch would have them, or None
    when that cannot be done without fetching (the caller then fetches everything). Statements, ratios and ownership filings change slowly and
    are reused; daily candles are not: supplied (Dhan) candles are the first choice whenever they are valid, exactly as in a fresh fetch, and
    candles that were kept are used only when they end on today's last completed session and come from the same source a fresh fetch would use."""
    try:
        from backend.premium_supplied_candles import supplied_price_input, benchmarks_with_supplied, quote_price_from_raw
        from backend.premium_technical_sources import load_benchmark_history
    except ImportError:
        from premium_supplied_candles import supplied_price_input, benchmarks_with_supplied, quote_price_from_raw
        from premium_technical_sources import load_benchmark_history
    candle_date = _technical_candle_date(now)
    raw = dict(kept["raw"])
    supplied = supplied_price_input(supplied_candles, candle_date, quote_price_from_raw(raw))
    if supplied is not None:
        raw["technicalPriceInput"] = supplied
        required_dates = [row["date"] for row in supplied["bars"][-505:]]
        raw["technicalBenchmarks"] = benchmarks_with_supplied(supplied_candles, candle_date, required_dates,
            lambda: load_benchmark_history(_finedge_get, candle_date, _fetch_upstox_price_history, required_dates))
        return raw
    price_input, benchmarks = raw.get("technicalPriceInput"), raw.get("technicalBenchmarks")
    if not isinstance(price_input, dict) or not isinstance(benchmarks, dict):
        return None
    if price_input.get("throughDate") != candle_date.isoformat() or price_input.get("provider") == "Dhan":
        return None
    if any(isinstance(item, dict) and item.get("provider") == "Dhan" for item in benchmarks.values()):
        return None
    return raw


def _premium_inputs_loader(kept, fresh, observations, supplied_candles=None):
    """The `dashboard_load` of one calculation: inputs kept from an earlier one when they are still fresh enough, else the resolver's, which
    are then copied into `fresh` (to be kept for next time). Either way the model receives the same kind of data."""
    def load(symbol, statement_type, now):
        if kept is not None:
            current = _premium_kept_with_current_technical(kept, now, supplied_candles)
            if current is not None:
                return current, kept["sources"], kept["effective"], kept["sourcing"]
        raw, sources, effective, sourcing = _premium_dashboard_inputs(symbol, statement_type, now, supplied_candles, observations)
        fresh.update({"symbol": symbol, "requested": statement_type, "fetchedAt": now.isoformat(), "raw": raw, "sources": sources,
                      "effective": effective, "sourcing": sourcing})
        return raw, sources, effective, sourcing
    return load


def _premium_dashboard_inputs_resolved(symbol, statement_type, now, lean=True, supplied_candles=None):
    """lean=False is the resolver as it was before the premium report skipped the dashboard's extras (kept for the regression test)."""
    annual, quarterly = {}, {}
    yearly = _fetch_stock_fundamentals(symbol, statement_type, "yearly", annual, _lean=lean)
    effective = yearly["statementType"]
    quarterly_view = _fetch_stock_fundamentals(symbol, effective, "quarterly", quarterly, _lean=lean)
    if quarterly_view["statementType"] != effective:
        effective = quarterly_view["statementType"]
        annual = {}
        yearly = _fetch_stock_fundamentals(symbol, effective, "yearly", annual, _lean=lean)
    quote_data = yearly.get("quote", {})
    raw = {"profile": annual.get("profile", {}), "annual": annual.get("income", {}),
        "quarterly": quarterly.get("income", {}), "balance": annual.get("balance", {}),
        "balance_recent": quarterly.get("balance", {}), "cashflow": annual.get("cashflow", {}),
        "prices": annual.get("prices", {}), "summary": annual.get("summary", {}),
        "distribution": annual.get("distribution", {}), "declaration": annual.get("declaration", {}),
        "asset_quality": {"financials": quarterly.get("assetQualityRows", [])},
        "asset_quality_basis": quarterly.get("assetQualityBasis"),
        "benchmarkObservations": annual.get("benchmarkObservations", []),
        "leverage": annual.get("leverage", {}), "secondaryLeverage": annual.get("secondaryLeverage"),
        "quote": {symbol: {"current_price": quote_data.get("price"), "tradetime": quote_data.get("timestamp"),
                            "market_cap": quote_data.get("marketCap"), "shares": quote_data.get("shares")}}}
    resolved_profile = yearly.get("profile", {})
    if isinstance(raw["profile"], dict):
        raw["profile"] = {**raw["profile"], **{key: value for key, value in {
            "name": yearly.get("instrument", {}).get("name"), "industry": resolved_profile.get("industry"),
            "sector": resolved_profile.get("sector"), "description": resolved_profile.get("description")}.items() if value is not None}}
    # Additional history required by the model uses the same FinEdge connector.
    sources = []
    for section, path, params in [
        ("ratios", f"/daily-price-ratios/{_stock_symbol_path(symbol)}", {"statement_type": "c" if effective == "consolidated" else "s", "from": str(now.year-5), "to": str(now.year)}),
        ("peers", f"/peers/{_stock_symbol_path(symbol)}", {"group": "industry"})]:
        try:
            raw[section] = _finedge_get(path, params)
            available = True
        except Exception:
            raw[section], available = {}, False
        sources.append({"section": section, "available": available, "retrievedAt": now.isoformat()})
    for period, view in (("yearly", yearly), ("quarterly", quarterly_view)):
        sources.extend({"section": f"Dashboard {period}: {key} ({provider})", "available": True,
                        "retrievedAt": view["generatedAt"], "provider": provider} for key, provider in view["sources"].items())
    # The model's cash conversion consumes annual cash flow only. Do not turn
    # the dashboard's separate quarterly-CF availability into a model warning.
    quarterly_notes = [note for note in quarterly.get("resolutionNotes", []) if "cashflow" not in note.lower()]
    notes = list(dict.fromkeys(annual.get("resolutionNotes", []) + quarterly_notes))
    # Technical candles must precede the dashboard's close-only display defaults.
    # Keep their source and any fallback separate from financial-health inputs.
    try:
        from backend.premium_technical import resolve_technical_prices
        from backend.premium_technical_sources import load_benchmark_history
        from backend.premium_supplied_candles import prices_with_supplied, benchmarks_with_supplied, quote_price_from_raw
    except ImportError:
        from premium_technical import resolve_technical_prices
        from premium_technical_sources import load_benchmark_history
        from premium_supplied_candles import prices_with_supplied, benchmarks_with_supplied, quote_price_from_raw
    def load_technical_candles():
        key = yearly.get("instrument", {}).get("upstoxInstrumentKey")
        return _fetch_upstox_price_history(key) if key else []
    # Exclude an unfinished daily session from technical indicators.
    candle_date = _technical_candle_date(now)
    # FinLit: supplied (Dhan) candles are the first choice per series when valid; the original calls are the unchanged fallback.
    raw["technicalPriceInput"] = prices_with_supplied(supplied_candles, candle_date, lambda: resolve_technical_prices(
        annual.get("technicalPrices", {}), yearly["sources"].get("priceHistory"),
        candle_date, load_technical_candles), quote_price_from_raw(raw))
    required_dates = [row["date"] for row in raw["technicalPriceInput"]["bars"][-505:]]
    raw["technicalBenchmarks"] = benchmarks_with_supplied(supplied_candles, candle_date, required_dates,
        lambda: load_benchmark_history(_finedge_get, candle_date, _fetch_upstox_price_history, required_dates))
    return raw, sources, effective, {"yearly": yearly["sources"], "quarterly": quarterly_view["sources"],
        "requestedStatementType": statement_type, "effectiveStatementType": effective,
        "bankAssetQualityStatementType": quarterly.get("assetQualityBasis"), "notes": notes}


async def _generate_premium_report(report_id, symbol, name, statement_type, created_at, supplied_candles=None):
    try:
        from backend.premium_service import generate_report
    except ImportError:
        from premium_service import generate_report
    try:
        async with _premium_generation_slots:
            report = await asyncio.to_thread(generate_report, _finedge_get, symbol, name, statement_type, report_id, created_at,
                lambda s, t, n: _premium_dashboard_inputs(s, t, n, supplied_candles=supplied_candles))
            job =_premium_jobs.get(report_id)
            if job and job["expires"] > monotonic() and job["report"]["state"] == "generating":
                job["report"] = report
    except Exception:
        logger.warning("Premium report generation failed: %s", report_id)
        job = _premium_jobs.get(report_id)
        if job:
            job["report"] = {**job["report"], "state": "failed", "error": "The report could not be generated. Please retry."}


@api_router.post("/premium-reports", status_code=202)
async def create_premium_report(payload: PremiumReportRequest, background_tasks: BackgroundTasks, _admin=Depends(require_admin)):
    _prune_premium_jobs()
    if payload.suppliedCandles is not None:
        size = len(json.dumps(payload.suppliedCandles, separators=(",", ":"), default=str))
        if size > SUPPLIED_CANDLES_MAX_BYTES:
            logger.warning("suppliedCandles rejected: %d bytes is over the %d byte limit", size, SUPPLIED_CANDLES_MAX_BYTES)
            raise HTTPException(status_code=413, detail="The supplied candles are too large. Six years of daily candles for a stock and four indices fit well under the limit.")
    instrument = await asyncio.to_thread(_resolve_finedge_stock, payload.query.strip())
    symbol = str(instrument.get("symbol") or "").upper()
    if not re.fullmatch(r"[A-Z0-9.&-]{1,30}", symbol):
        raise HTTPException(status_code=400, detail="Select a valid company symbol.")
    if payload.delivery == "inline":
        # Vercel can route each request to a different process. Complete this
        # request and return a signed snapshot instead of polling local memory.
        try:
            from backend.premium_service import generate_report
            from backend.premium_snapshot import issue
        except ImportError:
            from premium_service import generate_report
            from premium_snapshot import issue
        global _premium_interactive
        report_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        background = payload.priority == "background"
        if background and _premium_interactive > 0:
            raise HTTPException(status_code=429, detail="A member is waiting for a report; the pre-calculation pauses.", headers={"Retry-After": "3"})
        if not background:
            _premium_interactive += 1
        started = monotonic()
        try:
            try:
                from backend import premium_cache
                from backend.premium_benchmarks import ObservationCache
            except ImportError:
                import premium_cache
                from premium_benchmarks import ObservationCache
            kept = premium_cache.usable_inputs(payload.inputs, symbol, payload.statement_type)
            observations = ObservationCache(premium_cache.preload(payload.observations))
            fresh = {}
            async with _premium_generation_slots:
                report = await asyncio.to_thread(generate_report, _finedge_get, symbol, instrument.get("name"), payload.statement_type, report_id, created_at,
                                                 _premium_inputs_loader(kept, fresh, observations, payload.suppliedCandles), observations)
            snapshot = issue(report, _admin["sub"], token_secret())
            report_cache = {"observations": premium_cache.flatten(observations.new), "universe": observations.universe(), "inputsReused": kept is not None and not fresh,
                            "seconds": round(monotonic() - started, 1)}
            if fresh and payload.keep:
                try:
                    report_cache["inputs"] = premium_cache.pack(fresh)
                except (ValueError, TypeError):
                    logger.info("Premium inputs for %s could not be packed for keeping", symbol)
            if payload.cache:
                snapshot = {**snapshot, "cache": report_cache}
        except Exception as exc:
            logger.warning("Inline premium report generation failed (%s): %s", type(exc).__name__, report_id)
            raise HTTPException(status_code=502, detail="The financial data providers could not complete this report. Please retry.") from None
        finally:
            if not background:
                _premium_interactive -= 1
        return JSONResponse(snapshot, headers={"Cache-Control": "no-store"})
    if len(_premium_jobs) >= _PREMIUM_JOB_LIMIT:
        completed = next((key for key, job in _premium_jobs.items() if job["report"]["state"] != "generating"), None)
        if completed is None:
            raise HTTPException(status_code=429, detail="Report generation is busy. Please try again shortly.")
        _premium_jobs.pop(completed, None)
    report_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()
    pending = {"id": report_id, "state": "generating", "createdAt": created_at, "statementType": payload.statement_type,
               "company": {"symbol": symbol, "name": instrument.get("name") or symbol}}
    _premium_jobs[report_id] = {"report": pending, "expires": monotonic() + _PREMIUM_JOB_TTL_SECONDS}
    asyncio.get_running_loop().call_later(_PREMIUM_JOB_TTL_SECONDS, _premium_jobs.pop, report_id, None)
    background_tasks.add_task(_generate_premium_report, report_id, symbol, instrument.get("name"), payload.statement_type, created_at, payload.suppliedCandles)
    return JSONResponse(pending, status_code=202, headers={"Cache-Control": "no-store"})


async def _current_premium_report(report_id):
    _prune_premium_jobs()
    if not re.fullmatch(r"[a-f0-9]{32}", report_id):
        raise HTTPException(status_code=404, detail="Report not found or expired. Generate a new report.")
    job = _premium_jobs.get(report_id)
    if not job:
        raise HTTPException(status_code=404, detail="Report not found or expired. Generate a new report.")
    report = job["report"]
    if report["state"] == "generating" and (datetime.now(timezone.utc) - datetime.fromisoformat(report["createdAt"])).total_seconds() > 600:
        report = {**report, "state": "failed", "error": "Generation was interrupted or timed out. Please generate a new report."}
        job["report"] = report
    return report


@api_router.get("/premium-reports/{report_id}")
async def get_premium_report(report_id: str, _admin=Depends(require_admin)):
    return JSONResponse(await _current_premium_report(report_id), headers={"Cache-Control": "no-store"})


# Short-lived, one-use, report-scoped capabilities support browser-native attachment
# downloads without placing the administrator JWT in URLs or granting report browsing.
_premium_pdf_tokens = {}


@api_router.post("/premium-reports/{report_id}/download-link")
async def premium_report_download_link(report_id: str, _admin=Depends(require_admin)):
    report = await _current_premium_report(report_id)
    if report["state"] != "ready":
        raise HTTPException(status_code=409, detail="The report is not ready to download.")
    now = monotonic()
    for key, value in list(_premium_pdf_tokens.items()):
        if value["expires"] <= now:
            _premium_pdf_tokens.pop(key, None)
    if len(_premium_pdf_tokens) >= 200:
        _premium_pdf_tokens.pop(next(iter(_premium_pdf_tokens)))
    token = secrets.token_urlsafe(32)
    key = hashlib.sha256(token.encode()).hexdigest()
    _premium_pdf_tokens[key] = {"id": report_id, "expires": now + 120}
    return JSONResponse({"url": f"/api/premium-report-downloads/{token}", "expiresIn": 120}, headers={"Cache-Control": "no-store"})


@api_router.get("/premium-report-downloads/{token}")
async def premium_report_attachment(token: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,60}", token):
        raise HTTPException(status_code=404, detail="Download link is invalid or expired.")
    key = hashlib.sha256(token.encode()).hexdigest()
    capability = _premium_pdf_tokens.pop(key, None)
    if not capability or capability["expires"] <= monotonic():
        raise HTTPException(status_code=404, detail="Download link is invalid or expired. Please download again from the report.")
    report = await _current_premium_report(capability["id"])
    return await _premium_pdf_response(report)


async def _premium_pdf_response(report):
    if report["state"] != "ready":
        raise HTTPException(status_code=409, detail="The report is not ready to download.")
    # The model's buy/sell words must never reach a reader: render a relabelled COPY (premium_pdf.py itself stays identical to upstream).
    try:
        from backend.technical_wording import render_compliant_pdf
    except ImportError:
        from technical_wording import render_compliant_pdf
    content = await asyncio.to_thread(render_compliant_pdf, report)
    filename = f"FinLit-Premium-{report['company']['symbol']}-{report['id'][:8]}.pdf"
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"})


@api_router.post("/premium-reports/pdf")
async def download_current_premium_snapshot(payload: PremiumSnapshotPDFRequest, _admin=Depends(require_admin)):
    try:
        from backend.premium_snapshot import verify
    except ImportError:
        from premium_snapshot import verify
    try:
        report = verify(payload.report, payload.receipt, _admin["sub"], token_secret())
    except Exception:
        raise HTTPException(status_code=400, detail="This report is expired or has changed. Generate a fresh report before downloading.") from None
    return await _premium_pdf_response(report)


@api_router.get("/premium-reports/{report_id}/pdf")
async def download_premium_report(report_id: str, _admin=Depends(require_admin)):
    return await _premium_pdf_response(await _current_premium_report(report_id))


@api_router.get("/content/admin/items")
async def admin_content_list(_admin=Depends(require_admin)):
    docs = await db.content.find({}, {"_id": 0}).sort("updatedAt", -1).to_list(500)
    return [content_admin_view(doc) for doc in docs]


@api_router.get("/content/admin/items/{content_id}")
async def admin_content_detail(content_id: str, _admin=Depends(require_admin)):
    doc = await db.content.find_one({"id": content_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Content was not found.")
    return content_admin_view(doc)


async def resolve_file_metadata(file_key: Optional[str], content_type: Optional[str] = None):
    if not file_key:
        return {}
    doc = await db.content_assets.find_one({"key": file_key}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=400, detail="Uploaded file was not found.")
    if content_type and content_type != "ARTICLE" and doc.get("mimeType") not in RESOURCE_MIME_TYPES[content_type]:
        raise HTTPException(status_code=400, detail=f"The uploaded file is not valid for {content_type.lower()} content.")
    return {
        "fileKey": file_key, "fileUrl": f"/api/content/assets/{file_key}",
        "originalFileName": doc["originalFileName"], "mimeType": doc["mimeType"], "fileSize": doc["fileSize"],
    }


async def validate_image_assets(keys: List[Optional[str]]):
    for key in filter(None, keys):
        asset = await db.content_assets.find_one({"key": key}, {"_id": 0, "mimeType": 1})
        if not asset or not asset.get("mimeType", "").startswith("image/"):
            raise HTTPException(status_code=400, detail="Uploaded image was not found.")


@api_router.post("/content/admin/items", status_code=201)
async def admin_create_content(payload: ContentInput, admin=Depends(require_admin)):
    slug = slugify(payload.slug or payload.title)
    if await db.content.find_one({"slug": slug}):
        raise HTTPException(status_code=409, detail="A content item already uses this slug.")
    if payload.contentType == "ARTICLE" and not payload.articleBody.strip():
        raise HTTPException(status_code=400, detail="Articles require a body.")
    if payload.contentType != "ARTICLE" and not payload.fileKey:
        raise HTTPException(status_code=400, detail="Resources require an uploaded file.")
    if payload.contentType == "ARTICLE" and payload.articleFormat == "HTML":
        payload.articleBody = sanitize_article_html(payload.articleBody)
        if rich_article_is_empty(payload.articleBody):
            raise HTTPException(status_code=400, detail="Articles require a body.")
    validate_external_cover_url(payload.coverImageUrl)
    await validate_image_assets([payload.coverImageKey, *payload.inlineImageKeys])
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc.update(await resolve_file_metadata(payload.fileKey, payload.contentType))
    doc.update({"id": str(uuid.uuid4()), "slug": slug, "createdAt": now, "updatedAt": now, "publishedAt": now if payload.status == "PUBLISHED" else None, "createdBy": admin["sub"]})
    await db.content.insert_one(doc)
    return content_public_view(doc)


@api_router.put("/content/admin/items/{content_id}")
async def admin_update_content(content_id: str, payload: ContentInput, _admin=Depends(require_admin)):
    existing = await db.content.find_one({"id": content_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Content was not found.")
    slug = slugify(payload.slug or payload.title)
    duplicate = await db.content.find_one({"slug": slug, "id": {"$ne": content_id}})
    if duplicate:
        raise HTTPException(status_code=409, detail="A content item already uses this slug.")
    if payload.contentType == "ARTICLE" and not payload.articleBody.strip():
        raise HTTPException(status_code=400, detail="Articles require a body.")
    if payload.contentType != "ARTICLE" and not payload.fileKey:
        raise HTTPException(status_code=400, detail="Resources require an uploaded file.")
    if payload.contentType == "ARTICLE" and payload.articleFormat == "HTML":
        payload.articleBody = sanitize_article_html(payload.articleBody)
        if rich_article_is_empty(payload.articleBody):
            raise HTTPException(status_code=400, detail="Articles require a body.")
    validate_external_cover_url(payload.coverImageUrl)
    await validate_image_assets([payload.coverImageKey, *payload.inlineImageKeys])
    update = payload.model_dump()
    update.update(await resolve_file_metadata(payload.fileKey, payload.contentType))
    update.update({"slug": slug, "updatedAt": datetime.now(timezone.utc).isoformat()})
    if payload.status == "PUBLISHED" and existing.get("status") != "PUBLISHED":
        update["publishedAt"] = datetime.now(timezone.utc).isoformat()
    elif payload.status == "DRAFT" and existing.get("status") == "PUBLISHED":
        update["publishedAt"] = None
    await db.content.update_one({"id": content_id}, {"$set": update})
    return content_admin_view({**existing, **update})


@api_router.delete("/content/admin/items/{content_id}", status_code=204)
async def admin_delete_content(content_id: str, _admin=Depends(require_admin)):
    existing = await db.content.find_one_and_delete({"id": content_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Content was not found.")
    asset_keys = {
        existing.get("fileKey"), existing.get("coverImageKey"),
        *(existing.get("inlineImageKeys") or []),
    }
    for key in filter(None, asset_keys):
        asset = await db.content_assets.find_one_and_delete({"key": key})
        if asset:
            (CONTENT_STORAGE_DIR / asset["storedName"]).unlink(missing_ok=True)
            await db.content_blobs.delete_one({"key": key})
    return None


@api_router.post("/content/admin/upload")
async def admin_upload_content_file(file: UploadFile = File(...), _admin=Depends(require_admin)):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()
    if extension not in UPLOAD_TYPES or file.content_type not in UPLOAD_TYPES[extension]:
        raise HTTPException(status_code=400, detail="Unsupported file type.")
    key = str(uuid.uuid4())
    stored_name = f"{key}{extension}"
    destination = CONTENT_STORAGE_DIR / stored_name
    total = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File exceeds the 15 MB limit.")
                output.write(chunk)
        validate_uploaded_signature(extension, destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    asset = {"key": key, "storedName": stored_name, "originalFileName": original_name, "mimeType": file.content_type, "fileSize": total}
    # Motor mutates the inserted dictionary by adding MongoDB's ObjectId. Insert
    # a copy so the API response remains JSON serializable and never exposes it.
    await db.content_assets.insert_one(asset.copy())
    # The disk of a cloud host is wiped on restart; keep the bytes in MongoDB as well (restored on demand, see restored_asset_path).
    await db.content_blobs.replace_one({"key": key}, {"key": key, "data": destination.read_bytes()}, upsert=True)
    return {**asset, "fileUrl": f"/api/content/assets/{key}"}


def validate_uploaded_signature(extension: str, path: Path):
    """Confirm the file contents match the already validated extension/MIME pair."""
    header = path.read_bytes()[:65536]
    valid = {
        ".pdf": header.startswith(b"%PDF-"),
        ".xlsx": header.startswith(b"PK\x03\x04"),
        ".xls": header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
        ".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": header.startswith(b"\xff\xd8\xff"),
        ".jpeg": header.startswith(b"\xff\xd8\xff"),
        ".webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
    }
    if extension == ".csv":
        try:
            header.decode("utf-8-sig")
            valid[extension] = b"\x00" not in header
        except UnicodeDecodeError:
            valid[extension] = False
    if not valid.get(extension, False):
        raise HTTPException(status_code=400, detail="File contents do not match the selected file type.")


def stored_asset_path(stored_name: str) -> Path:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}\.(pdf|xlsx|xls|csv|png|jpg|jpeg|webp)", stored_name or ""):
        raise HTTPException(status_code=404, detail="Asset storage was not found.")
    path = (CONTENT_STORAGE_DIR / stored_name).resolve()
    storage_root = CONTENT_STORAGE_DIR.resolve()
    if storage_root not in path.parents:
        raise HTTPException(status_code=404, detail="Asset storage was not found.")
    return path


async def restored_asset_path(asset: dict) -> Path:
    """Path of an uploaded file; if a restart wiped the disk, write it back from the copy kept in MongoDB."""
    path = stored_asset_path(asset["storedName"])
    if not path.is_file():
        blob = await db.content_blobs.find_one({"key": asset["key"]})
        if blob:
            path.write_bytes(bytes(blob["data"]))
    return path


@api_router.get("/content/assets/{key}")
async def content_asset(key: str):
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", key):
        raise HTTPException(status_code=404, detail="Published asset was not found.")
    # An asset becomes public only when associated content is published.
    published = await db.content.find_one({
        "status": "PUBLISHED",
        "$or": [{"fileKey": key}, {"coverImageKey": key}, {"inlineImageKeys": key}],
    })
    if not published:
        raise HTTPException(status_code=404, detail="Published asset was not found.")
    asset = await db.content_assets.find_one({"key": key}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset was not found.")
    path = await restored_asset_path(asset)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Asset storage was not found.")
    return FileResponse(path, media_type=asset["mimeType"], filename=asset["originalFileName"], content_disposition_type="inline")


@api_router.get("/content/admin/assets/{key}")
async def admin_content_asset(key: str, _admin=Depends(require_admin)):
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", key):
        raise HTTPException(status_code=404, detail="Asset was not found.")
    asset = await db.content_assets.find_one({"key": key}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset was not found.")
    path = await restored_asset_path(asset)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Asset storage was not found.")
    return FileResponse(path, media_type=asset["mimeType"], filename=asset["originalFileName"], content_disposition_type="inline")


def configured_market_ticker_instruments():
    configured = os.environ.get("UPSTOX_MARKET_TICKER_INSTRUMENTS", "").strip()
    if not configured:
        return [*MARKET_TICKER_INDEX_INSTRUMENTS, *fetch_nifty_50_constituents()]
    try:
        instruments = json.loads(configured)
    except json.JSONDecodeError as e:
        raise ValueError("UPSTOX_MARKET_TICKER_INSTRUMENTS must be valid JSON") from e
    if not isinstance(instruments, list) or not instruments:
        raise ValueError("UPSTOX_MARKET_TICKER_INSTRUMENTS must be a non-empty JSON array")
    for instrument in instruments:
        if not isinstance(instrument, dict) or not instrument.get("instrument_key"):
            raise ValueError("Each ticker instrument must include an instrument_key")
    return instruments


def fetch_nifty_50_constituents():
    cached_items = _nifty_50_constituents_cache["items"]
    if cached_items and monotonic() - _nifty_50_constituents_cache["fetched_at"] < NIFTY_50_CONSTITUENTS_CACHE_SECONDS:
        return cached_items

    response = requests.get(
        NIFTY_50_CONSTITUENTS_URL,
        headers={
            "Accept": "text/csv,*/*",
            "User-Agent": "financial-portfolio-local/1.0",
        },
        timeout=10,
    )
    response.raise_for_status()

    rows = csv.DictReader(StringIO(response.text))
    instruments = []
    for row in rows:
        symbol = (row.get("Symbol") or "").strip()
        company = (row.get("Company Name") or symbol).strip()
        isin = (row.get("ISIN Code") or "").strip()
        if not symbol or not isin:
            continue
        instruments.append({
            "name": company,
            "symbol": symbol,
            "instrument_key": f"NSE_EQ|{isin}",
            "category": "NIFTY 50",
            "currency": "INR",
        })

    if len(instruments) < 45:
        raise ValueError("NIFTY 50 constituent feed returned too few instruments")
    _nifty_50_constituents_cache.update({"items": instruments, "fetched_at": monotonic()})
    return instruments


def _fetch_upstox_quotes(instruments, access_token):
    instrument_keys = [instrument["instrument_key"] for instrument in instruments]
    response = requests.get(
        "https://api.upstox.com/v3/market-quote/ltp",
        params={"instrument_key": ",".join(instrument_keys)},
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "financial-portfolio-local/1.0",
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()

    data = payload.get("data")
    if payload.get("status") != "success" or not isinstance(data, dict):
        raise ValueError("No usable Upstox quote payload returned")

    quotes_by_token = {
        quote.get("instrument_token"): quote
        for quote in data.values()
        if isinstance(quote, dict) and quote.get("instrument_token")
    }

    items = []
    for instrument in instruments:
        quote = quotes_by_token.get(instrument["instrument_key"])
        if not quote:
            raise ValueError(f"No usable quote returned for {instrument['instrument_key']}")

        price = quote.get("last_price")
        close = quote.get("cp")
        if not isinstance(price, (int, float)) or price <= 0:
            raise ValueError(f"No usable price returned for {instrument['instrument_key']}")

        change = price - close if isinstance(close, (int, float)) else 0
        change_percent = (change / close) * 100 if isinstance(close, (int, float)) and close else 0
        items.append({
            "name": instrument.get("name") or quote.get("symbol") or instrument["instrument_key"],
            "symbol": instrument.get("symbol") or quote.get("symbol") or instrument["instrument_key"],
            "instrumentKey": instrument["instrument_key"],
            "category": instrument.get("category", "Market"),
            "currency": instrument.get("currency", "INR"),
            "price": price,
            "change": change,
            "changePercent": change_percent,
            "direction": "up" if change > 0 else "down" if change < 0 else "flat",
            "volume": quote.get("volume"),
            "timestamp": int(time()),
        })
    return items


def _upstox_headers():
    access_token = os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    if not access_token:
        raise HTTPException(status_code=503, detail="Upstox API is not configured.")
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "financial-portfolio-local/1.0",
    }


def _upstox_get_url(url: str, params: Optional[Dict[str, Any]] = None):
    response = requests.get(
        url,
        headers=_upstox_headers(),
        params=params or {},
        timeout=12,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        response.raise_for_status()
        raise ValueError("Upstox returned a non-JSON response") from exc

    if response.status_code >= 400 or payload.get("status") == "error":
        message = "Upstox could not return stock fundamental data."
        errors = payload.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            message = errors[0].get("message") or message
        raise HTTPException(status_code=502 if response.status_code >= 500 else 400, detail=message)

    data = payload.get("data")
    if payload.get("status") != "success" or data is None:
        raise ValueError("Upstox returned an unexpected payload")
    return data


def _upstox_get(path: str, params: Optional[Dict[str, Any]] = None):
    return _upstox_get_url(f"https://api.upstox.com/v2{path}", params)


def _upstox_get_v3(path: str, params: Optional[Dict[str, Any]] = None):
    return _upstox_get_url(f"https://api.upstox.com/v3{path}", params)


def _safe_upstox_get(path: str, params: Optional[Dict[str, Any]] = None, default=None):
    try:
        return _upstox_get(path, params)
    except HTTPException:
        logger.info("Optional Upstox endpoint failed: %s", path)
        return default if default is not None else {}
    except Exception:
        logger.warning("Optional Upstox endpoint errored: %s", path)
        return default if default is not None else {}


def _fetch_upstox_price_history(instrument_key: str):
    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=365 * 6)
    data = _upstox_get_v3(
        f"/historical-candle/{quote(instrument_key, safe='')}/days/1/{to_date.isoformat()}/{from_date.isoformat()}"
    )
    candles = data.get("candles") if isinstance(data, dict) else []
    history = []
    for candle in candles or []:
        if not isinstance(candle, list) or len(candle) < 6:
            continue
        history.append({
            "date": str(candle[0])[:10],
            "open": candle[1],
            "high": candle[2],
            "low": candle[3],
            "close": candle[4],
            "volume": candle[5],
        })
    return sorted(history, key=lambda item: item["date"])


def _is_isin(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value.strip().upper()))


def _normalize_instrument(instrument: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": instrument.get("name") or instrument.get("short_name") or instrument.get("trading_symbol"),
        "shortName": instrument.get("short_name") or instrument.get("trading_symbol"),
        "symbol": instrument.get("trading_symbol"),
        "isin": instrument.get("isin"),
        "instrumentKey": instrument.get("instrument_key"),
        "exchange": instrument.get("exchange"),
        "segment": instrument.get("segment"),
        "instrumentType": instrument.get("instrument_type"),
        "tickSize": instrument.get("tick_size"),
        "lotSize": instrument.get("lot_size"),
    }


def _choose_equity_instrument(query: str, instruments: List[Dict[str, Any]]):
    normalized_query = query.strip().upper()
    equity_matches = [
        item for item in instruments
        if item.get("isin") and item.get("instrument_key") and item.get("segment") in {"NSE_EQ", "BSE_EQ"}
    ]
    if not equity_matches:
        raise HTTPException(status_code=404, detail="No listed equity instrument was found for this query.")

    def score(item):
        symbol = (item.get("trading_symbol") or "").upper()
        name = (item.get("name") or "").upper()
        exact_symbol = 0 if symbol == normalized_query else 1
        starts = 0 if symbol.startswith(normalized_query) or name.startswith(normalized_query) else 1
        exchange = 0 if item.get("segment") == "NSE_EQ" else 1
        return (exact_symbol, starts, exchange, len(symbol or name))

    return sorted(equity_matches, key=score)[0]


def _search_upstox_instruments(query: str):
    cache_key = query.strip().upper()
    cached = _stock_search_cache.get(cache_key)
    if cached and monotonic() - cached["fetched_at"] < STOCK_FUNDAMENTALS_CACHE_SECONDS:
        return cached["items"]

    data = _upstox_get("/instruments/search", {"query": query.strip()})
    if not isinstance(data, list):
        raise ValueError("Upstox instrument search returned an unexpected payload")
    items = [_normalize_instrument(item) for item in data if isinstance(item, dict)]
    _stock_search_cache[cache_key] = {"items": items, "fetched_at": monotonic()}
    return items


def _resolve_upstox_instrument(query: str) -> Dict[str, Any]:
    value = query.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Enter a stock symbol, company name, ISIN, or instrument key.")

    if value.upper().startswith(("NSE_EQ|", "BSE_EQ|")):
        isin = value.split("|", 1)[1].upper()
        instruments = _search_upstox_instruments(isin)
    else:
        instruments = _search_upstox_instruments(value.upper() if _is_isin(value) else value)

    resolved = _choose_equity_instrument(value.split("|", 1)[-1], [
        {
            "name": item.get("name"),
            "short_name": item.get("shortName"),
            "trading_symbol": item.get("symbol"),
            "isin": item.get("isin"),
            "instrument_key": item.get("instrumentKey"),
            "exchange": item.get("exchange"),
            "segment": item.get("segment"),
            "instrument_type": item.get("instrumentType"),
            "tick_size": item.get("tickSize"),
            "lot_size": item.get("lotSize"),
        }
        for item in instruments
    ])
    return _normalize_instrument(resolved)


def _try_resolve_upstox_instrument(*queries: str):
    for query in queries:
        if not query:
            continue
        try:
            return _resolve_upstox_instrument(str(query))
        except Exception:
            continue
    return {}


def _label_key(value: str) -> str:
    value = re.sub(r"(?<!^)(?=[A-Z])", " ", str(value or ""))
    return value.replace("_", " ").replace("-", " ").title()


def _ratio_display_name(value: str):
    compact = re.sub(r"[^a-z0-9]", "", str(value or "").lower())
    aliases = {
        "pe": "P/E",
        "priceearnings": "P/E",
        "pb": "P/B",
        "pricebook": "P/B",
        "roa": "ROA",
        "returnonasset": "ROA",
        "roe": "ROE",
        "returnonequity": "ROE",
        "roce": "ROCE",
        "returnoncapital": "ROCE",
        "returnoncapitalemployed": "ROCE",
        "operatingmargin": "Operating Margin",
        "opm": "Operating Margin",
        "netmargin": "Net Margin",
        "npm": "Net Margin",
        "evebitda": "EV/EBITDA",
        "debtequity": "Debt / Equity",
        "totaldebttoequity": "Debt / Equity",
    }
    return aliases.get(compact) or _label_key(str(value)).replace("P E", "P/E").replace("P B", "P/B")


def _finedge_api_key():
    api_key = os.environ.get("FINEDGE_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="FinEdge API is not configured. Add FINEDGE_API_KEY to the backend environment.")
    return api_key


class _CallMemo:
    """Provider answers kept for the length of ONE premium input assembly. The dashboard resolver runs twice (yearly, then quarterly) and asks
    for the same statements, ratios and quotes both times; a prefetch also asks for them all at once. Two askers of one request share a
    single call. Only successes are kept, so a failed call is still retried exactly as before."""

    def __init__(self):
        self._lock = threading.Lock()
        self._done = {}
        self._inflight = {}
        self.calls = 0
        self.reused = 0

    def get(self, path, params, call):
        key = json.dumps([path, params or {}], sort_keys=True, default=str)
        while True:
            with self._lock:
                if key in self._done:
                    self.reused += 1
                    return copy.deepcopy(self._done[key])
                event = self._inflight.get(key)
                if event is None:
                    self._inflight[key] = event = threading.Event()
                    break
            event.wait(60)
        try:
            value = call(path, params)
            with self._lock:
                self._done[key] = value
                self.calls += 1
            return copy.deepcopy(value)
        finally:
            with self._lock:
                self._inflight.pop(key, None)
            event.set()


_call_memo = contextvars.ContextVar("finedge_call_memo", default=None)


def _finedge_get(path: str, params: Optional[Dict[str, Any]] = None):
    memo = _call_memo.get()
    return _finedge_get_retrying(path, params) if memo is None else memo.get(path, params, _finedge_get_retrying)


def _finedge_get_retrying(path: str, params: Optional[Dict[str, Any]] = None):
    """Bounded retries shared by dashboard and reports; transient errors are not N/A."""
    for attempt in range(3):
        try:
            return _finedge_get_once(path, params)
        except (HTTPException, requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            status = getattr(exc, "status_code", None)
            transient = status in (429, 500, 502, 503, 504) or isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError))
            if not transient:
                raise
            if attempt == 2:
                raise HTTPException(status_code=429 if status == 429 else 502,
                                    detail="FinEdge is temporarily unavailable after bounded retries. Please retry.") from None
            sleep(.5 * (2 ** attempt))


_finedge_get._handles_transient_retries = True


def _finedge_get_once(path: str, params: Optional[Dict[str, Any]] = None):
    request_params = {**(params or {}), "token": _finedge_api_key()}
    response = requests.get(
        f"{FINEDGE_BASE_URL}{path}",
        params=request_params,
        headers={"Accept": "application/json", "User-Agent": "financial-portfolio-local/1.0"},
        timeout=18,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        if response.status_code in {401, 403}:
            raise HTTPException(status_code=response.status_code, detail="FinEdge rejected the API key or this plan is not entitled to the requested data.") from exc
        if response.status_code >= 400:
            raise HTTPException(status_code=502 if response.status_code >= 500 else response.status_code, detail="FinEdge returned an error response.") from exc
        raise ValueError("FinEdge returned a non-JSON response") from exc

    if response.status_code >= 400:
        message = "FinEdge could not return stock fundamental data."
        if response.status_code in {401, 403}:
            message = "FinEdge rejected the API key or this plan is not entitled to the requested data."
        elif isinstance(payload, dict):
            message = payload.get("message") or payload.get("detail") or payload.get("error") or message
        raise HTTPException(status_code=502 if response.status_code >= 500 else response.status_code, detail=message)
    return payload


def _safe_finedge_get(path: str, params: Optional[Dict[str, Any]] = None, default=None):
    try:
        return _finedge_get(path, params)
    except HTTPException:
        logger.info("Optional FinEdge endpoint failed: %s", path)
        return default if default is not None else {}
    except Exception:
        logger.warning("Optional FinEdge endpoint errored: %s", path)
        return default if default is not None else {}


def _payload_items(payload, preferred_keys=None):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    keys = preferred_keys or ["results", "items", "data", "financials", "ratios", "peers", "symbols", "records", "history", "price"]
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    for value in payload.values():
        if isinstance(value, list):
            return value
    return []


def _first_value(row: Dict[str, Any], keys: List[str]):
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    lower_lookup = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        value = lower_lookup.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _to_number(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    cleaned = str(value).replace(",", "").replace("%", "").strip()
    if cleaned in {"", "-", "NA", "N/A", "None", "null"}:
        return None
    try:
        number = float(cleaned)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def _period_sort_value(period: str):
    text = str(period or "")
    year_match = re.search(r"(20\d{2}|19\d{2})", text)
    year = int(year_match.group(1)) if year_match else 0
    quarter_match = re.search(r"Q([1-4])", text.upper())
    quarter = int(quarter_match.group(1)) if quarter_match else 4
    if not quarter_match:
        if re.search(r"JAN|FEB|MAR", text.upper()):
            quarter = 1
        elif re.search(r"APR|MAY|JUN", text.upper()):
            quarter = 2
        elif re.search(r"JUL|AUG|SEP", text.upper()):
            quarter = 3
        elif re.search(r"OCT|NOV|DEC", text.upper()):
            quarter = 4
    return (year, quarter, text)


def _month_label(month: int, year: str):
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    if month < 1 or month > 12:
        return str(year)
    return f"{month_names[month - 1]} {year}"


def _compact_date_label(value, period: str):
    text = str(value or "")
    if re.fullmatch(r"\d{8}", text):
        year = text[:4]
        month = int(text[4:6])
        if period == "quarterly":
            return _month_label(month, year)
        return year
    return None


def _period_label(row: Dict[str, Any], index: int, period: str):
    header = _first_value(row, ["header"])
    if header and str(header).upper() in {"TTM", "YTD"}:
        return str(header).upper()
    if period == "quarterly":
        period_keys = [
            "period", "periodLabel", "displayPeriod", "fiscalPeriod",
            "period_end", "periodEnd", "date", "endDate", "reportDate",
            "fiscal_year", "fiscalYear", "financialYear", "year",
        ]
    else:
        period_keys = [
            "period", "periodLabel", "displayPeriod", "fiscalPeriod", "fiscal_year", "fiscalYear",
            "financialYear", "year", "period_end", "periodEnd", "date", "endDate", "reportDate",
        ]
    value = _first_value(row, period_keys)
    quarter = _first_value(row, ["quarter", "fiscalQuarter", "qtr"])
    year = _first_value(row, ["year", "fiscalYear", "financialYear"])
    if quarter not in (None, "") and year not in (None, ""):
        quarter_text = str(quarter).upper().replace("QUARTER", "Q").replace(" ", "")
        if not quarter_text.startswith("Q") and str(quarter).isdigit():
            quarter_text = f"Q{quarter_text}"
        return f"{quarter_text} {year}"
    if value not in (None, ""):
        text = str(value)
        compact = _compact_date_label(text, period)
        if compact:
            return compact
        date_match = re.match(r"(\d{4})-(\d{2})-", text)
        if period == "quarterly" and date_match:
            month = int(date_match.group(2))
            return _month_label(month, date_match.group(1))
        return text[:10] if date_match else text
    return f"Period {index + 1}"


def _period_change(current, previous):
    current_value = _to_number(current)
    previous_value = _to_number(previous)
    if current_value is None or previous_value is None:
        return None
    if previous_value == 0:
        return 0 if current_value == 0 else None
    return ((current_value - previous_value) / abs(previous_value)) * 100


def _point_change(current, previous):
    current_value = _to_number(current)
    previous_value = _to_number(previous)
    if current_value is None or previous_value is None:
        return None
    return current_value - previous_value


def _normalize_finedge_stock(row: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _first_value(row, ["symbol", "ticker", "nseSymbol", "code", "tradingSymbol"])
    name = _first_value(row, ["companyName", "company_name", "name", "longName", "shortName"])
    isin = _first_value(row, ["isin", "ISIN"])
    exchange = _first_value(row, ["exchange", "exchangeSegment", "listingExchange"])
    return {
        "name": name or symbol,
        "shortName": _first_value(row, ["shortName", "short_name"]) or name or symbol,
        "symbol": symbol,
        "isin": isin,
        "instrumentKey": symbol,
        "exchange": exchange or "NSE/BSE",
        "segment": "EQ",
        "instrumentType": _first_value(row, ["instrumentType", "type"]) or "Equity",
        "bseCode": _first_value(row, ["bse_code", "bseCode"]),
    }


def _finedge_all_symbols():
    cached = _finedge_symbol_cache.get("items")
    if cached and monotonic() - _finedge_symbol_cache["fetched_at"] < NIFTY_50_CONSTITUENTS_CACHE_SECONDS:
        return cached
    payload = _finedge_get("/stock-symbols")
    items = [_normalize_finedge_stock(item) for item in _payload_items(payload) if isinstance(item, dict)]
    _finedge_symbol_cache["items"] = items
    _finedge_symbol_cache["fetched_at"] = monotonic()
    return items


_STOCK_SEARCH_ALIASES = {
    "HUL": "HINDUNILVR", "IHCL": "INDHOTEL", "TAJ HOTEL": "INDHOTEL",
    "TAJ HOTELS": "INDHOTEL", "ZEE5": "ZEEL", "ZEE 5": "ZEEL",
}


def _stock_name_key(value):
    words = re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).split()
    return " ".join(word for word in words if word not in {"THE", "LTD", "LIMITED"})


def _stock_match_rank(item, query):
    needle = query.strip().upper()
    codes = [str(item.get(key) or "").upper() for key in ("symbol", "isin", "bseCode")]
    name, phrase = _stock_name_key(item.get("name")), _stock_name_key(needle)
    if needle in codes: return 0
    if codes[0] == _STOCK_SEARCH_ALIASES.get(phrase): return 1
    if phrase and name == phrase: return 2
    if phrase and (name.startswith(phrase + " ") or name.startswith(phrase)): return 3
    if any(code.startswith(needle) for code in codes if code): return 4
    if phrase and any(word.startswith(phrase) for word in name.split()): return 5
    return 6


def _search_finedge_stocks(query: str):
    cache_key = f"FINEDGE:{query.strip().upper()}"
    cached = _stock_search_cache.get(cache_key)
    if cached and monotonic() - cached["fetched_at"] < STOCK_FUNDAMENTALS_CACHE_SECONDS:
        return cached["items"]

    needle = query.strip().upper()
    alias = _STOCK_SEARCH_ALIASES.get(_stock_name_key(needle))
    items = [
        item for item in _finedge_all_symbols()
        if alias == item.get("symbol") or any(needle in str(item.get(key) or "").upper() for key in ("symbol", "name", "isin", "bseCode"))
        or (_stock_name_key(needle) and _stock_name_key(needle) in _stock_name_key(item.get("name")))
    ]
    items = [item for item in items if item.get("symbol")]
    # Rank the full directory before limiting suggestions; an exact symbol may
    # occur after many incidental company-name substring matches.
    items.sort(key=lambda item: (_stock_match_rank(item, needle), str(item.get("name") or ""), str(item["symbol"])))
    items = items[:20]
    _stock_search_cache[cache_key] = {"items": items, "fetched_at": monotonic()}
    return items


def _search_finedge_classification(group: str, value: str):
    value = value.strip()
    if group not in {"sector", "industry"} or not value:
        raise HTTPException(status_code=400, detail="Choose a sector or industry and enter its classification name.")
    cache_key = f"CLASSIFICATION:{group}:{value.casefold()}"
    cached = _stock_search_cache.get(cache_key)
    if cached and monotonic() - cached["fetched_at"] < STOCK_FUNDAMENTALS_CACHE_SECONDS:
        return cached["items"]
    # Unlike name search, this endpoint accepts an exact classification value
    # and returns symbol strings, including BSE codes.
    payload = _finedge_get("/stock-search", {"group": group, "value": value})
    directory = {}
    for item in _finedge_all_symbols():
        for key in (item.get("symbol"), item.get("bseCode")):
            if key:
                directory[str(key).strip().upper()] = item
    items, seen = [], set()
    for entry in _payload_items(payload, ["symbols", "items", "results"]):
        if isinstance(entry, dict):
            entry = entry.get("symbol")
        symbol = str(entry).strip().upper() if isinstance(entry, (str, int)) else ""
        if not symbol:
            continue
        item = directory.get(symbol) or _normalize_finedge_stock({"symbol": symbol})
        if item["symbol"] in seen:
            continue
        seen.add(item["symbol"])
        items.append(item)
    items.sort(key=lambda item: str(item.get("name") or item["symbol"]).casefold())
    _stock_search_cache[cache_key] = {"items": items, "fetched_at": monotonic()}
    return items


def _resolve_finedge_stock(query: str) -> Dict[str, Any]:
    value = query.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Enter a stock symbol, company name, or ISIN.")
    matches = _search_finedge_stocks(value)
    if matches:
        best = min(_stock_match_rank(item, value) for item in matches)
        candidates = [item for item in matches if _stock_match_rank(item, value) == best]
        if best <= 2 and len(candidates) == 1:
            return candidates[0]
        if best <= 5 and len(matches) == 1:
            return matches[0]
        raise HTTPException(status_code=422, detail="Several or partial company names match this search. Select the intended company symbol from the suggestions.")
    raise HTTPException(status_code=404, detail="No Indian listed equity was found for this query.")


def _stock_symbol_path(symbol: str):
    return quote(str(symbol).strip().upper(), safe="")


def _finedge_statement(symbol: str, statement_type: str, statement_code: str, period: str):
    finedge_period = "annual" if period == "yearly" else "quarterly"
    finedge_type = "c" if statement_type == "consolidated" else "s"
    payload = _finedge_get(
        f"/financials/{_stock_symbol_path(symbol)}",
        {"statement_type": finedge_type, "statement_code": statement_code, "period": finedge_period},
    )
    return _payload_items(payload, ["financials", "data", "results", "items"])


def _metric_key_allowed(key: str, allow_eps: bool = False):
    lowered = key.lower()
    metadata = {
        "period", "periodlabel", "displayperiod", "fiscalperiod", "fiscal_year", "fiscalyear",
        "financialyear", "year", "quarter", "qtr", "date", "enddate", "periodend", "period_end",
        "periodstart", "period_start", "reportdate", "resultdate", "result_date", "statementtype",
        "statementcode", "symbol", "companyname", "company_name", "currency", "unit", "units",
        "unitsin", "createdat", "updatedat",
    }
    if lowered in metadata:
        return False
    if "outstandingshares" in lowered:
        return False
    if not allow_eps and lowered in {"eps", "dilutedeps", "basiceps"}:
        return False
    return not lowered.endswith("date")


def _history_from_period_rows(rows: List[Dict[str, Any]], period: str, aliases: Dict[str, str], scale: float = 1):
    alias_lookup = {str(key).lower(): value for key, value in aliases.items()}
    period_rows = []
    for index, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        period_rows.append({"label": _period_label(row, index, period), "row": row})
    period_rows = sorted(period_rows, key=lambda item: _period_sort_value(item["label"]), reverse=True)

    categories = {}
    for period_index, item in enumerate(period_rows):
        row = item["row"]
        label = item["label"]
        for key, value in row.items():
            if not _metric_key_allowed(str(key), allow_eps=True):
                continue
            number = _to_number(value)
            if number is None:
                continue
            alias_value = aliases.get(str(key), alias_lookup.get(str(key).lower(), str(key)))
            if isinstance(alias_value, (tuple, list)):
                category = alias_value[0]
                priority = alias_value[1] if len(alias_value) > 1 else 100
            else:
                category = alias_value
                priority = 100
            value_scale = 1 if category == "eps" else scale
            number = number / value_scale if value_scale and value_scale != 1 else number
            categories.setdefault(category, {
                "category": category,
                "label": _label_key(category),
                "history": [],
            })
            previous_value = None
            if period_index + 1 < len(period_rows):
                previous_value = _to_number(period_rows[period_index + 1]["row"].get(key))
                previous_value = previous_value / value_scale if previous_value is not None and value_scale and value_scale != 1 else previous_value
            point = {
                "period": label,
                "value": number,
                "change": _period_change(number, previous_value),
                "_priority": priority,
            }
            existing_index = next((idx for idx, item in enumerate(categories[category]["history"]) if item.get("period") == label), None)
            if existing_index is None:
                categories[category]["history"].append(point)
                continue
            existing_value = _to_number(categories[category]["history"][existing_index].get("value"))
            existing_priority = categories[category]["history"][existing_index].get("_priority", 100)
            if priority < existing_priority or (priority == existing_priority and (existing_value in (None, 0) or abs(number) > abs(existing_value))):
                categories[category]["history"][existing_index] = point
    for category in categories.values():
        for point in category["history"]:
            point.pop("_priority", None)
    return list(categories.values())


def _derive_income_metrics(statement: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    categories = {row.get("category"): row for row in statement or [] if isinstance(row, dict)}

    def history(category: str) -> List[Dict[str, Any]]:
        return categories.get(category, {}).get("history") or []

    def value_by_period(category: str) -> Dict[str, float]:
        values = {}
        for point in history(category):
            value = _to_number(point.get("value"))
            if value is not None:
                values[point.get("period")] = value
        return values

    pbt = value_by_period("profit_before_tax")
    interest = value_by_period("interest")
    depreciation = value_by_period("depreciation")
    other_income = value_by_period("other_income")
    associate_profit = value_by_period("associate_profit")
    exceptional = value_by_period("exceptional_items")
    provisions = value_by_period("provisions_for_loan_loss")
    net_profit = value_by_period("net_profit")
    tax_expense = value_by_period("tax_expense")
    existing_operating = value_by_period("operating_profit")
    revenue = value_by_period("revenue")
    if associate_profit:
        income_history = []
        periods_for_income = sorted(set(other_income) | set(associate_profit), key=_period_sort_value, reverse=True)
        for period in periods_for_income:
            income_history.append({
                "period": period,
                "value": other_income.get(period, 0) + associate_profit.get(period, 0),
                "change": None,
            })
        for index, point in enumerate(income_history):
            previous = income_history[index + 1]["value"] if index + 1 < len(income_history) else None
            point["change"] = _period_change(point.get("value"), previous)
        if income_history:
            categories["other_income"] = {
                "category": "other_income",
                "label": _label_key("other_income"),
                "history": income_history,
            }
            other_income = value_by_period("other_income")
    if net_profit and tax_expense and "profit_before_tax" in categories:
        pbt_history = []
        periods_for_pbt = sorted(set(net_profit) & set(tax_expense), key=_period_sort_value, reverse=True)
        for period in periods_for_pbt:
            value = net_profit.get(period)
            tax = tax_expense.get(period)
            if value is None or tax is None:
                continue
            pbt_history.append({
                "period": period,
                "value": value + tax,
                "change": None,
            })
        for index, point in enumerate(pbt_history):
            previous = pbt_history[index + 1]["value"] if index + 1 < len(pbt_history) else None
            point["change"] = _period_change(point.get("value"), previous)
        if pbt_history:
            categories["profit_before_tax"]["history"] = pbt_history
            pbt = value_by_period("profit_before_tax")
    if provisions and "expenses" in categories:
        expense_history = []
        expense_periods = sorted(
            set(revenue) & set(interest) & set(pbt) & set(other_income),
            key=_period_sort_value,
            reverse=True,
        )
        for period in expense_periods:
            value = revenue.get(period, 0) - interest.get(period, 0) - pbt.get(period, 0) + other_income.get(period, 0) - depreciation.get(period, 0)
            expense_history.append({"period": period, "value": value, "change": None})
        for index, point in enumerate(expense_history):
            previous = expense_history[index + 1]["value"] if index + 1 < len(expense_history) else None
            point["change"] = _period_change(point.get("value"), previous)
        if expense_history:
            categories["expenses"]["history"] = expense_history
        expense_by_period = value_by_period("expenses")
        financing_history = []
        financing_periods = sorted(set(revenue) & set(interest) & set(expense_by_period), key=_period_sort_value, reverse=True)
        for period in financing_periods:
            financing_history.append({
                "period": period,
                "value": revenue.get(period, 0) - interest.get(period, 0) - expense_by_period.get(period, 0),
                "change": None,
            })
        for index, point in enumerate(financing_history):
            previous = financing_history[index + 1]["value"] if index + 1 < len(financing_history) else None
            point["change"] = _period_change(point.get("value"), previous)
        if financing_history:
            categories["financing_profit"] = {
                "category": "financing_profit",
                "label": _label_key("financing_profit"),
                "history": financing_history,
            }
    elif revenue and existing_operating and "expenses" in categories:
        expense_history = []
        expense_periods = sorted(set(revenue) & set(existing_operating), key=_period_sort_value, reverse=True)
        for period in expense_periods:
            expense_history.append({
                "period": period,
                "value": revenue.get(period, 0) - existing_operating.get(period, 0),
                "change": None,
            })
        for index, point in enumerate(expense_history):
            previous = expense_history[index + 1]["value"] if index + 1 < len(expense_history) else None
            point["change"] = _period_change(point.get("value"), previous)
        if expense_history:
            categories["expenses"]["history"] = expense_history
    periods = sorted(
        set(pbt) | set(interest) | set(depreciation) | set(other_income),
        key=_period_sort_value,
        reverse=True,
    )
    operating_history = []
    for period in periods:
        if period in existing_operating and existing_operating[period] != 0:
            value = existing_operating[period]
        elif period not in pbt:
            continue
        elif provisions:
            value = pbt.get(period, 0) + provisions.get(period, 0)
        else:
            value = (
                pbt.get(period, 0)
                + interest.get(period, 0)
                + depreciation.get(period, 0)
                - other_income.get(period, 0)
                - exceptional.get(period, 0)
            )
        operating_history.append({"period": period, "value": value, "change": None})

    for index, point in enumerate(operating_history):
        previous = operating_history[index + 1]["value"] if index + 1 < len(operating_history) else None
        point["change"] = _period_change(point.get("value"), previous)

    if operating_history:
        categories["operating_profit"] = {
            "category": "operating_profit",
            "label": _label_key("operating_profit"),
            "history": operating_history,
        }
        if not provisions and revenue and "expenses" in categories:
            operating_by_period = {
                point.get("period"): _to_number(point.get("value"))
                for point in operating_history
                if _to_number(point.get("value")) is not None
            }
            expense_history = []
            expense_periods = sorted(set(revenue) & set(operating_by_period), key=_period_sort_value, reverse=True)
            for period in expense_periods:
                expense_history.append({
                    "period": period,
                    "value": revenue.get(period, 0) - operating_by_period.get(period, 0),
                    "change": None,
                })
            for index, point in enumerate(expense_history):
                previous = expense_history[index + 1]["value"] if index + 1 < len(expense_history) else None
                point["change"] = _period_change(point.get("value"), previous)
            if expense_history:
                categories["expenses"]["history"] = expense_history

    ordered = []
    for category in [
        "revenue",
        "total_income",
        "expenses",
        "financing_profit",
        "operating_profit",
        "other_income",
        "interest",
        "operating_expenses",
        "provisions_for_loan_loss",
        "depreciation",
        "profit_before_tax",
        "exceptional_items",
        "tax_expense",
        "eps",
        "net_profit",
    ]:
        if category in categories:
            ordered.append(categories.pop(category))
    ordered.extend(categories.values())
    return ordered


def _statement_units(rows):
    for row in rows or []:
        if isinstance(row, dict):
            unit = _first_value(row, ["unit", "units", "unitsIn", "currency"])
            if unit:
                return unit
    return "Cr"


def _balance_history(rows: List[Dict[str, Any]], period: str):
    aliases = {
        "totalAssets": "total_asset", "totalAsset": "total_asset", "total_assets": "total_asset",
        "assets": "total_asset",
        "totalLiabilities": "total_liability", "totalLiability": "total_liability", "total_liabilities": "total_liability",
        "liabilities": "total_liability",
        "totalEquity": "equity", "shareholdersEquity": "equity", "shareholderEquity": "equity",
        "equity": "equity", "netWorth": "equity",
        "borrowings": "borrowings", "totalBorrowings": "borrowings", "totalDebt": "borrowings",
        "shortTermBorrowings": "short_term_borrowings", "longTermBorrowings": "long_term_borrowings",
        "deposits": "deposits",
        "reserves": "reserves",
        "capital": "capital",
        "cashAndCashEquivalents": "cash_and_cash_equivalents",
        "cashAndBankBalances": "cash_and_cash_equivalents",
        "cashEquivalents": "cash_and_cash_equivalents",
        "cash": "cash_and_cash_equivalents",
    }
    categories = _history_from_period_rows(rows, period, aliases, scale=10_000_000)
    asset_history = next((row["history"] for row in categories if row["category"] == "total_asset"), [])
    liability_history = next((row["history"] for row in categories if row["category"] == "total_liability"), [])
    liability_by_period = {item["period"]: item for item in liability_history}
    history = []
    for asset in asset_history:
        liability = liability_by_period.get(asset["period"], {})
        history.append({
            "period": asset["period"],
            "total_asset": asset.get("value"),
            "total_liability": liability.get("value"),
        })
    return history, categories


def _normalize_ratio_items(*payloads):
    ratios = []
    seen = set()
    for payload in payloads:
        for row in _payload_items(payload):
            if not isinstance(row, dict):
                continue
            name = _first_value(row, ["name", "ratio", "metric", "label", "displayName"])
            value = _first_value(row, ["company_value", "companyValue", "value", "latestValue", "current", "ratioValue"])
            sector = _first_value(row, ["sector_value", "sectorValue", "industryValue", "benchmark", "peerMedian"])
            if not name:
                numeric_keys = [(key, _to_number(val)) for key, val in row.items() if _metric_key_allowed(str(key))]
                numeric_keys = [(key, val) for key, val in numeric_keys if val is not None]
                if len(numeric_keys) > 1:
                    for metric_name, metric_value in numeric_keys:
                        display_name = _ratio_display_name(str(metric_name))
                        display_value = metric_value
                        if re.search(r"margin|rate|return", str(metric_name), re.IGNORECASE) and abs(display_value) <= 1:
                            display_value *= 100
                        key = display_name.upper()
                        if key in seen:
                            continue
                        seen.add(key)
                        ratios.append({
                            "name": display_name,
                            "company_value": display_value,
                            "sector_value": None,
                        })
                    continue
                if len(numeric_keys) == 1:
                    name, value = numeric_keys[0]
            if not name or _to_number(value) is None:
                continue
            display_name = _ratio_display_name(str(name))
            key = display_name.upper()
            if key in seen:
                continue
            seen.add(key)
            ratios.append({
                "name": display_name,
                "company_value": _to_number(value),
                "sector_value": _to_number(sector),
            })
    return ratios


PROFITABILITY_RATIO_FIELDS = [
    ("grossMargin", "gross_margin", "Gross margin %"),
    ("operatingMargin", "operating_margin", "Operating margin %"),
    ("ebitdaMargin", "ebitda_margin", "EBITDA margin %"),
    ("ebitMargin", "ebit_margin", "EBIT margin %"),
    ("preTaxMargin", "pre_tax_margin", "Pre-tax margin %"),
    ("netMargin", "net_margin", "Net margin %"),
    ("effectiveTaxRate", "effective_tax_rate", "Effective tax rate %"),
    ("returnOnEquity", "return_on_equity", "Return on equity %"),
    ("returnOnCapital", "return_on_capital", "Return on capital %"),
    ("returnOnAsset", "return_on_assets", "Return on assets %"),
    ("returnOnTangibleAssets", "return_on_tangible_assets", "Return on tangible assets %"),
]


def _ratio_percent_value(value):
    number = _to_number(value)
    if number is None:
        return None
    return number * 100 if abs(number) <= 1 else number


def _normalize_revenue_segments(payload, period, income_statement, warnings=None):
    records = _payload_items(payload, ["segment_revenues", "data", "results", "items"])
    revenue = _category_history_map(income_statement.get("income_statement", []), "revenue")
    categories = {}

    def add_point(key, label, period_label, value, description=None):
        row = categories.setdefault(key, {"category": key, "label": label, "history": []})
        if description:
            row["description"] = description
        # A filing may be repeated in a provider response; keep one point.
        row["history"] = [point for point in row["history"] if point["period"] != period_label]
        row["history"].append({"period": period_label, "value": value, "change": None})

    records = [row for row in records if isinstance(row, dict)]
    records.sort(key=lambda row: _period_sort_value(row.get("header", "")), reverse=True)
    for record in records:
        header = str(record.get("header") or "").strip()
        if not header or header.upper() in {"TTM", "YTD"}:
            continue
        period_label = _period_label({"period": header}, 0, period)
        if period == "yearly":
            year = re.search(r"(19\d{2}|20\d{2})", header)
            if year:
                period_label = year.group(0)
        if period_label not in revenue:
            continue
        segments = [segment for segment in record.get("segments") or [] if isinstance(segment, dict)]
        reported_total = _to_number((record.get("data") or {}).get("segmentRevenue"))
        reported_parts = sum(_to_number((segment.get("data") or {}).get("segmentRevenue")) or 0 for segment in segments)
        if reported_total is not None and abs(reported_parts - reported_total) > max(100_000, abs(reported_total) * 0.000001):
            if warnings is not None:
                warnings.append({
                    "severity": "warning", "section": "revenueSegments", "metric": "Revenue",
                    "code": "segment_revenue_total_mismatch",
                    "message": f"{header}: FinEdge's segment figures do not match its reported segment total. The breakdown is unavailable for this period.",
                })
            continue
        segment_total = 0
        found = False
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            name = str(segment.get("name") or "").strip()
            value = _to_number((segment.get("data") or {}).get("segmentRevenue"))
            if not name or value is None:
                continue
            # Treat punctuation variants such as Oil & Gas / Oil and Gas alike.
            key = "segment_" + re.sub(r"[^a-z0-9]", "", name.lower().replace("&", "and"))
            amount = value / 10_000_000
            add_point(key, name, period_label, amount)
            segment_total += amount
            found = True
        if not found:
            continue
        elimination = _to_number((record.get("data") or {}).get("interSegmentRevenue"))
        if elimination is not None:
            elimination /= 10_000_000
            add_point("segment_inter_segment", "Less: inter-segment revenue", period_label, -elimination)
        remainder = revenue[period_label] - (segment_total - (elimination or 0))
        add_point(
            "segment_reconciliation", "Other revenue adjustments", period_label, round(remainder, 6),
            "Difference between reported segment revenue after inter-segment eliminations and P&L revenue.",
        )
    for row in categories.values():
        row["history"].sort(key=lambda point: _period_sort_value(point["period"]), reverse=True)
    streams = [row for key, row in categories.items() if key not in {"segment_inter_segment", "segment_reconciliation"}]
    adjustments = [categories[key] for key in ("segment_inter_segment", "segment_reconciliation") if key in categories]
    return streams + adjustments


def _normalize_bank_asset_quality_history(rows, period):
    # These FinEdge statement fields are fractions, unlike the monetary NPA
    # fields. Keep them separate from the statement's rupees-to-crores scaling.
    fields = [
        ("percentageOfGrossNpa", "gross_npa_percent", "Gross NPA %"),
        ("percentageOfNpa", "net_npa_percent", "Net NPA %"),
        ("cET1Ratio", "cet1_ratio", "CET1 ratio %"),
    ]
    result = []
    for field, category, label in fields:
        points = {}
        for index, row in enumerate(rows or []):
            if not isinstance(row, dict):
                continue
            # FinEdge uses an all-zero disclosure tuple when consolidated bank
            # ratios are unavailable. An individual zero NPA remains valid.
            if all(_to_number(row.get(key)) == 0 for key, _, _ in fields):
                continue
            value = _to_number(row.get(field))
            if value is None:
                continue
            period_label = _period_label(row, index, period)
            if period_label in {"TTM", "YTD"}:
                continue
            points[period_label] = {
                "period": period_label,
                "value": round(value * 100, 2),
                "change": None,
            }
        history = sorted(points.values(), key=lambda point: _period_sort_value(point["period"]), reverse=True)
        if history:
            result.append({"category": category, "label": label, "history": history})
    return result


def _normalize_profitability_ratio_history(payload):
    rows = _payload_items(payload, ["ratios", "data", "results", "items"])
    history_by_category = {
        category: {"category": category, "label": label, "history": []}
        for _, category, label in PROFITABILITY_RATIO_FIELDS
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        period = _first_value(row, ["header", "period", "date", "year"])
        if not period:
            continue
        period = str(period)
        if period.strip().upper() == "TTM":
            continue
        for field, category, _ in PROFITABILITY_RATIO_FIELDS:
            value = _ratio_percent_value(_first_value(row, [field]))
            if value is None:
                continue
            history_by_category[category]["history"].append({
                "period": period,
                "value": round(value, 2),
                "change": None,
            })
    normalized = []
    for item in history_by_category.values():
        history = sorted(item["history"], key=lambda point: _period_sort_value(point.get("period")), reverse=True)
        for index, point in enumerate(history):
            previous = history[index + 1]["value"] if index + 1 < len(history) else None
            point["change"] = _period_change(point.get("value"), previous)
        if history:
            normalized.append({**item, "history": history})
    return normalized


def _clean_ratio_benchmarks(ratios):
    cleaned = []
    for ratio in ratios or []:
        if not isinstance(ratio, dict):
            continue
        item = {**ratio}
        name = str(item.get("name") or "").upper()
        sector_value = _to_number(item.get("sector_value"))
        if name in {"P/E", "PE", "P/B", "PB", "EV/EBITDA", "EV/EBIT", "EV/SALES"} and (sector_value is not None and sector_value <= 0):
            item["sector_value"] = None
        cleaned.append(item)
    return cleaned


def _upsert_ratio(ratios, name, company_value=None, sector_value=None, source=None):
    normalized = str(name).upper()
    for ratio in ratios:
        if str(ratio.get("name") or "").upper() == normalized:
            if company_value is not None:
                ratio["company_value"] = company_value
            if sector_value is not None or ratio.get("sector_value") is not None:
                ratio["sector_value"] = sector_value
            if source:
                ratio["source"] = source
            return ratios
    ratios.append({
        "name": name,
        "company_value": company_value,
        "sector_value": sector_value,
        **({"source": source} if source else {}),
    })
    return ratios


def _latest_price_ratio_snapshot(payload):
    rows = _payload_items(payload, ["price_ratios", "data", "ratios", "items", "results"])
    valid_rows = [row for row in rows if isinstance(row, dict)]
    if not valid_rows:
        return {}
    return sorted(valid_rows, key=lambda row: str(row.get("quote_date") or row.get("date") or ""), reverse=True)[0]


def _history_row(rows, category):
    if not isinstance(rows, list):
        return None
    return next((row for row in rows if isinstance(row, dict) and row.get("category") == category), None)


def _category_history_map(rows, category):
    row = _history_row(rows, category)
    if not row:
        return {}
    return {
        str(point.get("period")): _to_number(point.get("value"))
        for point in row.get("history") or []
        if point.get("period") is not None and _to_number(point.get("value")) is not None
    }


def _merge_category_history(rows, category, history, label=None, source=None):
    if not history:
        return rows
    rows = list(rows or [])
    existing = _history_row(rows, category)
    if existing and existing.get("history"):
        return rows
    item = {
        "category": category,
        "label": label or _label_key(category),
        "history": history,
    }
    if source:
        item["source"] = source
    if existing:
        existing.update(item)
        return rows
    rows.append(item)
    return rows


def _cash_flow_depreciation_history(cash_rows, period):
    rows = _history_from_period_rows(cash_rows, period, {
        "adjForDepreciationAndAmortisationExpense": "depreciation",
        "adjForDepreciationAndAmortizationExpense": "depreciation",
        "depreciationAndAmortisation": "depreciation",
        "depreciationAndAmortization": "depreciation",
        "depreciation": "depreciation",
    }, scale=10_000_000)
    history = _category_history_map(rows, "depreciation")
    return [
        {"period": period_label, "value": value, "change": None}
        for period_label, value in sorted(history.items(), key=lambda item: _period_sort_value(item[0]), reverse=True)
        if value is not None
    ]


def _ttm_net_profit_from_statement(income_statement):
    history = _category_history_map((income_statement or {}).get("income_statement"), "net_profit")
    values = [
        value
        for _, value in sorted(history.items(), key=lambda item: _period_sort_value(item[0]), reverse=True)
        if value is not None
    ]
    if len(values) < 4:
        return None
    ttm_profit = sum(values[:4])
    return ttm_profit if ttm_profit > 0 else None


def _derive_bank_roce(income_statement, balance_sheet):
    income_rows = (income_statement or {}).get("income_statement")
    balance_rows = (balance_sheet or {}).get("balance_sheet")
    pbt = _category_history_map(income_rows, "profit_before_tax")
    interest = _category_history_map(income_rows, "interest")
    deposits = _category_history_map(balance_rows, "deposits")
    borrowings = _category_history_map(balance_rows, "borrowings")
    capital = _category_history_map(balance_rows, "capital")
    reserves = _category_history_map(balance_rows, "reserves")
    periods = sorted(set(pbt) & set(interest), key=_period_sort_value, reverse=True)
    if not periods:
        return None
    latest_period = periods[0]
    capital_periods = sorted(
        set(deposits) | set(borrowings) | set(capital) | set(reserves),
        key=_period_sort_value,
        reverse=True,
    )
    employed_values = []
    for period in capital_periods:
        value = (
            (deposits.get(period) or 0)
            + (borrowings.get(period) or 0)
            + (capital.get(period) or 0)
            + (reserves.get(period) or 0)
        )
        if value > 0:
            employed_values.append(value)
        if len(employed_values) == 2:
            break
    if not employed_values:
        return None
    average_capital_employed = sum(employed_values) / len(employed_values)
    earnings_before_interest_tax = (pbt.get(latest_period) or 0) + (interest.get(latest_period) or 0)
    if average_capital_employed <= 0 or earnings_before_interest_tax <= 0:
        return None
    return (earnings_before_interest_tax / average_capital_employed) * 100


INCOME_STATEMENT_ALIASES = {
    "netSales": ("revenue", 10), "sales": ("revenue", 10),
    "revenueFromOperations": ("revenue", 10), "incomeFromOperations": ("revenue", 10),
    "interestEarned": ("revenue", 10), "interestIncome": ("revenue", 10),
    "revenue": ("revenue", 20), "totalRevenue": ("revenue", 20),
    "totalIncome": "total_income", "income": "total_income",
    "costOfGoodsSold": "cost_of_goods_sold", "cogs": "cost_of_goods_sold",
    "totalExpenses": "expenses", "expenses": "expenses", "operatingExpenses": "expenses",
    "employeeBenefitExpense": "employee_benefit_expense", "employeeBenefitsExpense": "employee_benefit_expense",
    "employeesCost": "employee_benefit_expense",
    "financeCosts": "interest", "financeCost": "interest", "interest": "interest", "interestExpended": "interest",
    "interestExpense": "interest", "interestExpenses": "interest",
    "depreciation": "depreciation", "depreciationAndAmortisation": "depreciation",
    "depreciationAndAmortization": "depreciation",
    "otherIncome": "other_income",
    "otherOperatingExpenses": "operating_expenses",
    "expenditureExcludingProvisions": "expenses",
    "provisionsForLoanLoss": "provisions_for_loan_loss",
    "exceptionalItems": "exceptional_items", "exceptionalItem": "exceptional_items",
    "exceptionalItemsBeforeTax": "exceptional_items", "extraordinaryItems": "exceptional_items",
    "operatingProfit": "operating_profit", "operating_profit": "operating_profit",
    "ebit": "operating_profit",
    "profitBeforeTax": "profit_before_tax", "profitLossBeforeTax": "profit_before_tax", "pbt": "profit_before_tax",
    "profitOrLossOfAssociates": "associate_profit",
    "tax": ("tax_expense", 20), "taxExpense": ("tax_expense", 10), "currentTax": ("tax_expense", 30),
    "profitLossForPeriod": ("net_profit", 5),
    "profitLossForThePeriod": ("net_profit", 5),
    "profitForThePeriod": ("net_profit", 5),
    "netProfitAfterTax": ("net_profit", 10),
    "profitAttributableToOwnersOfParent": ("net_profit", 20),
    "profitOrLossAttributableToOwners": ("net_profit", 20),
    "profitLossAttributableToOwnersOfParent": ("net_profit", 20),
    "profitOrLossAttributableToOwnersOfParent": ("net_profit", 20),
    "profitAfterTax": ("net_profit", 30), "pat": ("net_profit", 30),
    "netProfit": ("net_profit", 40), "net_profit": ("net_profit", 40),
    "netIncome": ("net_profit", 40), "netProfitLoss": ("net_profit", 40),
    "eps": "eps", "basicEPS": "eps", "basicEps": "eps", "dilutedEPS": "eps", "dilutedEps": "eps",
}


def _income_statement_quality_warnings(income_statement, upstox_income_payload, period):
    upstox_rows = _normalize_upstox_statement(upstox_income_payload, "income_statement", period)
    if not upstox_rows:
        return []
    finedge_revenue = _category_history_map(income_statement.get("income_statement"), "revenue")
    finedge_profit = _category_history_map(income_statement.get("income_statement"), "net_profit")
    upstox_revenue_row = next((row for row in upstox_rows if row.get("category") == "revenue"), None)
    upstox_profit = _category_history_map(upstox_rows, "net_profit")
    if not finedge_revenue or not upstox_revenue_row:
        return []
    upstox_revenue = {
        str(point.get("period")): _to_number(point.get("value"))
        for point in upstox_revenue_row.get("history") or []
        if point.get("period") is not None and _to_number(point.get("value")) is not None
    }
    flagged_periods = []
    checked_periods = 0
    for period_label, finedge_value in finedge_revenue.items():
        upstox_value = upstox_revenue.get(period_label)
        if upstox_value is None:
            year_match = re.search(r"(20\d{2}|19\d{2})", str(period_label))
            if year_match:
                upstox_value = next((value for label, value in upstox_revenue.items() if year_match.group(1) in str(label)), None)
        if not upstox_value or not finedge_value:
            continue
        checked_periods += 1
        profit_label = next((label for label in upstox_profit if str(period_label) in str(label) or str(label) in str(period_label)), period_label)
        finedge_np = finedge_profit.get(period_label)
        upstox_np = upstox_profit.get(profit_label)
        profit_aligned = not finedge_np or not upstox_np or abs(finedge_np - upstox_np) / max(abs(upstox_np), 1) < 0.05
        if profit_aligned and abs(finedge_value - upstox_value) / max(abs(upstox_value), 1) > 0.35:
            flagged_periods.append({
                "period": period_label,
                "finedge": round(finedge_value, 2),
                "fallbackProvider": round(upstox_value, 2),
                "differencePercent": round(((finedge_value - upstox_value) / max(abs(upstox_value), 1)) * 100, 2),
            })
    if checked_periods and len(flagged_periods) >= max(1, math.ceil(checked_periods * 0.6)):
        return [{
            "severity": "warning",
            "section": "incomeStatement",
            "metric": "Revenue",
            "code": "finedge_revenue_fallback_provider_mismatch",
            "message": "FinEdge revenue materially differs from the fallback provider while net profit is broadly aligned. FinEdge remains the displayed source; review provider classification before changing source.",
            "periods": flagged_periods[:6],
        }]
    return []


def _reconcile_valuation_ratios(ratios, profile, income_statement, balance_sheet=None, price_ratio_snapshot=None, ttm_net_profit=None):
    ratios = _clean_ratio_benchmarks(ratios)
    market_cap = _to_number((profile or {}).get("marketCap"))
    latest_profit = _latest_history_value((income_statement or {}).get("income_statement"), "net_profit")
    net_profit = _to_number((latest_profit or {}).get("value"))
    latest_revenue = _latest_history_value((income_statement or {}).get("income_statement"), "revenue")
    latest_operating = _latest_history_value((income_statement or {}).get("income_statement"), "operating_profit")
    revenue = _to_number((latest_revenue or {}).get("value"))
    operating_profit = _to_number((latest_operating or {}).get("value"))
    lookup = _ratio_lookup(ratios)
    if revenue and revenue > 0:
        if operating_profit is not None:
            derived_opm = (operating_profit / revenue) * 100
            current_opm = _to_number((lookup.get("OPERATING MARGIN") or {}).get("company_value"))
            if current_opm is None:
                ratios = _upsert_ratio(ratios, "Operating Margin", round(derived_opm, 2), (lookup.get("OPERATING MARGIN") or {}).get("sector_value"), "derived_income_statement")
                lookup = _ratio_lookup(ratios)
        if net_profit is not None:
            derived_npm = (net_profit / revenue) * 100
            current_npm = _to_number((lookup.get("NET MARGIN") or {}).get("company_value"))
            if current_npm is None:
                ratios = _upsert_ratio(ratios, "Net Margin", round(derived_npm, 2), (lookup.get("NET MARGIN") or {}).get("sector_value"), "derived_income_statement")
                lookup = _ratio_lookup(ratios)
    derived_pe = None
    current_pe = _to_number((lookup.get("P/E") or {}).get("company_value"))
    if market_cap and ttm_net_profit and ttm_net_profit > 0 and (current_pe is None or current_pe <= 0):
        ratios = _upsert_ratio(ratios, "P/E", round(market_cap / ttm_net_profit, 2), (lookup.get("P/E") or {}).get("sector_value"), "derived_ttm_net_profit")
        lookup = _ratio_lookup(ratios)
        current_pe = _to_number((lookup.get("P/E") or {}).get("company_value"))
    if market_cap and net_profit and net_profit > 0:
        derived_pe = market_cap / net_profit
        if current_pe is None or current_pe <= 0:
            ratios = _upsert_ratio(ratios, "P/E", round(derived_pe, 2), (lookup.get("P/E") or {}).get("sector_value"), "derived_market_cap")
    daily_pe = _to_number((price_ratio_snapshot or {}).get("pe"))
    if daily_pe and daily_pe > 0:
        lookup = _ratio_lookup(ratios)
        current_pe = _to_number((lookup.get("P/E") or {}).get("company_value"))
        if current_pe is None or current_pe <= 0 or abs(daily_pe - current_pe) / max(abs(daily_pe), 1) > 0.03:
            ratios = _upsert_ratio(ratios, "P/E", round(daily_pe, 2), (lookup.get("P/E") or {}).get("sector_value"), "finedge_daily_price_ratios")
    lookup = _ratio_lookup(ratios)
    current_pe = _to_number((lookup.get("P/E") or {}).get("company_value"))
    if current_pe is not None and current_pe <= 0:
        ratios = _upsert_ratio(ratios, "P/E", None, (lookup.get("P/E") or {}).get("sector_value"), "unavailable_negative_earnings")
        lookup = _ratio_lookup(ratios)
        if lookup.get("P/E"):
            lookup["P/E"]["company_value"] = None
    latest_equity = _latest_history_value((balance_sheet or {}).get("balance_sheet"), "equity")
    equity = _to_number((latest_equity or {}).get("value"))
    if market_cap and equity and equity > 0:
        derived_pb = market_cap / equity
        lookup = _ratio_lookup(ratios)
        current_pb = _to_number((lookup.get("P/B") or {}).get("company_value"))
        if current_pb is None or current_pb <= 0:
            ratios = _upsert_ratio(ratios, "P/B", round(derived_pb, 2), (lookup.get("P/B") or {}).get("sector_value"), "derived_market_cap")
    daily_pb = _to_number((price_ratio_snapshot or {}).get("pb"))
    if daily_pb and daily_pb > 0:
        lookup = _ratio_lookup(ratios)
        current_pb = _to_number((lookup.get("P/B") or {}).get("company_value"))
        if current_pb is None or current_pb <= 0 or abs(daily_pb - current_pb) / max(abs(daily_pb), 1) > 0.05:
            ratios = _upsert_ratio(ratios, "P/B", round(daily_pb, 2), (lookup.get("P/B") or {}).get("sector_value"), "finedge_daily_price_ratios")
    equity_points = []
    latest_equity_row = next((row for row in (balance_sheet or {}).get("balance_sheet", []) if isinstance(row, dict) and row.get("category") == "equity"), None)
    if latest_equity_row:
        equity_points = [_to_number(point.get("value")) for point in latest_equity_row.get("history") or []]
    if len([value for value in equity_points if value and value > 0]) < 2:
        equity_points = [
            _to_number(point.get("total_asset")) - _to_number(point.get("total_liability"))
            for point in (balance_sheet or {}).get("history") or []
            if _to_number(point.get("total_asset")) is not None and _to_number(point.get("total_liability")) is not None
        ]
    equity_points = [value for value in equity_points if value and value > 0]
    if net_profit and net_profit > 0 and equity_points:
        equity_base = sum(equity_points[:2]) / 2 if len(equity_points) > 1 else equity_points[0]
        if equity_base > 0:
            derived_roe = (net_profit / equity_base) * 100
            lookup = _ratio_lookup(ratios)
            current_roe = _to_number((lookup.get("ROE") or {}).get("company_value"))
            if current_roe is None:
                ratios = _upsert_ratio(ratios, "ROE", round(derived_roe, 2), (lookup.get("ROE") or {}).get("sector_value"), "derived_equity")
    lookup = _ratio_lookup(ratios)
    current_roce = _to_number((lookup.get("ROCE") or {}).get("company_value"))
    if current_roce is None:
        bank_roce = _derive_bank_roce(income_statement, balance_sheet)
        if bank_roce is not None:
            ratios = _upsert_ratio(ratios, "ROCE", round(bank_roce, 2), (lookup.get("ROCE") or {}).get("sector_value"), "derived_bank_capital_employed")
    return ratios


def _normalize_profile(payload, instrument):
    if not isinstance(payload, dict):
        payload = {}
    return {
        "description": _first_value(payload, ["description", "companyProfile", "company_profile", "about", "businessSummary"]),
        "sector": _first_value(payload, ["sector", "industry", "sectorName"]),
        "industry": _first_value(payload, ["industry", "industryName"]),
        "website": _first_value(payload, ["website", "homepage", "url"]),
        "marketCap": _first_value(payload, [
            "marketCap", "market_cap", "marketCapitalization", "market_capitalization",
            "mcap", "marketValue", "fullMarketCap", "ffmc",
        ]),
        "companyName": _first_value(payload, ["companyName", "name"]) or instrument.get("name"),
    }


def _normalize_price_history(payload):
    rows = _payload_items(payload, ["price", "quotes", "dailyQuotes", "data", "results", "history"])
    history = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        date = _first_value(row, ["date", "quote_date", "timestamp", "tradingDate", "time"])
        close = _first_value(row, ["close", "close_price", "closePrice", "lastPrice", "adjClose"])
        if not date or _to_number(close) is None:
            continue
        history.append({
            "date": str(date)[:10],
            "open": _to_number(_first_value(row, ["open", "open_price", "openPrice"])) or _to_number(close),
            "high": _to_number(_first_value(row, ["high", "high_price", "highPrice"])) or _to_number(close),
            "low": _to_number(_first_value(row, ["low", "low_price", "lowPrice"])) or _to_number(close),
            "close": _to_number(close),
            "volume": _to_number(_first_value(row, ["volume", "tradedVolume"])),
        })
    return sorted(history, key=lambda item: item["date"])


def _quote_from_price_history(history):
    if not history:
        return {"source": "finedge"}
    latest = history[-1]
    previous = history[-2] if len(history) > 1 else {}
    change = None
    change_percent = None
    if previous.get("close") not in (None, 0):
        change = latest["close"] - previous["close"]
        change_percent = (change / previous["close"]) * 100
    return {
        "price": latest.get("close"),
        "lastPrice": latest.get("close"),
        "change": change,
        "changePercent": change_percent,
        "volume": latest.get("volume"),
        "timestamp": latest.get("date"),
        "source": "finedge",
    }


def _quote_from_finedge_quote(payload, symbol: str):
    if not isinstance(payload, dict):
        return {}
    row = payload.get(symbol) or payload.get(str(symbol).upper()) or next((value for value in payload.values() if isinstance(value, dict)), None)
    if not isinstance(row, dict):
        return {}
    price = _to_number(_first_value(row, ["current_price", "currentPrice", "lastPrice", "price", "close"]))
    if price is None:
        return {}
    observed = _first_value(row, ["tradetime", "tradeTime", "timestamp", "date"])
    if observed and _to_number(observed) is None and _parse_market_date(observed) is None:
        # Invalid provider sentinel dates are not current market observations.
        # Let the shared dashboard path recover a dated close or Upstox quote.
        return {}
    change_percent = _to_number(_first_value(row, ["change", "changePercent", "percentChange"]))
    return {
        "price": price,
        "lastPrice": price,
        "change": _to_number(_first_value(row, ["change_value", "changeValue", "net_change", "netChange"])),
        "changePercent": change_percent,
        "volume": _to_number(_first_value(row, ["volume", "tradedVolume"])),
        "timestamp": _first_value(row, ["tradetime", "tradeTime", "timestamp", "date"]),
        "open": _to_number(_first_value(row, ["open_price", "openPrice", "open"])),
        "high": _to_number(_first_value(row, ["high_price", "highPrice", "high"])),
        "low": _to_number(_first_value(row, ["low_price", "lowPrice", "low"])),
        "high52": _to_number(_first_value(row, ["high52", "week52High", "fiftyTwoWeekHigh"])),
        "low52": _to_number(_first_value(row, ["low52", "week52Low", "fiftyTwoWeekLow"])),
        "marketCap": _to_number(_first_value(row, ["market_cap", "marketCap"])),
        "shares": _to_number(_first_value(row, ["shares", "sharesOutstanding"])),
        "source": "finedge",
    }


def _format_market_cap(value):
    number = _to_number(value)
    if number is None:
        return None
    crore_value = number / 10_000_000 if abs(number) >= 10_000_000 else number
    if abs(crore_value) >= 100000:
        formatted = f"{crore_value:,.0f}"
    elif abs(crore_value) >= 1000:
        formatted = f"{crore_value:,.1f}"
    else:
        formatted = f"{crore_value:,.2f}".rstrip("0").rstrip(".")
    return f"Rs. {formatted} Cr"


def _quote_from_upstox(instrument: Dict[str, Any]):
    instrument_key = instrument.get("upstoxInstrumentKey")
    if not instrument_key:
        return {}
    access_token = os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    if not access_token:
        return {}
    quote_items = _fetch_upstox_quotes([{
        "name": instrument.get("name"),
        "symbol": instrument.get("symbol") or instrument.get("upstoxSymbol"),
        "instrument_key": instrument_key,
        "category": "Equity",
        "currency": "INR",
    }], access_token)
    if not quote_items:
        return {}
    return {**quote_items[0], "source": "upstox"}


def _merge_history_categories(items):
    merged = {}
    for item in items or []:
        if not isinstance(item, dict) or not item.get("category"):
            continue
        bucket = merged.setdefault(item["category"], {
            "category": item["category"],
            "label": item.get("label") or _label_key(item["category"]),
            "history": {},
        })
        for point in item.get("history") or []:
            period = point.get("period")
            value = _to_number(point.get("value"))
            if not period or value is None:
                continue
            current = bucket["history"].get(period)
            bucket["history"][period] = value if current is None else current + value
    normalized = []
    for bucket in merged.values():
        history = [
            {"period": period, "value": round(value, 4), "change": None}
            for period, value in bucket["history"].items()
        ]
        history = sorted(history, key=lambda point: _period_sort_value(point.get("period")), reverse=True)
        for index, point in enumerate(history):
            previous = history[index + 1]["value"] if index + 1 < len(history) else None
            point["change"] = _period_change(point.get("value"), previous)
        normalized.append({**bucket, "history": history})
    return normalized


def _normalize_ownership_structure(summary_payload, distribution_payload, declaration_payload=None):
    definitions = [
        ("total_shares", "Total shares (Cr)", "Cr"),
        ("locked_in_percent", "Locked-in shares %", "%"),
        ("pledged_percent", "Pledged shares %", "%"),
        ("promoter_pledged_percent", "Promoter pledged shares %", "%"),
        ("total_shareholders", "Total shareholders", "count"),
    ]
    metrics = {key: {"category": key, "label": label, "unit": unit, "history": []} for key, label, unit in definitions}
    summaries = {str(row["header"]): row for row in _payload_items(summary_payload, ["summary"])
                 if isinstance(row, dict) and row.get("header")}
    distributions = {str(row["date_header"]): row for row in _payload_items(distribution_payload, ["distributions"])
                     if isinstance(row, dict) and row.get("date_header")}

    declarations = {str(row["header"]): row for row in _payload_items(declaration_payload or {}, ["declaration"])
                    if isinstance(row, dict) and row.get("header")}

    def percentage(data, count_key, percent_key):
        count = _to_number(data.get(count_key))
        total = _to_number(data.get("totalShares"))
        if count is not None and total is not None and total > 0:
            return count / total * 100
        value = _to_number(data.get(percent_key))
        return value if value is not None and 0 <= value <= 100 else None

    for label in sorted(set(summaries) | set(distributions) | set(declarations), key=_period_sort_value, reverse=True):
        summary = summaries.get(label, {})
        promoter = next((row.get("data") or {} for row in distributions.get(label, {}).get("distributions", [])
                         if row.get("group") == "promoterAndPromoterGroup"), {})
        total = _to_number(summary.get("totalShares"))
        values = {
            "total_shares": total / 10_000_000 if total is not None else None,
            "locked_in_percent": percentage(summary, "lockedInShares", "lockedInSharesPct"),
            "pledged_percent": percentage(summary, "pledgedShares", "pledgedSharesPct"),
            "promoter_pledged_percent": percentage(promoter, "pledgedShares", "pledgedSharesPct"),
            "total_shareholders": _to_number(summary.get("totalShareholders")),
        }
        declaration = declarations.get(label, {})
        declared_zeros = set()
        for metric, flag in (("locked_in_percent", "lockedInShares"),
                             ("promoter_pledged_percent", "pledgedSharesForPromoterAndGroup")):
            if values[metric] is None and declaration.get(flag) is False:
                values[metric] = 0
                declared_zeros.add(metric)
        # A promoter-only flag cannot establish total-company pledged shares.
        for key, value in values.items():
            if value is not None:
                point = {"period": label, "value": round(value, 6), "change": None}
                if key in declared_zeros:
                    point["source"] = "declaration_no_shares"
                metrics[key]["history"].append(point)
    return [row for row in metrics.values() if row["history"]]


def _normalize_detailed_shareholding(payload):
    """Preserve reported parent totals and named holders without aggregating them."""
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        return []

    def normalize(row, identity):
        if not isinstance(row, dict):
            return None
        name = str(row.get("name") or row.get("catagory") or row.get("category") or "").strip()
        if not name:
            return None
        values = row.get("data") if isinstance(row.get("data"), dict) else {}
        history = [{"period": label, "value": _to_number(value), "change": None}
                   for label, value in sorted(values.items(), key=lambda item: _period_sort_value(item[0]), reverse=True)]
        children = [child for i, item in enumerate(row.get("shareholders") or [])
                    if (child := normalize(item, f"{identity}-{i}")) is not None]
        return {"category": identity, "label": name, "history": history, "children": children}

    return [row for i, item in enumerate(payload["rows"])
            if (row := normalize(item, f"reported-{i}")) is not None]


def _normalize_shareholding(payload, period="quarterly"):
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        columns = payload.get("columns") or []
        aliases = {
            "promoter": "promoters", "promoters": "promoters", "promotergroup": "promoters",
            "fii": "fii", "fiis": "fii", "foreigninstitution": "fii", "foreigninstitutions": "fii",
            "institutionsforeign": "fii",
            "dii": "other_dii", "otherdii": "other_dii", "insurance": "other_dii",
            "institutionsdomestic": "other_dii", "domesticinstitutions": "other_dii",
            "mutualfunds": "mutual_funds", "mutualfund": "mutual_funds", "mf": "mutual_funds",
            "public": "retail_and_other", "noninstitutions": "retail_and_other",
            "noninstitution": "retail_and_other", "retailandothers": "retail_and_other",
            "others": "retail_and_other", "goverments": "retail_and_other",
            "governments": "retail_and_other", "government": "retail_and_other",
            "sharesheldbynonpromoternonpublicshareholders": "retail_and_other",
        }
        items = []
        for row in payload.get("rows") or []:
            if not isinstance(row, dict):
                continue
            raw_name = str(row.get("catagory") or row.get("category") or row.get("name") or "")
            compact = re.sub(r"[^a-z0-9]", "", raw_name.lower())
            category = aliases.get(compact)
            if not category:
                continue
            data = row.get("data") if isinstance(row.get("data"), dict) else {}
            history = []
            for label in sorted(columns or data.keys(), key=_period_sort_value, reverse=True):
                value = _to_number(data.get(label))
                if value is not None:
                    history.append({"period": label, "value": value, "change": None})
            for index, point in enumerate(history):
                previous = history[index + 1]["value"] if index + 1 < len(history) else None
                point["change"] = _period_change(point.get("value"), previous)
            if history:
                items.append({"category": category, "label": _label_key(category), "history": history})
        return _complete_shareholding_categories(_merge_history_categories(items))
    rows = _payload_items(payload, ["shareholding", "shareholdingPattern", "data", "results", "history"])
    aliases = {
        "promoter": "promoters", "promoters": "promoters", "promoterGroup": "promoters",
        "fii": "fii", "fiis": "fii", "foreignInstitution": "fii", "institutionsForeign": "fii",
        "dii": "other_dii", "otherDii": "other_dii", "insurance": "other_dii",
        "institutionsDomestic": "other_dii", "domesticInstitutions": "other_dii",
        "mutualFunds": "mutual_funds", "mutual_fund": "mutual_funds", "mf": "mutual_funds",
        "retail": "retail_and_other", "public": "retail_and_other", "others": "retail_and_other",
        "retailAndOthers": "retail_and_other", "nonInstitution": "retail_and_other",
        "nonInstitutions": "retail_and_other", "goverments": "retail_and_other",
        "governments": "retail_and_other", "government": "retail_and_other",
        "sharesHeldByNonPromoterNonPublicShareholders": "retail_and_other",
    }
    normalized = _history_from_period_rows(rows, period, aliases)
    keep = {"promoters", "fii", "other_dii", "mutual_funds", "retail_and_other"}
    return _complete_shareholding_categories(_merge_history_categories([{**item, "label": _label_key(item["category"])} for item in normalized if item["category"] in keep]))


def _complete_shareholding_categories(rows):
    rows = rows or []
    if any(row.get("category") == "promoters" for row in rows):
        return rows
    periods = sorted(
        {point.get("period") for row in rows for point in row.get("history", []) if point.get("period")},
        key=_period_sort_value,
        reverse=True,
    )
    promoter_history = []
    for period_label in periods:
        disclosed_total = 0
        for row in rows:
            point = next((item for item in row.get("history", []) if item.get("period") == period_label), None)
            value = _to_number(point.get("value") if point else None)
            if value is not None:
                disclosed_total += value
        if disclosed_total > 0 and disclosed_total < 99.5:
            promoter_history.append({"period": period_label, "value": round(100 - disclosed_total, 4), "change": None})
    for index, point in enumerate(promoter_history):
        previous = promoter_history[index + 1]["value"] if index + 1 < len(promoter_history) else None
        point["change"] = _period_change(point.get("value"), previous)
    if promoter_history:
        return [{"category": "promoters", "label": _label_key("promoters"), "history": promoter_history}, *rows]
    return rows


def _normalize_corporate_actions(*payloads):
    actions = []
    for payload in payloads:
        for row in _payload_items(payload, ["corporateActions", "actions", "dividend", "dividends", "data", "results"]):
            if not isinstance(row, dict):
                continue
            action_type = _first_value(row, ["action", "type", "actionType", "purpose", "dividend_type"]) or ("Dividend" if _first_value(row, ["dividend", "amount", "adj_amount"]) else "Corporate action")
            existing_details = _first_value(row, ["event_details", "eventDetails"])
            actions.append({
                "type": action_type,
                "name": _first_value(row, ["name", "title", "subject", "purpose"]) or action_type,
                "purpose": _first_value(row, ["purpose", "subject", "description"]),
                "ex_date": _first_value(row, ["exDate", "ex_date", "exDividendDate", "date"]),
                "record_date": _first_value(row, ["recordDate", "record_date"]),
                "announcement_date": _first_value(row, ["announcementDate", "announcement_date", "date"]),
                "amount": _first_value(row, ["adj_amount", "amount", "dividend", "dividendAmount"]),
                "ratio": _first_value(row, ["ratio", "bonusRatio", "splitRatio"]),
                "event_details": existing_details if isinstance(existing_details, list) else [
                    {"name": _label_key(key), "value": value}
                    for key, value in row.items()
                    if value not in (None, "")
                    and key not in {"name", "title", "purpose", "type", "actionType", "event_details", "eventDetails"}
                    and not isinstance(value, (dict, list))
                ][:8],
            })
    return actions


def _parse_market_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%Y%m%d"):
        try:
            parsed = datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).replace(tzinfo=timezone.utc)
            return parsed if parsed.year >= 1900 else None
        except ValueError:
            continue
    return None


def _derive_dividend_yield(actions, price, as_of=None):
    latest_price = _to_number(price)
    if not latest_price or latest_price <= 0:
        return None
    end_date = _parse_market_date(as_of) or datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=370)
    dividend_total = 0.0
    seen = set()
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("type") or action.get("name") or "").lower()
        if "dividend" not in action_type:
            continue
        action_date = _parse_market_date(action.get("ex_date") or action.get("announcement_date") or action.get("record_date"))
        if action_date and not (start_date <= action_date <= end_date):
            continue
        amount = _to_number(action.get("amount"))
        if amount:
            key = (action_date.date().isoformat() if action_date else "", round(amount, 6))
            if key in seen:
                continue
            seen.add(key)
            dividend_total += amount
    if dividend_total <= 0:
        return None
    return (dividend_total / latest_price) * 100


def _normalize_upstox_period(period: str):
    text = str(period or "")
    match = re.search(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(20\d{2}|19\d{2})", text.upper())
    if not match:
        return text
    month = {
        "JAN": 1, "FEB": 2, "MAR": 3,
        "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9,
        "OCT": 10, "NOV": 11, "DEC": 12,
    }[match.group(1)]
    return _month_label(month, match.group(2))


def _normalize_upstox_history(history, period="yearly"):
    rows = []
    for point in history or []:
        if not isinstance(point, dict):
            continue
        value = _to_number(point.get("value"))
        if value is None:
            continue
        label = point.get("period")
        rows.append({
            "period": _normalize_upstox_period(label) if period == "quarterly" else str(label or ""),
            "value": value,
            "change": _to_number(point.get("change")),
        })
    return rows


def _fill_point_changes(history):
    rows = list(history or [])
    for index, row in enumerate(rows):
        if row.get("change") is not None:
            continue
        previous = rows[index + 1] if index + 1 < len(rows) else None
        if previous:
            row["change"] = _point_change(row.get("value"), previous.get("value"))
    return rows


def _normalize_upstox_statement(payload, key, period="yearly"):
    if not isinstance(payload, dict):
        return []
    rows = []
    for row in payload.get(key) or []:
        if not isinstance(row, dict):
            continue
        category = row.get("category")
        history = _normalize_upstox_history(row.get("history"), period)
        if category and history:
            rows.append({"category": category, "label": _label_key(category), "history": history})
    return rows


def _normalize_upstox_balance_sheet(payload, period="yearly"):
    if not isinstance(payload, dict):
        return []
    rows = []
    for row in payload.get("history") or []:
        if not isinstance(row, dict):
            continue
        rows.append({
            "period": _normalize_upstox_period(row.get("period")) if period == "quarterly" else str(row.get("period") or ""),
            "total_asset": _to_number(row.get("total_asset")),
            "total_liability": _to_number(row.get("total_liability")),
        })
    return [row for row in rows if row.get("total_asset") is not None or row.get("total_liability") is not None]


def _normalize_upstox_shareholding(payload):
    rows = []
    aliases = {"dii": "other_dii", "public": "retail_and_other"}
    for row in payload or []:
        if not isinstance(row, dict):
            continue
        category = aliases.get(str(row.get("category") or "").lower(), row.get("category"))
        history = _fill_point_changes(_normalize_upstox_history(row.get("history"), "quarterly"))
        if category and history:
            rows.append({"category": category, "label": _label_key(category), "history": history})
    return rows


def _normalize_upstox_competitors(payload, base_competitors=None):
    competitors = []
    base_competitors = base_competitors or []
    for index, row in enumerate(payload or []):
        if not isinstance(row, dict):
            continue
        base = base_competitors[index] if index < len(base_competitors) else {}
        instrument_key = _first_value(row, ["instrument_key", "instrumentKey"])
        isin = instrument_key.split("|", 1)[1] if isinstance(instrument_key, str) and "|" in instrument_key else _first_value(row, ["isin"])
        competitors.append({
            "instrumentKey": instrument_key or base.get("instrumentKey") or isin or _first_value(row, ["symbol", "trading_symbol"]),
            "name": _first_value(row, ["name", "company_name", "companyName"]) or base.get("name") or _first_value(row, ["symbol", "trading_symbol"]),
            "symbol": _first_value(row, ["trading_symbol", "symbol"]) or base.get("symbol"),
            "isin": isin,
            "exchange": _first_value(row, ["exchange"]) or base.get("exchange") or "NSE/BSE",
            "sector": _first_value(row, ["sector", "industry"]) or base.get("sector"),
            "summary": _first_value(row, ["company_profile", "description", "summary"]) or "",
            "sectorMarketCapInr": (_first_value(row, ["sector_market_cap_inr"]) or {}).get("formatted") if isinstance(_first_value(row, ["sector_market_cap_inr"]), dict) else _first_value(row, ["sector_market_cap_inr", "marketCap"]),
        })
    return [item for item in competitors if item.get("instrumentKey") or item.get("symbol")]


def _peer_profile(symbol):
    if not symbol:
        return {}
    normalized = str(symbol).strip().upper()
    cached = _finedge_symbol_cache.get("items") or []
    match = next((item for item in cached if str(item.get("symbol") or "").upper() == normalized), None)
    if match:
        return match
    try:
        universe = _finedge_all_symbols()
    except Exception:
        return {}
    return next((item for item in universe if str(item.get("symbol") or "").upper() == normalized), {})


def _normalize_competitors(payload, current_symbol=None):
    competitors = []
    current = str(current_symbol or "").upper()
    for row in _payload_items(payload, ["peers", "competitors", "data", "results"]):
        if isinstance(row, str):
            if row.upper() == current:
                continue
            peer = _peer_profile(row)
            competitors.append({
                "instrumentKey": peer.get("instrumentKey") or row,
                "name": peer.get("name") or row,
                "symbol": peer.get("symbol") or row,
                "isin": peer.get("isin"),
                "exchange": "NSE/BSE",
                "sector": peer.get("segment"),
                "summary": "",
                "sectorMarketCapInr": None,
            })
            continue
        if not isinstance(row, dict):
            continue
        symbol = _first_value(row, ["symbol", "ticker", "peerSymbol", "nseSymbol"])
        if str(symbol or "").upper() == current:
            continue
        peer = _peer_profile(symbol)
        name = _first_value(row, ["companyName", "name", "peerName"]) or symbol
        competitors.append({
            "instrumentKey": peer.get("instrumentKey") or symbol,
            "name": peer.get("name") or name,
            "symbol": peer.get("symbol") or symbol,
            "isin": _first_value(row, ["isin"]) or peer.get("isin"),
            "exchange": _first_value(row, ["exchange"]) or peer.get("exchange") or "NSE/BSE",
            "sector": _first_value(row, ["sector", "industry"]) or peer.get("segment"),
            "summary": _first_value(row, ["description", "summary"]) or "",
            "sectorMarketCapInr": _first_value(row, ["marketCap", "market_cap"]),
        })
    return [item for item in competitors if item.get("symbol")]


def _enrich_competitors_from_finedge(competitors):
    enriched = []
    for competitor in (competitors or [])[:12]:
        symbol = competitor.get("symbol")
        if not symbol:
            enriched.append(competitor)
            continue
        profile_payload = {}
        quote_data = {}
        needs_profile = not competitor.get("name") or not competitor.get("sector")
        if needs_profile:
            profile_payload = _safe_finedge_get(f"/company-profile/{_stock_symbol_path(symbol)}", default={}) or {}
        if not competitor.get("sectorMarketCapInr") and not competitor.get("marketCap"):
            quote_data = _quote_from_finedge_quote(_safe_finedge_get("/quote", {"symbol": symbol}, default={}), symbol)
        market_cap = (
            competitor.get("marketCap")
            or competitor.get("sectorMarketCapInr")
            or quote_data.get("marketCap")
            or _first_value(profile_payload, ["marketCap", "market_cap", "marketCapitalization", "market_capitalization", "mcap", "marketValue", "fullMarketCap", "ffmc"])
        )
        enriched.append({
            **competitor,
            "name": competitor.get("name") or _first_value(profile_payload, ["companyName", "name"]) or symbol,
            "sector": competitor.get("sector") or _first_value(profile_payload, ["sector", "industry", "sectorName"]),
            "summary": competitor.get("summary") or (_first_value(profile_payload, ["description", "companyProfile", "company_profile", "about", "businessSummary"]) or "")[:220],
            "marketCap": _to_number(market_cap),
            "marketCapDisplay": competitor.get("marketCapDisplay") or _format_market_cap(market_cap),
        })
    return enriched


def _latest_history_value(rows, category):
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("category") == category and row.get("history"):
            history = row["history"]
            if isinstance(history, list) and history:
                return history[0]
    return None


def _history_length(rows, category):
    value = _latest_history_value(rows, category)
    if not value:
        return 0
    for row in rows or []:
        if isinstance(row, dict) and row.get("category") == category:
            return len(row.get("history") or [])
    return 0


def _ratio_lookup(ratios):
    result = {}
    if isinstance(ratios, list):
        for ratio in ratios:
            if isinstance(ratio, dict) and ratio.get("name"):
                result[ratio["name"].upper()] = ratio
    return result


def _history_point_count(rows):
    return sum(len(row.get("history") or []) for row in rows or [] if isinstance(row, dict))


def _stock_section_counts(result):
    return {
        "profile": 1 if result.get("profile") else 0,
        "incomeStatement": _history_point_count(result.get("incomeStatement", {}).get("income_statement")),
        "balanceSheet": len(result.get("balanceSheet", {}).get("history") or []) + _history_point_count(result.get("balanceSheet", {}).get("balance_sheet")),
        "cashFlow": _history_point_count(result.get("cashFlow", {}).get("cash_flow")),
        "ratios": len(result.get("ratios") or []),
        "profitabilityRatios": _history_point_count(result.get("profitabilityRatios")),
        "bankAssetQuality": _history_point_count(result.get("bankAssetQuality")),
        "revenueSegments": _history_point_count(result.get("revenueSegments")),
        "shareholding": _history_point_count(result.get("shareholding")),
        "ownershipStructure": _history_point_count(result.get("ownershipStructure")),
        "corporateActions": len(result.get("corporateActions") or []),
        "competitors": len(result.get("competitors") or []),
        "priceHistory": len(result.get("priceHistory") or []),
        "quote": 1 if result.get("quote", {}).get("price") else 0,
    }


def _provider_bucket(source):
    text = str(source or "").lower()
    if "finedge" in text and "upstox" in text:
        return "mixed"
    if "upstox" in text:
        return "upstox"
    if "finedge" in text:
        return "finedge"
    return "other"


def _stock_dev_metrics(result, started_at):
    sources = result.get("sources") or {}
    section_counts = _stock_section_counts(result)
    provider_records = {"finedge": 0, "upstox": 0, "mixed": 0, "other": 0}
    provider_sections = {"finedge": 0, "upstox": 0, "mixed": 0, "other": 0}
    section_breakdown = {}
    for section, count in section_counts.items():
        provider = _provider_bucket(sources.get(section))
        provider_records[provider] += count
        provider_sections[provider] += 1
        section_breakdown[section] = {
            "source": sources.get(section) or "unknown",
            "provider": provider,
            "records": count,
        }
    total_records = sum(provider_records.values())
    return {
        "backendMs": round((monotonic() - started_at) * 1000),
        "totalRecords": total_records,
        "providerRecords": provider_records,
        "providerRecordShare": {
            provider: round((count / total_records) * 100, 1) if total_records else 0
            for provider, count in provider_records.items()
        },
        "providerSections": provider_sections,
        "sections": section_breakdown,
    }


def _compact_competitor(competitor):
    profile = competitor.get("company_profile") or ""
    instrument_key = competitor.get("instrument_key")
    instrument = {}
    if instrument_key:
        try:
            instrument = _resolve_upstox_instrument(instrument_key)
        except Exception:
            logger.warning("Stock fundamentals competitor instrument lookup failed")
    return {
        "instrumentKey": instrument_key,
        "name": instrument.get("name"),
        "symbol": instrument.get("symbol"),
        "isin": instrument.get("isin") or (instrument_key.split("|", 1)[1] if "|" in instrument_key else None),
        "exchange": instrument.get("exchange"),
        "sector": competitor.get("sector"),
        "summary": profile[:220] + ("..." if len(profile) > 220 else ""),
        "sectorMarketCapInr": competitor.get("sector_market_cap_inr", {}).get("formatted"),
    }


def _remember_stock_fundamentals(cache_key, entry):
    """Store one resolved result: expired entries are dropped first, then the oldest, to stay within STOCK_FUNDAMENTALS_CACHE_ENTRIES."""
    now = monotonic()
    for key, value in list(_stock_fundamentals_cache.items()):
        if now - value.get("fetched_at", 0) >= STOCK_FUNDAMENTALS_CACHE_SECONDS:
            _stock_fundamentals_cache.pop(key, None)
    _stock_fundamentals_cache.pop(cache_key, None)
    while _stock_fundamentals_cache and len(_stock_fundamentals_cache) >= STOCK_FUNDAMENTALS_CACHE_ENTRIES:
        _stock_fundamentals_cache.pop(next(iter(_stock_fundamentals_cache)), None)
    _stock_fundamentals_cache[cache_key] = entry


def _fetch_stock_fundamentals(query: str, statement_type: str = "consolidated", period: str = "yearly", _model_capture=None, _lean=None):
    started_at = monotonic()
    instrument = _resolve_finedge_stock(query)
    symbol = instrument.get("symbol")
    if not symbol:
        raise HTTPException(status_code=404, detail="This stock is missing a FinEdge symbol.")
    upstox_instrument = _try_resolve_upstox_instrument(
        instrument.get("isin"),
        instrument.get("symbol"),
        instrument.get("name"),
        query,
    )
    if upstox_instrument:
        instrument = {
            **instrument,
            "isin": instrument.get("isin") or upstox_instrument.get("isin"),
            "upstoxInstrumentKey": upstox_instrument.get("instrumentKey"),
            "upstoxSymbol": upstox_instrument.get("symbol"),
        }

    # A premium report (`_model_capture`) needs the statements, ratios, quote, prices and ownership filings only. The dashboard's own extras
    # (revenue segments, shareholding pattern, corporate actions, dividends, competitors with a quote each) feed nothing in the model: in
    # that case they are not fetched, and the half-built view is not left in the dashboard's cache.
    lean = (_model_capture is not None) if _lean is None else _lean
    cache_key = f"finedge:{symbol}:{statement_type}:{period}"
    cached = _stock_fundamentals_cache.get(cache_key)
    if cached and monotonic() - cached["fetched_at"] < STOCK_FUNDAMENTALS_CACHE_SECONDS:
        if _model_capture is not None and cached.get("model_inputs") is not None:
            _model_capture.update(cached["model_inputs"])
        cached_data = {**cached["data"], "cached": True}
        cached_data["devMetrics"] = {
            **cached_data.get("devMetrics", {}),
            "backendMs": round((monotonic() - started_at) * 1000),
            "cacheAgeSeconds": round(monotonic() - cached["fetched_at"], 1),
        }
        return cached_data

    profile_payload = _finedge_get(f"/company-profile/{_stock_symbol_path(symbol)}")
    requested_income_rows = _finedge_statement(symbol, statement_type, "pl", period)
    requested_balance_rows = _finedge_statement(symbol, statement_type, "bs", period)
    requested_cash_rows = _finedge_statement(symbol, statement_type, "cf", period)
    income_rows = requested_income_rows
    standalone_income_rows = []
    balance_rows = requested_balance_rows
    cash_rows = requested_cash_rows
    effective_statement_type = statement_type
    data_sources = {
        "profile": "finedge",
        "incomeStatement": "finedge",
        "balanceSheet": "finedge",
        "cashFlow": "finedge",
        "ratios": "finedge",
        "profitabilityRatios": "finedge",
        "bankAssetQuality": "finedge",
        "revenueSegments": "finedge",
        "shareholding": "finedge",
        "ownershipStructure": "finedge",
        "corporateActions": "finedge",
        "competitors": "finedge",
        "priceHistory": "finedge",
        "quote": "finedge",
    }
    data_quality = []
    if statement_type == "consolidated":
        standalone_income_rows = _safe_finedge_get(
            f"/financials/{_stock_symbol_path(symbol)}",
            {"statement_type": "s", "statement_code": "pl", "period": "annual" if period == "yearly" else "quarterly"},
            default={},
        )
        standalone_income_rows = _payload_items(standalone_income_rows, ["financials", "data", "results", "items"])
        revenue_aliases = {
            "netSales": ("revenue", 10), "sales": ("revenue", 10),
            "revenueFromOperations": ("revenue", 10), "incomeFromOperations": ("revenue", 10),
            "interestEarned": ("revenue", 10), "interestIncome": ("revenue", 10),
            "revenue": ("revenue", 20), "totalRevenue": ("revenue", 20),
        }
        requested_income_history = _history_from_period_rows(requested_income_rows, period, revenue_aliases, scale=10_000_000)
        standalone_income_history = _history_from_period_rows(standalone_income_rows, period, revenue_aliases, scale=10_000_000)
        if _history_length(requested_income_history, "revenue") == 0 and _history_length(standalone_income_history, "revenue") > 0:
            income_rows = standalone_income_rows
            balance_rows = _finedge_statement(symbol, "standalone", "bs", period)
            cash_rows = _finedge_statement(symbol, "standalone", "cf", period)
            effective_statement_type = "standalone"
            data_sources["incomeStatement"] = "finedge:standalone"
            data_sources["balanceSheet"] = "finedge:standalone"
            data_sources["cashFlow"] = "finedge:standalone"

    # Both pages consume this resolver: FinEdge actuals -> complete identities
    # calculated from FinEdge -> matching Upstox observations -> unavailable.
    try:
        from backend.fundamental_resolution import recover_inputs
    except ImportError:
        from fundamental_resolution import recover_inputs
    raw_section = "annual" if period == "yearly" else "quarterly"
    quarterly_income_rows = income_rows if period == "quarterly" else _finedge_statement(symbol, effective_statement_type, "pl", "quarterly")
    shared_raw = {"profile": profile_payload, raw_section: {"financials": income_rows},
                  "balance": {"financials": balance_rows}, "cashflow": {"financials": cash_rows}}
    if period == "yearly":
        shared_raw["quarterly"] = {"financials": quarterly_income_rows}
    else:
        # Same-basis annual figures can recover an absent/malformed Q4 by
        # subtraction. This optional source never changes the selected basis.
        annual_for_recovery = _safe_finedge_get(f"/financials/{_stock_symbol_path(symbol)}",
            {"statement_type": "c" if effective_statement_type == "consolidated" else "s", "statement_code": "pl", "period": "annual"}, default={})
        shared_raw["annual_for_quarter_recovery"] = {"financials": _payload_items(annual_for_recovery, ["financials", "data", "results", "items"])}
    def shared_load(section):
        if not instrument.get("isin"):
            return None
        isin = quote(instrument["isin"], safe="")
        if section in ("annual", "quarterly"):
            return _safe_upstox_get(f"/fundamentals/{isin}/income-statement",
                {"type": effective_statement_type, "time_period": "yearly" if section == "annual" else "quarterly", "fs": "true"}, default={})
        if section == "cashflow":
            return _safe_upstox_get(f"/fundamentals/{isin}/cash-flow", {"type": effective_statement_type, "fs": "true"}, default={})
        if section == "balance":
            return _safe_upstox_get(f"/fundamentals/{isin}/balance-sheet", {"type": effective_statement_type, "fs": "true"}, default={})
        return None
    shared_raw, resolution_notes = recover_inputs(shared_raw, effective_statement_type, datetime.now(timezone.utc).date(), shared_load, period=period, recover_prices=False)
    income_rows = shared_raw.get(raw_section, {}).get("financials", [])
    quarterly_income_rows = shared_raw.get("quarterly", {}).get("financials", quarterly_income_rows)
    balance_rows = shared_raw.get("balance", {}).get("financials", [])
    cash_rows = shared_raw.get("cashflow", {}).get("financials", [])
    for note in resolution_notes:
        if note.startswith("Upstox") and "recovered periods" in note:
            data_sources["cashFlow" if "cashflow" in note else "balanceSheet" if "Upstox balance " in note else "incomeStatement"] = "finedge+upstox:fallback"
    if resolution_notes:
        data_quality.append({"severity": "info", "section": "sourceResolution", "code": "shared_resolution",
            "message": f"Shared FinEdge calculation/recovery checks applied ({len(resolution_notes)} observations).", "details": resolution_notes})

    normalized_income_statement = _history_from_period_rows(income_rows, period, INCOME_STATEMENT_ALIASES, scale=10_000_000)
    bank_asset_quality = _normalize_bank_asset_quality_history(income_rows, period)
    bank_asset_quality_statement_type = effective_statement_type
    if not bank_asset_quality and effective_statement_type == "consolidated":
        bank_asset_quality = _normalize_bank_asset_quality_history(standalone_income_rows, period)
        if bank_asset_quality:
            bank_asset_quality_statement_type = "standalone"
            data_sources["bankAssetQuality"] = "finedge:standalone"
    if period == "yearly":
        normalized_income_statement = _merge_category_history(
            normalized_income_statement,
            "depreciation",
            _cash_flow_depreciation_history(cash_rows, period),
            source="derived_cash_flow",
        )
    income_statement = {
        "units_in": "Cr",
        "income_statement": _derive_income_metrics(normalized_income_statement),
    }
    balance_history, balance_categories = _balance_history(balance_rows, period)
    balance_sheet = {
        "units_in": "Cr",
        "history": balance_history,
        "balance_sheet": balance_categories,
    }
    cash_flow = {
        "units_in": "Cr",
        "cash_flow": _history_from_period_rows(cash_rows, period, {
            "netCashFromOperatingActivities": "operating", "cashFromOperatingActivity": "operating",
            "operatingCashFlow": "operating", "cashFlowFromOperatingActivities": "operating",
            "cashFlowsFromOperatingActivities": "operating",
            "netCashUsedInInvestingActivities": "investing", "cashFromInvestingActivity": "investing",
            "investingCashFlow": "investing", "cashFlowFromInvestingActivities": "investing",
            "cashFlowsFromInvestingActivities": "investing",
            "netCashUsedInFinancingActivities": "financing", "cashFromFinancingActivity": "financing",
            "financingCashFlow": "financing", "cashFlowFromFinancingActivities": "financing",
            "cashFlowsFromFinancingActivities": "financing",
        }, scale=10_000_000),
    }

    finedge_type = "c" if effective_statement_type == "consolidated" else "s"
    segment_payload = {} if lean else _safe_finedge_get(
        f"/segment-revenue/{_stock_symbol_path(symbol)}",
        {"statement_type": finedge_type, "statement_code": "pl", "period": "annual" if period == "yearly" else "quarterly"},
        default={},
    )
    current_year = datetime.now(timezone.utc).year
    ratio_payloads = [
        _safe_finedge_get(f"/ratios/{_stock_symbol_path(symbol)}", {"statement_type": finedge_type, "ratio_type": ratio_type}, default=[])
        for ratio_type in ("ef", "le", "li", "pr")
    ]
    profitability_ratios = _normalize_profitability_ratio_history(ratio_payloads[-1] if ratio_payloads else [])
    daily_price_ratio_payload = _safe_finedge_get(
        f"/daily-price-ratios/{_stock_symbol_path(symbol)}",
        {"statement_type": finedge_type, "from": str(current_year), "to": str(current_year)},
        default={},
    )
    price_ratio_snapshot = _latest_price_ratio_snapshot(daily_price_ratio_payload)
    metric_payloads = [
        _safe_finedge_get(f"/financial-metrics/{_stock_symbol_path(symbol)}", {"statement_type": finedge_type, "ratio_type": ratio_type}, default=[])
        for ratio_type in ("cu", "gr", "av")
    ]
    basic_financials_payload = _safe_finedge_get(
        f"/basic-financials/{_stock_symbol_path(symbol)}",
        {"statement_type": finedge_type, "statement_code": "pl"},
        default={},
    )
    upstox_key = instrument.get("upstoxInstrumentKey")
    upstox_isin = instrument.get("isin")
    upstox_statement_type = effective_statement_type
    ratios = _normalize_ratio_items(
        *ratio_payloads,
        *metric_payloads,
        basic_financials_payload,
    )
    # Calculate available FinEdge ratios before considering a secondary provider.
    live_quote = _quote_from_finedge_quote(_safe_finedge_get("/quote", {"symbol": symbol}, default={}), symbol)
    pre_profile = _normalize_profile(profile_payload, instrument)
    if live_quote.get("marketCap") is not None:
        pre_profile["marketCap"] = live_quote["marketCap"]
    pre_quarterly = {"income_statement": _derive_income_metrics(_history_from_period_rows(quarterly_income_rows, "quarterly", INCOME_STATEMENT_ALIASES, scale=10_000_000))}
    ratios = _reconcile_valuation_ratios(ratios, pre_profile, income_statement, balance_sheet, price_ratio_snapshot, _ttm_net_profit_from_statement(pre_quarterly))
    try:
        from backend.benchmark_resolution import merge_sector_values, reported_benchmarks
    except ImportError:
        from benchmark_resolution import merge_sector_values, reported_benchmarks
    benchmark_observations = reported_benchmarks(
        [row for payload in ratio_payloads + metric_payloads + [basic_financials_payload] for row in _payload_items(payload)],
        [], datetime.now(timezone.utc).isoformat())
    upstox_ratio_payload = []
    if upstox_isin:
        finedge_ratio_keys = {str(ratio.get("name") or "").upper() for ratio in ratios if isinstance(ratio, dict)}
        upstox_ratio_payload = _safe_upstox_get(f"/fundamentals/{quote(upstox_isin, safe='')}/key-ratios", default=[])
        if not {"P/E", "P/B", "ROE", "ROCE"}.issubset(finedge_ratio_keys):
            calculated_ratios = ratios
            ratios = _normalize_ratio_items(
                calculated_ratios,
                *ratio_payloads,
                *metric_payloads,
                basic_financials_payload,
                upstox_ratio_payload,
            )
            data_sources["ratios"] = "finedge+upstox:fallback"
        ratios = merge_sector_values(ratios, upstox_ratio_payload)
        benchmark_observations += reported_benchmarks([], upstox_ratio_payload, datetime.now(timezone.utc).isoformat())
    if benchmark_observations:
        data_sources["valuationBenchmarks"] = "+".join(sorted({r["provider"].lower() for r in benchmark_observations}))
    upstox_income_payload = None
    if upstox_isin:
        upstox_income_payload = _safe_upstox_get(
            f"/fundamentals/{quote(upstox_isin, safe='')}/income-statement",
            {"type": upstox_statement_type, "time_period": period, "fs": "true"},
            default={},
        )
        data_quality.extend(_income_statement_quality_warnings(income_statement, upstox_income_payload, period))
    if _history_length(income_statement.get("income_statement"), "revenue") == 0:
        if upstox_income_payload is None:
            upstox_income_payload = _safe_upstox_get(
                f"/fundamentals/{quote(upstox_isin or '', safe='')}/income-statement",
                {"type": upstox_statement_type, "time_period": period, "fs": "true"},
                default={},
            ) if upstox_isin else {}
        upstox_income_rows = _normalize_upstox_statement(upstox_income_payload, "income_statement", period)
        if upstox_income_rows:
            income_statement = {"units_in": "Cr", "income_statement": upstox_income_rows}
            data_sources["incomeStatement"] = "upstox"
            data_quality.append({
                "severity": "info",
                "section": "incomeStatement",
                "metric": "Revenue",
                "code": "finedge_income_statement_missing_upstox_fallback",
                "message": "FinEdge did not provide usable income statement revenue, so Upstox was used as a fallback source.",
            })
    if not balance_sheet.get("history"):
        upstox_balance_payload = _safe_upstox_get(
            f"/fundamentals/{quote(upstox_isin or '', safe='')}/balance-sheet",
            {"type": upstox_statement_type, "fs": "true"},
            default={},
        ) if upstox_isin else {}
        upstox_balance_history = _normalize_upstox_balance_sheet(upstox_balance_payload, period)
        if upstox_balance_history:
            try:
                from backend.fundamental_resolution import balance_rows as resolved_balance_rows
            except ImportError:
                from fundamental_resolution import balance_rows as resolved_balance_rows
            balance_rows = resolved_balance_rows(upstox_balance_payload, effective_statement_type)
            if balance_rows:
                upstox_balance_history, upstox_balance_categories = _balance_history(balance_rows, period)
            else:
                upstox_balance_categories = []
            balance_sheet = {"units_in": "Cr", "history": upstox_balance_history, "balance_sheet": upstox_balance_categories}
            data_sources["balanceSheet"] = "upstox"
            data_quality.append({
                "severity": "info",
                "section": "balanceSheet",
                "code": "finedge_balance_sheet_missing_upstox_fallback",
                "message": "FinEdge did not provide usable balance sheet history, so Upstox was used as a fallback source.",
            })
    if not any((row.get("history") for row in cash_flow.get("cash_flow", []))):
        upstox_cash_payload = _safe_upstox_get(
            f"/fundamentals/{quote(upstox_isin or '', safe='')}/cash-flow",
            {"type": upstox_statement_type, "fs": "true"},
            default={},
        ) if upstox_isin else {}
        upstox_cash_rows = _normalize_upstox_statement(upstox_cash_payload, "cash_flow", period)
        if upstox_cash_rows:
            cash_flow = {"units_in": "Cr", "cash_flow": upstox_cash_rows}
            data_sources["cashFlow"] = "upstox"
            data_quality.append({
                "severity": "info",
                "section": "cashFlow",
                "code": "finedge_cash_flow_missing_upstox_fallback",
                "message": "FinEdge did not provide usable cash-flow history, so Upstox was used as a fallback source.",
            })

    profile = _normalize_profile(profile_payload, instrument)
    profile_needs_upstox = not profile.get("description") or not profile.get("sector") or not profile.get("marketCap")
    if upstox_isin and profile_needs_upstox:
        upstox_profile_payload = _safe_upstox_get(f"/fundamentals/{quote(upstox_isin, safe='')}/profile", default={})
        if not isinstance(upstox_profile_payload, dict):
            upstox_profile_payload = {}
        upstox_market_cap = upstox_profile_payload.get("sector_market_cap_inr")
        upstox_market_cap_value = upstox_market_cap.get("value") if isinstance(upstox_market_cap, dict) else None
        filled_from_upstox = (
            (not profile.get("description") and upstox_profile_payload.get("company_profile"))
            or (not profile.get("sector") and upstox_profile_payload.get("sector"))
            or (not profile.get("marketCap") and upstox_market_cap_value)
        )
        profile = {
            **profile,
            "description": profile.get("description") or upstox_profile_payload.get("company_profile"),
            "sector": profile.get("sector") or upstox_profile_payload.get("sector"),
            "marketCap": profile.get("marketCap") or upstox_market_cap_value,
        }
        if filled_from_upstox:
            data_sources["profile"] = "finedge+upstox:fallback"
    if live_quote.get("marketCap"):
        profile = {**profile, "marketCap": live_quote.get("marketCap")}
    quarterly_income_statement = None
    if period == "quarterly":
        quarterly_income_statement = income_statement
    else:
        if quarterly_income_rows:
            quarterly_income_statement = {
                "units_in": "Cr",
                "income_statement": _derive_income_metrics(_history_from_period_rows(quarterly_income_rows, "quarterly", INCOME_STATEMENT_ALIASES, scale=10_000_000)),
            }
    ratios = _reconcile_valuation_ratios(ratios, profile, income_statement, balance_sheet, price_ratio_snapshot, _ttm_net_profit_from_statement(quarterly_income_statement))
    shareholding_payload = [] if lean else _safe_finedge_get(f"/shareholdings/pattern/{_stock_symbol_path(symbol)}", {"period": "quarterly"}, default=[])
    ownership_summary = _safe_finedge_get(f"/shareholdings/summary/{_stock_symbol_path(symbol)}", {"period": "quarterly"}, default={})
    ownership_distribution = _safe_finedge_get(f"/shareholdings/distribution/{_stock_symbol_path(symbol)}", {"period": "quarterly"}, default={})
    ownership_declaration = _safe_finedge_get(f"/shareholdings/declaration/{_stock_symbol_path(symbol)}", {"period": "quarterly"}, default={})
    ownership_structure = _normalize_ownership_structure(ownership_summary, ownership_distribution, ownership_declaration)
    shareholding = _normalize_shareholding(shareholding_payload, "quarterly")
    if not shareholding and upstox_isin and not lean:
        shareholding = _normalize_upstox_shareholding(_safe_upstox_get(f"/fundamentals/{quote(upstox_isin, safe='')}/share-holdings", default=[]))
        if shareholding:
            data_sources["shareholding"] = "upstox"
    actions_payload = [] if lean else _safe_finedge_get(
        "/corporate-actions/all",
        {"symbol": symbol, "from_date": f"{current_year - 6}-01-01", "to_date": f"{current_year + 1}-12-31"},
        default=[],
    )
    dividends_payload = [] if lean else _safe_finedge_get(f"/dividend/{_stock_symbol_path(symbol)}", default=[])
    corporate_actions = _normalize_corporate_actions(actions_payload, dividends_payload)
    if not corporate_actions and upstox_isin and not lean:
        corporate_actions = _normalize_corporate_actions(_safe_upstox_get(f"/fundamentals/{quote(upstox_isin, safe='')}/corporate-actions", default=[]))
        if corporate_actions:
            data_sources["corporateActions"] = "upstox"
    competitors = [] if lean else _normalize_competitors(_safe_finedge_get(f"/peers/{_stock_symbol_path(symbol)}", default=[]), symbol)
    if competitors:
        competitors = _enrich_competitors_from_finedge(competitors)
    if upstox_key and not competitors and not lean:
        upstox_competitors = _normalize_upstox_competitors(
            _safe_upstox_get(f"/fundamentals/{quote(upstox_key, safe='')}/competitors", default=[]),
            competitors,
        )
        if upstox_competitors:
            competitors = upstox_competitors
            data_sources["competitors"] = "upstox"

    price_payload = _safe_finedge_get(
        f"/daily-quotes/{_stock_symbol_path(symbol)}",
        {"from": str(current_year - 6), "to": str(current_year)}, default=[],
    )
    def load_prices(section):
        if section != "prices" or not upstox_key:
            return None
        return {"prices": _fetch_upstox_price_history(upstox_key), "exchange": upstox_instrument.get("exchange"), "instrumentKey": upstox_key}
    resolved_prices, price_notes = recover_inputs({"prices": price_payload}, effective_statement_type,
        datetime.now(timezone.utc).date(), load_prices)
    price_history = _normalize_price_history(resolved_prices.get("prices"))
    resolution_notes.extend(price_notes)
    if any("complete Upstox" in note for note in price_notes):
        data_sources["priceHistory"] = "upstox:fallback"
        data_quality.append({"severity": "info", "section": "priceHistory", "code": "shared_price_recovery", "message": price_notes[-1]})
    quote_data = live_quote if live_quote.get("price") and live_quote["price"] > 0 else _quote_from_price_history(price_history)
    if quote_data is not live_quote and quote_data.get("price"):
        data_sources["quote"] = "calculated_finedge_price_history" if data_sources["priceHistory"] == "finedge" else "upstox:price_history_fallback"
    if not quote_data.get("price"):
        try:
            upstox_quote = _quote_from_upstox(instrument)
        except Exception:
            logger.warning("Optional Upstox quote lookup failed for %s", symbol)
            upstox_quote = {}
        if upstox_quote.get("price"):
            quote_data = upstox_quote
            data_sources["quote"] = "upstox"
    lookup = _ratio_lookup(ratios)
    if _to_number((lookup.get("DIVIDEND YIELD") or {}).get("company_value")) is None:
        dividend_yield = _derive_dividend_yield(corporate_actions, quote_data.get("price"), quote_data.get("timestamp"))
        if dividend_yield is not None:
            ratios = _upsert_ratio(ratios, "Dividend Yield", round(dividend_yield, 2), None, "derived_finedge_dividends")

    lookup = _ratio_lookup(ratios)
    latest_revenue = _latest_history_value(income_statement.get("income_statement"), "revenue")
    latest_net_profit = _latest_history_value(income_statement.get("income_statement"), "net_profit")
    highlights = [
        {"label": "P/E", "value": lookup.get("P/E", {}).get("company_value"), "benchmark": lookup.get("P/E", {}).get("sector_value")},
        {"label": "P/B", "value": lookup.get("P/B", {}).get("company_value"), "benchmark": lookup.get("P/B", {}).get("sector_value")},
        {"label": "ROE", "value": lookup.get("ROE", {}).get("company_value"), "benchmark": lookup.get("ROE", {}).get("sector_value")},
        {"label": "ROCE", "value": lookup.get("ROCE", {}).get("company_value"), "benchmark": lookup.get("ROCE", {}).get("sector_value")},
        {"label": "Revenue", "value": latest_revenue.get("value") if latest_revenue else None, "period": latest_revenue.get("period") if latest_revenue else None, "unit": income_statement.get("units_in"), "change": latest_revenue.get("change") if latest_revenue else None},
        {"label": "Net Profit", "value": latest_net_profit.get("value") if latest_net_profit else None, "period": latest_net_profit.get("period") if latest_net_profit else None, "unit": income_statement.get("units_in"), "change": latest_net_profit.get("change") if latest_net_profit else None},
    ]

    revenue_segments = _normalize_revenue_segments(segment_payload, period, income_statement, data_quality)
    result = {
        "provider": "finedge",
        "sources": data_sources,
        "query": query,
        "requestedStatementType": statement_type,
        "statementType": effective_statement_type,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "cached": False,
        "instrument": instrument,
        "quote": quote_data,
        "priceHistory": price_history,
        "profile": profile,
        "highlights": [item for item in highlights if item.get("value") not in (None, "")],
        "ratios": ratios,
        "valuationBenchmarks": benchmark_observations,
        "profitabilityRatios": profitability_ratios,
        "bankAssetQuality": bank_asset_quality,
        "bankAssetQualityStatementType": bank_asset_quality_statement_type,
        "revenueSegments": revenue_segments,
        "incomeStatement": income_statement,
        "balanceSheet": balance_sheet,
        "cashFlow": cash_flow,
        "shareholding": shareholding,
        "shareholdingDetails": _normalize_detailed_shareholding(shareholding_payload),
        "ownershipStructure": ownership_structure,
        "corporateActions": corporate_actions,
        "competitors": competitors,
        "dataQuality": data_quality,
    }
    result["devMetrics"] = _stock_dev_metrics(result, started_at)
    model_inputs = {"profile": profile_payload, "income": {"financials": income_rows},
        "balance": {"financials": balance_rows}, "cashflow": {"financials": cash_rows},
        "prices": {"price": price_history}, "summary": ownership_summary,
        "distribution": ownership_distribution, "declaration": ownership_declaration,
        "assetQualityRows": standalone_income_rows if bank_asset_quality_statement_type == "standalone" else income_rows,
        "assetQualityBasis": bank_asset_quality_statement_type, "resolutionNotes": resolution_notes,
        "benchmarkObservations": benchmark_observations}
    model_inputs["technicalPrices"] = resolved_prices.get("prices", {})
    model_inputs["leverage"] = ratio_payloads[1]
    model_inputs["secondaryLeverage"] = next((row.get("company_value") for row in upstox_ratio_payload
        if isinstance(row,dict) and re.sub(r'[^a-z]','',str(row.get('name','')).lower())=='financialleverage'),None) if isinstance(upstox_ratio_payload,list) else None
    if lean:
        for skipped in ("revenueSegments", "shareholding", "corporateActions", "competitors"):
            result["sources"].pop(skipped, None)    # not fetched for a premium report, so not claimed
    else:
        _remember_stock_fundamentals(cache_key, {"data": result, "model_inputs": model_inputs, "fetched_at": monotonic()})
    if _model_capture is not None:
        _model_capture.update(model_inputs)
    return result


def _public_market_feed(section, params):
    key = (section, tuple(sorted(params.items())))
    cached = _public_market_cache.get(key)
    if cached and monotonic() - cached["stored_at"] < 300:
        return {**cached["data"], "cached": True}
    try:
        payload = _finedge_get(MARKET_ENDPOINTS[section], params)
        items = normalize_market_payload(section, payload)
    except (HTTPException, requests.RequestException, ValueError):
        logger.warning("Market feed unavailable: %s", section)
        raise HTTPException(status_code=502, detail="This market feed is temporarily unavailable. Please try again.")
    data = {"section": section, "items": items, "total": len(items), "provider": "FinEdge", "filters": params,
            "fetchedAt": datetime.now(timezone.utc).isoformat(), "cached": False}
    if len(_public_market_cache) >= 256:
        _public_market_cache.pop(next(iter(_public_market_cache)))
    _public_market_cache[key] = {"data": data, "stored_at": monotonic()}
    return data


@api_router.get("/market-data/{section}")
async def admin_market_data(
    section: Literal["ipo", "results", "announcements", "transcripts", "indices", "valuations"],
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    symbol: Optional[str] = Query(None, max_length=30),
    index_symbol: Optional[str] = Query(None, max_length=60),
    _admin=Depends(require_admin),
):
    try:
        params = market_params(section, from_date, to_date, symbol, index_symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await asyncio.to_thread(_public_market_feed, section, params)


def _commodity_feed(category=None, code=None):
    try:
        from backend.market_data import normalize_commodity_list, normalize_commodity_history, normalize_commodity_changes
    except ImportError:
        from market_data import normalize_commodity_list, normalize_commodity_history, normalize_commodity_changes
    key = ("commodities", code or category)
    cached = _public_market_cache.get(key)
    if cached and monotonic() - cached["stored_at"] < 300:
        return {**cached["data"], "cached": True}
    try:
        if code:
            data = {"code": code, "history": normalize_commodity_history(_finedge_get(f"/commodity-price/{code}"))}
            try:
                data["changes"] = normalize_commodity_changes(_finedge_get(f"/commodity-pct-change/{code}"))
            except (HTTPException, requests.RequestException, ValueError):
                data["changes"] = []
                data["changesUnavailable"] = True
        else:
            data = {"items": normalize_commodity_list(_finedge_get("/commodity-list", {"category": category})), "category": category}
    except (HTTPException, requests.RequestException, ValueError):
        raise HTTPException(status_code=502, detail="Commodity data is temporarily unavailable. Please try again.")
    data.update({"provider": "FinEdge", "fetchedAt": datetime.now(timezone.utc).isoformat(), "cached": False})
    if len(_public_market_cache) >= 256:
        _public_market_cache.pop(next(iter(_public_market_cache)))
    _public_market_cache[key] = {"data": data, "stored_at": monotonic()}
    return data


@api_router.get("/commodities")
async def commodity_list(category: Literal["monthly_index", "core_infra"] = "monthly_index", _admin=Depends(require_admin)):
    return await asyncio.to_thread(_commodity_feed, category=category)


@api_router.get("/commodities/{code}")
async def commodity_history(code: str, _admin=Depends(require_admin)):
    if not re.fullmatch(r"[0-9]{1,12}", code):
        raise HTTPException(status_code=400, detail="Select a valid commodity code.")
    return await asyncio.to_thread(_commodity_feed, code=code)


@api_router.get("/market-ticker")
async def market_ticker():
    """Return cached, normalized Upstox quotes without exposing the API token."""
    cached_items = _market_ticker_cache["items"]
    if cached_items and monotonic() - _market_ticker_cache["fetched_at"] < MARKET_TICKER_CACHE_SECONDS:
        return {"items": cached_items, "cached": True}

    access_token = os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    if not access_token:
        if cached_items:
            return {"items": cached_items, "cached": True, "stale": True}
        raise HTTPException(status_code=503, detail="Market data is not configured.")

    try:
        instruments = configured_market_ticker_instruments()
        items = await asyncio.to_thread(_fetch_upstox_quotes, instruments, access_token)
    except Exception:
        # Deliberately keep provider details out of logs: request headers include
        # a bearer token, and some errors echo request metadata.
        logger.warning("Market ticker provider request failed")
        if cached_items:
            return {"items": cached_items, "cached": True, "stale": True}
        raise HTTPException(status_code=503, detail="Market data is temporarily unavailable.")

    _market_ticker_cache.update({"items": items, "fetched_at": monotonic()})
    return {"items": items, "cached": False, "timestamp": int(time())}


FINLIT_CHAT_SYSTEM_INSTRUCTION = """You are FinLit AI, FinLit Ventures' knowledgeable, professional financial education assistant.

  Communication: answer the user's actual question immediately in clear, conversational language. Be intelligent but approachable, concise without being superficial, and financially accurate. Avoid greetings, congratulations, filler, repeated introductions, and opening with a generic disclaimer. The chat already displays a permanent financial disclaimer; add only a brief qualification when an example could otherwise be mistaken for a personal recommendation. Use short paragraphs and, when useful, simple Markdown with bold emphasis and concise numbered or bulleted lists. Do not use Markdown tables; use a short bulleted comparison instead. Do not output HTML.

Explain concepts with simple, realistic Indian examples when useful. When a user provides salary or other personal figures, use them only to build a clearly illustrative example. Do not imply that sample expenses, savings, or investment allocations are a recommendation for that person.

  Safety and accuracy: provide general financial education, not personalized buy/sell recommendations. Never guarantee returns or make overly confident claims about investment outcomes. Do not invent live market data, company services, credentials, published pricing, or FinLit performance figures. Do not quote current savings-account rates, fixed-deposit rates, returns, inflation figures, or market statistics unless they are supplied by an approved, verified data source. If asked for current market or performance data and no such source is available, say you cannot verify live figures and direct the visitor to the Portfolio page. Clearly label hypothetical figures as illustrative, not forecasts or recommendations. Explain liquidity accurately: savings-account balances are generally available subject to account terms and transaction limits; fixed deposits are designed for a chosen term and ordinarily pay at maturity. Premature FD withdrawal may be restricted or subject to a penalty or reduced interest under the bank's terms, so do not describe an FD as instantly accessible. If asked what they personally should buy or sell, explain general evaluation factors and invite them to contact the team.

Verified FinLit services: 0 → 1 Investing (help understanding stocks, ETFs, mutual funds and other options, with a strategy aligned to goals and risk); Wealth Planning (strategies to grow, diversify and protect wealth across life stages); Family Financial Planning (a roadmap covering family goals, investments, insurance and future needs); Global Investing (understanding global opportunities alongside the overall portfolio and risk appetite); Portfolio Review & Stock Selection (review of diversification, risk, performance and holdings). Service prices are not published yet: tell visitors prices will be announced soon and that they can send an enquiry from the Services page. Never quote a price. For company-specific enquiries, guide visitors to the website Contact form or Services enquiry form."""
CHAT_STYLE_RULES = (
    "\n\nFormat rules (strict): reply in plain text only, no markdown symbols (no asterisks, no # headings, no tables). "
    "Keep every answer under 110 words: a direct answer in 2-4 short sentences, then at most 3 short lines starting with '- ' if a list helps. "
    "Offer to go deeper instead of covering everything."
)


def plain_chat_text(text: str) -> str:
    """Gemini sometimes ignores the no-markdown rule; the chat bubble shows plain text, so strip the symbols."""
    import re
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", text)
    text = re.sub(r"^(\s*)[*\u2022]\s+", r"\1- ", text, flags=re.M)
    text = text.replace("`", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


CHAT_TOOL_RULES = (
    "\n\nFinLit data tools: you can call tools that return verified figures from FinLit's database (prices, financial statements, ratios, shareholding, results, "
    "screener, index levels, institutional flows, IPOs, funds, ETFs). These tools are the approved, verified data source for the rule above about market figures. "
    "Use a tool for EVERY number about a company, fund, ETF, index or the market. Never invent, estimate or recall a figure from memory. Answer only from what the tools returned. "
    "If a figure is null, missing, locked or a tool returns an error, say plainly that it is not available; never write zero or a guess in its place. "
    "Give the as-of date (asOf) from the result next to the figures. If you only know a company's name, call search_stocks first. Use as few calls as needed. "
    "A locked FinLit score is a Silver plan feature on the website: say so. "
    "Describe the data neutrally. Never say or imply that anyone should buy, sell, hold, reduce, avoid or accumulate a security, and never give a price target or a prediction."
)
CHAT_TOOL_FALLBACK = "I couldn't finish looking that up. Please ask a narrower question, for example about one company or one figure."
_RECOMMENDATION_PATTERNS = (
    re.compile(r"\b(should|could|can|would|must|ought to|better to|recommend\w*|suggest\w*|advis\w*|consider|time to|good time to)\b[^.!?\n]{0,50}\b(buy|buying|sell|selling|hold|holding|accumulate|accumulating|reduce|reducing|avoid|avoiding)\b", re.I),
    re.compile(r"\b(price target|target price|buy rating|sell rating|hold rating|strong buy|a buy|a sell|worth buying|good buy|buying opportunity|accumulate)\b", re.I),
)


def strip_recommendations(text: str) -> str:
    """Safety net for answers built from tool data: any sentence that reads as advice to buy, sell, hold, reduce, avoid or accumulate, or as a target, is dropped."""
    lines = []
    for line in text.split("\n"):
        kept = [x for x in re.split(r"(?<=[.!?])\s+", line) if x.strip() and not any(p.search(x) for p in _RECOMMENDATION_PATTERNS)]
        if kept or not line.strip():
            lines.append(" ".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


CHAT_MAX_REQUESTS_PER_MINUTE = 10
CHAT_RATE_WINDOW_SECONDS = 60
CHAT_INITIAL_OUTPUT_TOKENS = 700
CHAT_RETRY_OUTPUT_TOKENS = 1600


def gemini_finish_reason(response) -> str:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return "UNKNOWN"
    reason = getattr(candidates[0], "finish_reason", None)
    if reason is None:
        return "UNKNOWN"
    return str(getattr(reason, "name", reason)).rsplit(".", 1)[-1].upper()


@api_router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request):
    api_key = os.environ.get("GEMINI_API_KEY")
    logger.info(
        "FinLit AI chat handler reached (gemini_api_key_configured=%s, vercel_env=%s, vercel_commit=%s)",
        bool(api_key),
        os.environ.get("VERCEL_ENV", "unset"),
        os.environ.get("VERCEL_GIT_COMMIT_SHA", "unset"),
    )
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Please enter a message.")
    client_ip = client_identifier(request)
    if rate_limit_exceeded(_chat_attempts, client_ip, monotonic(), CHAT_MAX_REQUESTS_PER_MINUTE, CHAT_RATE_WINDOW_SECONDS):
        raise HTTPException(status_code=429, detail="You’ve sent several messages. Please wait a minute and try again.")

    if not api_key:
        logger.warning("FinLit AI unavailable: GEMINI_API_KEY is not configured")
        raise HTTPException(status_code=503, detail="FinLit AI is temporarily unavailable. Please try again later.")

    model_id = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-3.8-flash"   # GEMINI_MODEL lets the model be changed without editing code
    bounded_history_length = sum(1 for turn in payload.history[-12:] if turn.content.strip())
    logger.info(
        "FinLit AI Gemini request (model_id=%s, bounded_history_length=%s)",
        model_id,
        bounded_history_length,
    )
    try:
        from google import genai
        from google.genai import types

        contents = [
            {"role": "model" if turn.role == "assistant" else "user", "parts": [{"text": turn.content.strip()}]}
            for turn in payload.history[-12:]
            if turn.content.strip()
        ]
        contents.append({"role": "user", "parts": [{"text": payload.message.strip()}]})
        client = genai.Client(api_key=api_key)

        # FinLit data tools (through the research API's MCP endpoint). Any problem here leaves the chat working as it always did, without tools.
        tool_config = None
        try:
            offered = await run_in_threadpool(mcp_tools.get_tools, client_ip)
            if offered:
                tool_config = [types.Tool(function_declarations=[types.FunctionDeclaration(**d) for d in mcp_tools.declarations(offered)])]
        except Exception as exc:
            logger.warning("FinLit AI tools not attached (event=chat_tools_unavailable, exception_type=%s)", type(exc).__name__)
            tool_config = None
        system_instruction = FINLIT_CHAT_SYSTEM_INSTRUCTION + CHAT_STYLE_RULES + (CHAT_TOOL_RULES if tool_config else "")

        async def generate(output_limit, with_tools=True):
            options = {"system_instruction": system_instruction, "max_output_tokens": output_limit}
            if tool_config and with_tools:
                options["tools"] = tool_config
                options["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)   # this code runs the tools, to count and limit them
            return await run_in_threadpool(
                client.models.generate_content,
                model=model_id,
                contents=contents,
                config=types.GenerateContentConfig(**options),
            )

        async def complete(with_tools=True):
            result = await generate(CHAT_INITIAL_OUTPUT_TOKENS, with_tools)
            attempt = 1
            finish_reason = gemini_finish_reason(result)
            if finish_reason == "MAX_TOKENS":
                logger.warning(
                    "FinLit AI generation truncated (event=gemini_max_tokens, finish_reason=%s, attempt=%s, "
                    "output_token_limit=%s, model_id=%s, bounded_history_length=%s)",
                    finish_reason,
                    attempt,
                    CHAT_INITIAL_OUTPUT_TOKENS,
                    model_id,
                    bounded_history_length,
                )
                attempt = 2
                result = await generate(CHAT_RETRY_OUTPUT_TOKENS, with_tools)
                finish_reason = gemini_finish_reason(result)
            if finish_reason == "MAX_TOKENS":
                logger.warning(
                    "FinLit AI generation truncated (event=gemini_max_tokens, finish_reason=%s, attempt=%s, "
                    "output_token_limit=%s, model_id=%s, bounded_history_length=%s)",
                    finish_reason,
                    attempt,
                    CHAT_RETRY_OUTPUT_TOKENS,
                    model_id,
                    bounded_history_length,
                )
                raise HTTPException(
                    status_code=502,
                    detail="FinLit AI couldn’t complete that response. Please try a more focused question.",
                )
            return result, finish_reason

        result, finish_reason = await complete()
        tools_used, tool_rounds, gave_up = [], 0, False
        while tool_config:
            wanted = list(getattr(result, "function_calls", None) or [])
            if not wanted:
                break
            if tool_rounds >= mcp_tools.MAX_TOOL_ROUNDS:    # the round limit: no more tools, the model must answer with what it has
                gave_up = True
                break
            tool_rounds += 1
            candidates = getattr(result, "candidates", None) or []
            model_turn = getattr(candidates[0], "content", None) if candidates else None
            contents.append(model_turn or {"role": "model", "parts": [{"function_call": {"name": c.name, "args": dict(c.args or {})}} for c in wanted]})
            replies = []
            for position, call in enumerate(wanted):
                if position < mcp_tools.MAX_CALLS_PER_ROUND:
                    succeeded, output = await run_in_threadpool(mcp_tools.call_tool, call.name, dict(call.args or {}), client_ip)
                    if succeeded and call.name not in tools_used:
                        tools_used.append(call.name)
                else:
                    output = {"error": "Too many tool calls at once; ask for fewer."}
                replies.append({"function_response": {"name": call.name, "response": output}})
            contents.append({"role": "user", "parts": replies})
            result, finish_reason = await complete()
        if gave_up:
            logger.warning("FinLit AI tool round limit reached (event=chat_tool_round_limit, tool_rounds=%s)", tool_rounds)
            contents.append({"role": "user", "parts": [{"text": "Answer now from the tool results you already have; say what could not be found."}]})
            result, finish_reason = await complete(with_tools=False)
        answer = plain_chat_text(getattr(result, "text", None) or "")
        if gave_up and not answer:
            answer = CHAT_TOOL_FALLBACK
        if tool_config and tools_used:
            answer = strip_recommendations(answer) or CHAT_TOOL_FALLBACK
        if not answer:
            raise RuntimeError("Gemini returned an empty response")
        if tools_used:
            answer += "\n\nData from FinLit tools: " + ", ".join(tools_used)
        logger.info("FinLit AI response ready (finish_reason=%s, response_chars=%s, tool_rounds=%s, tools_used=%s)", finish_reason, len(answer), tool_rounds, ",".join(tools_used) or "none")
        return ChatResponse(response=answer)
    except HTTPException:
        raise
    except Exception as exc:
        provider_status = getattr(exc, "code", None)
        if not isinstance(provider_status, int):
            provider_status = getattr(getattr(exc, "response", None), "status_code", None)
        if not isinstance(provider_status, int):
            provider_status = "unknown"
        logger.warning(
            "FinLit AI request failed (event=gemini_request_error, exception_type=%s, provider_status=%s, "
            "model_id=%s, bounded_history_length=%s)",
            type(exc).__name__,
            provider_status,
            model_id,
            bounded_history_length,
        )
        raise HTTPException(status_code=502, detail="FinLit AI couldn’t respond just now. Please try again.")


@api_router.post("/contact", response_model=ContactMessage)
async def create_contact(payload: ContactCreate, request: Request):
    if rate_limit_exceeded(_form_attempts, form_rate_limit_key("contact", request), monotonic(), FORM_MAX_REQUESTS_PER_HOUR, FORM_RATE_WINDOW_SECONDS):
        raise HTTPException(status_code=429, detail="Too many submissions. Please wait and try again.")
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    msg = ContactMessage(**payload.model_dump())
    doc = msg.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    # Persist the lead first so it is never lost, even if email delivery fails.
    await db.contact_messages.insert_one(doc)

    # Send email synchronously — only report success if the provider accepts it.
    try:
        await send_lead_emails(msg.model_dump(mode="json"), auto_reply=False)
    except EmailNotConfigured as e:
        logger.error("Contact email not sent: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Email service is not configured yet. Your message was saved but not emailed.",
        )
    except Exception as e:
        logger.exception("Contact email delivery failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="We couldn't send your message right now. Please try again shortly.",
        )
    return msg


@api_router.get("/contact", response_model=List[ContactMessage])
async def list_contacts(_admin=Depends(require_admin)):
    docs = await db.contact_messages.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for d in docs:
        if isinstance(d.get('created_at'), str):
            d['created_at'] = datetime.fromisoformat(d['created_at'])
    return docs


@api_router.get("/service-enquiry", response_model=List[ServiceEnquiry])
async def list_service_enquiries(_admin=Depends(require_admin)):
    """Enquiries from the Services page are always saved first; this is how an administrator reads them (also when email is not configured)."""
    docs = await db.service_enquiries.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for d in docs:
        if isinstance(d.get('created_at'), str):
            d['created_at'] = datetime.fromisoformat(d['created_at'])
    return docs


@api_router.post("/service-enquiry", response_model=ServiceEnquiry)
async def create_service_enquiry(payload: ServiceEnquiryCreate, request: Request):
    if rate_limit_exceeded(_form_attempts, form_rate_limit_key("service-enquiry", request), monotonic(), FORM_MAX_REQUESTS_PER_HOUR, FORM_RATE_WINDOW_SECONDS):
        raise HTTPException(status_code=429, detail="Too many submissions. Please wait and try again.")
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not payload.services:
        raise HTTPException(status_code=400, detail="Select at least one service")
    if payload.message.strip() and len(payload.message.strip()) < 10:
        raise HTTPException(status_code=400, detail="Message is too short")
    enquiry = ServiceEnquiry(**payload.model_dump())
    doc = enquiry.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.service_enquiries.insert_one(doc)

    try:
        await send_service_enquiry_email(enquiry.model_dump(mode="json"))
    except EmailNotConfigured as e:
        logger.error("Service enquiry email not sent: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Email service is not configured yet. Your enquiry was saved but not emailed.",
        )
    except Exception as e:
        logger.exception("Service enquiry email delivery failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="We couldn't send your enquiry right now. Please try again shortly.",
        )
    return enquiry


app.include_router(api_router)

DEFAULT_ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "financial-portfolio-m4eb.vercel.app",
    "finlitventures.com",
    "www.finlitventures.com",
]
DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://financial-portfolio-m4eb.vercel.app",
    "https://finlitventures.com",
    "https://www.finlitventures.com",
]


def configured_allowed_hosts():
    hosts = DEFAULT_ALLOWED_HOSTS + os.environ.get("ALLOWED_HOSTS", "").split(",")
    return list(dict.fromkeys(host.strip().lower() for host in hosts if host.strip()))


def configured_cors_origins():
    origins = DEFAULT_CORS_ORIGINS + os.environ.get("CORS_ORIGINS", "").split(",")
    return list(dict.fromkeys(origin.strip().rstrip("/") for origin in origins if origin.strip()))


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=configured_allowed_hosts(),
)


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=configured_cors_origins(),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Cache-Control", "Pragma"],
    max_age=600,
)


@app.on_event("startup")
async def mirror_existing_uploads():
    """Files already on disk (shipped with the code or uploaded before the MongoDB copy existed) are copied into MongoDB once,
    so a restart on a host with a temporary disk cannot lose them."""
    if not mongo_url:
        return
    try:
        async for asset in db.content_assets.find({}, {"_id": 0, "key": 1, "storedName": 1}):
            if await db.content_blobs.count_documents({"key": asset["key"]}, limit=1):
                continue
            path = CONTENT_STORAGE_DIR / asset.get("storedName", "")
            if path.is_file() and path.stat().st_size <= MAX_UPLOAD_BYTES:
                await db.content_blobs.replace_one({"key": asset["key"]}, {"key": asset["key"], "data": path.read_bytes()}, upsert=True)
    except Exception:
        logger.warning("Could not mirror existing uploads to MongoDB at startup")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
