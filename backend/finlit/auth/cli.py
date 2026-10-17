"""Command-line account tools, run on the server: `python -m finlit.auth.cli create-admin --email you@company.com`.

The password is read from the FINLIT_ADMIN_PASSWORD environment variable or prompted (never passed as an argument,
so it does not land in shell history or process lists)."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from ..config import get_settings
from ..store import Store
from . import crypto


async def create_admin(email: str, password: str) -> None:
    settings = get_settings()
    e = crypto.normalise_email(email)
    if not e:
        sys.exit("That is not a valid email address.")
    problem = crypto.password_problem(password, e)
    if problem:
        sys.exit(problem)
    store = await Store.connect(settings, migrate=True)
    try:
        pw = await crypto.hash_password(password)
        async with store.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (email, name, password_hash, role, plan, email_verified_at) VALUES ($1, 'Administrator', $2, 'admin', 'gold', now()) "
                "ON CONFLICT (lower(email)) DO UPDATE SET role = 'admin', plan = 'gold', password_hash = EXCLUDED.password_hash, "
                "email_verified_at = COALESCE(users.email_verified_at, now()), failed_logins = 0, locked_until = NULL, status = 'active'", e, pw)
        print(f"Administrator ready: {e}. Sign in, then set up the authenticator app when asked.")
    finally:
        await store.close()


async def reset_mfa(email: str) -> None:
    store = await Store.connect(get_settings(), migrate=True)
    try:
        async with store.pool.acquire() as conn:
            n = await conn.fetchval("UPDATE users SET totp_secret_enc = NULL, totp_enabled_at = NULL WHERE lower(email) = $1 RETURNING 1", email.strip().lower())
            await conn.execute("DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE lower(email) = $1)", email.strip().lower())
        print("Two-step sign-in cleared; sign in and set it up again." if n else "No such account.")
    finally:
        await store.close()


def main() -> None:
    ap = argparse.ArgumentParser(prog="finlit.auth.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("create-admin")
    a.add_argument("--email", required=True)
    r = sub.add_parser("reset-mfa")
    r.add_argument("--email", required=True)
    args = ap.parse_args()
    if args.cmd == "create-admin":
        pw = os.getenv("FINLIT_ADMIN_PASSWORD") or getpass.getpass("Password (10+ characters): ")
        asyncio.run(create_admin(args.email, pw))
    else:
        asyncio.run(reset_mfa(args.email))


if __name__ == "__main__":
    main()
