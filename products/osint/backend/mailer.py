"""Gmail SMTP sender — reads credentials from the environment ONLY (never
hardcoded). Sending is a deliberate action; callers default to dry-run.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


class MailNotConfigured(RuntimeError):
    """Raised when GMAIL_ADDRESS / GMAIL_APP_PASSWORD are not set in env."""


def _creds() -> tuple[str, str]:
    addr = os.environ.get("GMAIL_ADDRESS")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not addr or not pw:
        raise MailNotConfigured("GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set in the osint-backend env")
    return addr, pw


def send_gmail(to_addr: str, subject: str, html: str, text: str) -> dict:
    """Send one multipart (text + HTML) email via Gmail SMTP. Blocking — call
    from a thread in async contexts."""
    addr, pw = _creds()
    msg = EmailMessage()
    msg["From"] = addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
        s.starttls()
        s.login(addr, pw)
        s.send_message(msg)
    return {"sent": True, "to": to_addr, "from": addr}
