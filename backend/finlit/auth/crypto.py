"""Password hashing, one-time tokens and authenticator (TOTP) codes. Nothing here touches the network or the database."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
import weakref
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken

_hasher = PasswordHasher()  # argon2id with the library's recommended (RFC 9106 low-memory) parameters
DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")
_sems: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def _sem() -> asyncio.Semaphore:
    """At most four hashes at once: each uses ~64 MB, so a login flood cannot exhaust memory."""
    loop = asyncio.get_running_loop()
    if loop not in _sems:
        _sems[loop] = asyncio.Semaphore(4)
    return _sems[loop]


async def hash_password(password: str) -> str:
    async with _sem():
        return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(stored: str, password: str) -> bool:
    async with _sem():
        try:
            return await asyncio.to_thread(_hasher.verify, stored, password)
        except (VerificationError, InvalidHashError):
            return False


def needs_rehash(stored: str) -> bool:
    return _hasher.check_needs_rehash(stored)


EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
COMMON = {"password", "password1", "password123", "123456789", "1234567890", "qwertyuiop", "iloveyou12", "letmein123", "welcome123",
          "admin12345", "finlit12345", "finlitventures", "11111111111", "0123456789", "abcdefghij", "passw0rd123"}


def normalise_email(email: str) -> Optional[str]:
    e = email.strip().lower()
    return e if len(e) <= 254 and EMAIL.match(e) else None


def password_problem(password: str, email: str = "") -> Optional[str]:
    """A short, human reason the password is not acceptable, or None. Length matters more than symbols (NIST SP 800-63B)."""
    if len(password) < 10:
        return "Use at least 10 characters."
    if len(password) > 128:
        return "Use 128 characters or fewer."
    low = password.lower()
    if low in COMMON or len(set(low)) < 5:
        return "That password is too easy to guess."
    local = email.split("@")[0].lower() if email else ""
    if local and len(local) >= 4 and local in low:
        return "Do not use your email name in your password."
    return None


def new_token() -> tuple[str, str]:
    """(raw token to give the user, hash to store). The raw value is never stored."""
    raw = secrets.token_urlsafe(32)
    return raw, token_hash(raw)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def fernet(secret_key: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("finlit-totp:" + secret_key).encode()).digest()))


def encrypt_secret(secret_key: str, value: str) -> str:
    return fernet(secret_key).encrypt(value.encode()).decode()


def decrypt_secret(secret_key: str, value: str) -> Optional[str]:
    try:
        return fernet(secret_key).decrypt(value.encode()).decode()
    except InvalidToken:
        return None


# ---- TOTP (RFC 6238, SHA-1, 30 s, 6 digits): compatible with every authenticator app
def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret_b32: str, step: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), "sha1").digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def verify_totp(secret_b32: str, code: str, last_step: int, now: Optional[float] = None) -> Optional[int]:
    """Matching time step (accepting one step either side for clock drift), or None. A step can be used once."""
    code = code.strip().replace(" ", "")
    if not re.fullmatch(r"\d{6}", code):
        return None
    current = int((time.time() if now is None else now) // 30)
    for step in (current, current - 1, current + 1):
        if step > last_step and hmac.compare_digest(totp_code(secret_b32, step), code):
            return step
    return None


def totp_uri(secret_b32: str, email: str, issuer: str = "FinLit Ventures") -> str:
    from urllib.parse import quote
    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret_b32}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
