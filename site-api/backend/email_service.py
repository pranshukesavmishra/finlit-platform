import os
import asyncio
import logging
from html import escape
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
import resend

load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
# Centralized recipient for all contact-form submissions.
CONTACT_RECIPIENT_EMAIL = os.environ.get("CONTACT_RECIPIENT_EMAIL", "")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


class EmailNotConfigured(Exception):
    """Raised when the email provider is not configured."""


def is_configured() -> bool:
    return bool(RESEND_API_KEY and CONTACT_RECIPIENT_EMAIL)


def _fmt_ts(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str)
    except Exception:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%d %b %Y, %H:%M UTC")


def _row(label, value):
    if not value:
        return ""
    safe_value = escape(str(value), quote=True)
    return (
        f'<tr><td style="padding:6px 12px;color:#64748B;font-size:13px;">{label}</td>'
        f'<td style="padding:6px 12px;color:#0A1E3F;font-size:14px;font-weight:600;">{safe_value}</td></tr>'
    )


def _safe_text(value):
    """Escape submitted text at the HTML rendering boundary."""
    return escape(str(value or ""), quote=True)


def _safe_message(value):
    """Escape a message while retaining its submitted line breaks."""
    return _safe_text(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>\n")


def _alert_html(lead):
    return f"""
    <div style="background:#050E1D;padding:32px;font-family:Arial,sans-serif;">
      <table style="max-width:560px;margin:auto;background:#ffffff;border-radius:12px;overflow:hidden;">
        <tr><td style="background:#0A1E3F;padding:24px 28px;">
          <div style="color:#F5A623;font-size:12px;letter-spacing:2px;text-transform:uppercase;">New Contact Message</div>
          <div style="color:#ffffff;font-size:22px;font-weight:700;margin-top:6px;">Nishant Jain — Equity Research</div>
        </td></tr>
        <tr><td style="padding:24px 16px;">
          <table style="width:100%;border-collapse:collapse;">
            {_row("Full Name", lead.get("name"))}
            {_row("Email Address", lead.get("email"))}
            {_row("Mobile Number", lead.get("phone"))}
            {_row("Subject", lead.get("subject"))}
            {_row("Received", _fmt_ts(lead.get("created_at")))}
          </table>
          <div style="margin:18px 12px 0;color:#64748B;font-size:13px;">Message</div>
          <div style="margin:6px 12px;padding:14px;background:#F1F5F9;border-radius:8px;color:#0A1E3F;font-size:14px;line-height:1.6;">
            {_safe_message(lead.get("message", ""))}
          </div>
        </td></tr>
        <tr><td style="padding:16px 28px;background:#F8FAFC;color:#94A3B8;font-size:12px;">
          Reply directly to {_safe_text(lead.get("email"))} to respond to this enquiry.
        </td></tr>
      </table>
    </div>
    """


def _reply_html(lead):
    return f"""
    <div style="background:#050E1D;padding:32px;font-family:Arial,sans-serif;">
      <table style="max-width:560px;margin:auto;background:#ffffff;border-radius:12px;overflow:hidden;">
        <tr><td style="background:#0A1E3F;padding:28px;">
          <div style="color:#ffffff;font-size:22px;font-weight:700;">Thank you, {_safe_text(lead.get("name", ""))}</div>
          <div style="color:#F5A623;font-size:13px;margin-top:6px;">Nishant Jain · Independent Equity Research</div>
        </td></tr>
        <tr><td style="padding:28px;color:#334155;font-size:15px;line-height:1.7;">
          Thank you for reaching out. I've received your message and will personally
          get back to you shortly.
          <br/><br/>
          <span style="color:#64748B;font-size:13px;">— A copy of your message:</span>
          <div style="margin-top:8px;padding:14px;background:#F1F5F9;border-radius:8px;color:#0A1E3F;font-size:14px;line-height:1.6;">
            {_safe_message(lead.get("message", ""))}
          </div>
          <br/>
          Warm regards,<br/>
          <strong style="color:#0A1E3F;">Nishant Jain</strong>
        </td></tr>
        <tr><td style="padding:16px 28px;background:#F8FAFC;color:#94A3B8;font-size:11px;">
          This is an automated confirmation. Investments are subject to market risks.
        </td></tr>
      </table>
    </div>
    """


def _send_sync(to, subject, html, reply_to=None):
    params = {"from": SENDER_EMAIL, "to": [to], "subject": subject, "html": html}
    if reply_to:
        params["reply_to"] = reply_to
    return resend.Emails.send(params)


def _enquiry_html(e):
    services = ", ".join(str(service) for service in e.get("services", [])) or "—"
    return f"""
    <div style="background:#050E1D;padding:32px;font-family:Arial,sans-serif;">
      <table style="max-width:560px;margin:auto;background:#ffffff;border-radius:12px;overflow:hidden;">
        <tr><td style="background:#0A1E3F;padding:24px 28px;">
          <div style="color:#F5A623;font-size:12px;letter-spacing:2px;text-transform:uppercase;">New Service Enquiry</div>
          <div style="color:#ffffff;font-size:22px;font-weight:700;margin-top:6px;">Nishant Jain — Equity Research</div>
        </td></tr>
        <tr><td style="padding:24px 16px;">
          <table style="width:100%;border-collapse:collapse;">
            {_row("Full Name", e.get("name"))}
            {_row("Email Address", e.get("email"))}
            {_row("Mobile Number", e.get("phone"))}
            {_row("Service(s)", services)}
            {_row("Received", _fmt_ts(e.get("created_at")))}
            {_row("Source", "Services Page")}
          </table>
          <div style="margin:18px 12px 0;color:#64748B;font-size:13px;">Message</div>
          <div style="margin:6px 12px;padding:14px;background:#F1F5F9;border-radius:8px;color:#0A1E3F;font-size:14px;line-height:1.6;">
            {_safe_message(e.get("message", ""))}
          </div>
        </td></tr>
        <tr><td style="padding:16px 28px;background:#F8FAFC;color:#94A3B8;font-size:12px;">
          Reply directly to {_safe_text(e.get("email"))} to respond to this enquiry.
        </td></tr>
      </table>
    </div>
    """


async def send_service_enquiry_email(enquiry: dict) -> str:
    """Send a service-enquiry notification to the owner. Raises on failure."""
    if not is_configured():
        raise EmailNotConfigured(
            "Email provider not configured (missing RESEND_API_KEY or CONTACT_RECIPIENT_EMAIL)."
        )
    result = await asyncio.to_thread(
        _send_sync,
        CONTACT_RECIPIENT_EMAIL,
        f"New Service Enquiry — {enquiry.get('name', '')}",
        _enquiry_html(enquiry),
        enquiry.get("email"),
    )
    email_id = result.get("id") if isinstance(result, dict) else None
    logger.info("Service enquiry email sent to %s (id=%s)", CONTACT_RECIPIENT_EMAIL, email_id)
    return email_id or ""


async def send_lead_emails(lead: dict, auto_reply: bool = True) -> str:
    """Send the owner alert (critical) synchronously and the visitor auto-reply
    (best-effort). Returns the provider message id. Raises on failure so the API
    can surface a real error instead of a fake success.
    """
    if not is_configured():
        raise EmailNotConfigured(
            "Email provider not configured (missing RESEND_API_KEY or CONTACT_RECIPIENT_EMAIL)."
        )

    # Owner alert — this MUST succeed for the submission to count as delivered.
    result = await asyncio.to_thread(
        _send_sync,
        CONTACT_RECIPIENT_EMAIL,
        f"New contact message — {lead.get('subject') or lead.get('name', '')}",
        _alert_html(lead),
        lead.get("email"),
    )
    email_id = result.get("id") if isinstance(result, dict) else None
    logger.info("Contact alert email sent to %s (id=%s)", CONTACT_RECIPIENT_EMAIL, email_id)

    # Visitor auto-reply — best-effort, never blocks success.
    if auto_reply and lead.get("email"):
        try:
            await asyncio.to_thread(
                _send_sync,
                lead["email"],
                "We've received your message — Nishant Jain",
                _reply_html(lead),
            )
            logger.info("Auto-reply sent to %s", lead["email"])
        except Exception as e:
            logger.error("Auto-reply failed (non-blocking): %s", e)

    return email_id or ""
