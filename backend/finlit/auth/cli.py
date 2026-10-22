"""Command-line account tools, run on the server: `python -m finlit.auth.cli create-admin --email you@company.com`.

The password is read from the FINLIT_ADMIN_PASSWORD environment variable or prompted (FINLIT_MEMBER_PASSWORD for create-member; never passed as an argument,
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


async def create_admin(email: str, password: str) -> str:
    """Make sure the administrator account exists. Run at every start with ADMIN_PASSWORD, so it must not undo later changes:
    - no account yet: it is created with this password;
    - the variable holds the same value as at the last start: nothing changes (a password changed under Account is kept);
    - the variable holds a new value: the owner chose a new password (the documented way back in without a shell). It is applied,
      the lockout cleared and every session ended;
    - an account that predates this check (no fingerprint): the value is recorded, the password is left as it is.
    Returns what happened: created | unchanged | password_set | adopted."""
    settings = get_settings()
    e = crypto.normalise_email(email)
    if not e:
        sys.exit("That is not a valid email address.")
    problem = crypto.password_problem(password, e)
    if problem:
        sys.exit(problem)
    store = await Store.connect(settings, migrate=True)
    try:
        async with store.pool.acquire() as conn:
            u = await conn.fetchrow("SELECT id, bootstrap_pw_hash FROM users WHERE lower(email) = $1", e)
        if u is None:
            pw = await crypto.hash_password(password)
            async with store.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO users (email, name, password_hash, bootstrap_pw_hash, role, plan, email_verified_at) "
                    "VALUES ($1, 'Administrator', $2, $3, 'admin', 'gold', now()) ON CONFLICT (lower(email)) DO NOTHING", e, pw, await crypto.hash_password(password))
            outcome = "created"
        elif u["bootstrap_pw_hash"] and await crypto.verify_password(u["bootstrap_pw_hash"], password):
            outcome = "unchanged"
        elif u["bootstrap_pw_hash"] is None:
            async with store.pool.acquire() as conn:
                await conn.execute("UPDATE users SET bootstrap_pw_hash = $2 WHERE id = $1", u["id"], await crypto.hash_password(password))
            outcome = "adopted"
        else:
            pw = await crypto.hash_password(password)
            async with store.pool.acquire() as conn:
                await conn.execute("UPDATE users SET password_hash = $2, bootstrap_pw_hash = $3, password_changed_at = now(), failed_logins = 0, "
                                   "locked_until = NULL WHERE id = $1", u["id"], pw, await crypto.hash_password(password))
                await conn.execute("DELETE FROM sessions WHERE user_id = $1", u["id"])
            try:   # the cached copies of those sessions too, as finlit.auth.service.forget_cached does
                hashes = await store.redis.smembers(f"usess:{u['id']}")
                if hashes:
                    await store.redis.delete(*[f"sess:{h.decode() if isinstance(h, bytes) else h}" for h in hashes])
                await store.redis.delete(f"usess:{u['id']}")
            except Exception:
                pass   # Redis unavailable: cached sessions expire on their own within two minutes
            outcome = "password_set"
        # Always: the account is an active, confirmed administrator on the top plan (a role or plan changed by mistake is put back).
        async with store.pool.acquire() as conn:
            await conn.execute("UPDATE users SET role = 'admin', plan = 'gold', status = 'active', email_verified_at = COALESCE(email_verified_at, now()) "
                               "WHERE lower(email) = $1", e)
        print({"created": f"Administrator created: {e}. Sign in, then set up the authenticator app when asked.",
               "unchanged": f"Administrator ready: {e} (ADMIN_PASSWORD unchanged since the last start; the current password is kept).",
               "password_set": f"Administrator {e}: ADMIN_PASSWORD changed, so it is now the password. Every session was signed out.",
               "adopted": f"Administrator ready: {e}. The current password is kept; a NEW value in ADMIN_PASSWORD will replace it at a later start."}[outcome])
        return outcome
    finally:
        await store.close()


async def create_member(email: str, password: str, plan: str, name: str) -> None:
    """A confirmed member on the given plan (demo and staging accounts, where no email can be sent). Safe to run again."""
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
                "INSERT INTO users (email, name, password_hash, role, plan, email_verified_at) VALUES ($1, $2, $3, 'investor', $4, now()) "
                "ON CONFLICT (lower(email)) DO UPDATE SET plan = EXCLUDED.plan, password_hash = EXCLUDED.password_hash, "
                "email_verified_at = COALESCE(users.email_verified_at, now()), failed_logins = 0, locked_until = NULL, status = 'active'", e, name, pw, plan)
        print(f"Member ready: {e} ({plan})")
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
    m = sub.add_parser("create-member")
    m.add_argument("--email", required=True)
    m.add_argument("--plan", choices=["basic", "silver", "gold"], default="basic")
    m.add_argument("--name", default="Demo member")
    r = sub.add_parser("reset-mfa")
    r.add_argument("--email", required=True)
    args = ap.parse_args()
    if args.cmd == "create-admin":
        pw = os.getenv("FINLIT_ADMIN_PASSWORD") or getpass.getpass("Password (10+ characters): ")
        asyncio.run(create_admin(args.email, pw))
    elif args.cmd == "create-member":
        pw = os.getenv("FINLIT_MEMBER_PASSWORD") or getpass.getpass("Password (10+ characters): ")
        asyncio.run(create_member(args.email, pw, args.plan, args.name))
    else:
        asyncio.run(reset_mfa(args.email))


if __name__ == "__main__":
    main()
