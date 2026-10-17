"""Outgoing email. Development writes to the `outbox` table so flows can be tested without sending anything;
production sends through Resend. Messages are plain text with one link: nothing sensitive is ever in the body."""

from __future__ import annotations

import logging
from typing import Optional, Protocol

import httpx

log = logging.getLogger("finlit.mail")


class Mailer(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleMailer:
    def __init__(self, pool):
        self.pool = pool

    async def send(self, to: str, subject: str, body: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO outbox (to_email, subject, body) VALUES ($1, $2, $3)", to, subject, body)
        log.info("mail (console) to=%s subject=%s", to, subject)


class ResendMailer:
    def __init__(self, api_key: str, sender: str):
        self.api_key, self.sender = api_key, sender
        self.client: Optional[httpx.AsyncClient] = None

    async def send(self, to: str, subject: str, body: str) -> None:
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=10)
        r = await self.client.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {self.api_key}"},
                                   json={"from": self.sender, "to": [to], "subject": subject, "text": body})
        if r.status_code >= 300:  # never log the body or the address
            log.error("resend failed status=%s", r.status_code)
            raise RuntimeError("mail provider rejected the message")


def verify_mail(link: str, name: Optional[str]) -> tuple[str, str]:
    hello = f"Hello {name}," if name else "Hello,"
    return ("Confirm your FinLit email", f"{hello}\n\nConfirm your email to finish creating your FinLit account:\n{link}\n\n"
            "The link works once and expires in 24 hours. If you did not sign up, ignore this message.\n\nFinLit Ventures")


def reset_mail(link: str) -> tuple[str, str]:
    return ("Reset your FinLit password", f"Someone asked to reset the password for this FinLit account.\n\nChoose a new one here:\n{link}\n\n"
            "The link works once and expires in 1 hour. If this was not you, ignore this message; your password is unchanged.\n\nFinLit Ventures")


def already_mail(link: str) -> tuple[str, str]:
    return ("You already have a FinLit account", f"Someone tried to sign up with this email address, but an account already exists.\n\n"
            f"Sign in or reset your password here:\n{link}\n\nIf this was not you, no action is needed.\n\nFinLit Ventures")
