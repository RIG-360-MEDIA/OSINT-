"""Email a rendered report PDF via Gmail SMTP (GMAIL_ADDRESS / GMAIL_APP_PASSWORD)."""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("report_email")


def send_report_email(to_addr: str, subject: str, pdf_bytes: bytes, filename: str,
                      html_body: str | None = None) -> bool:
    sender = os.getenv("GMAIL_ADDRESS", "").strip()
    pw = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    if not sender or not pw:
        logger.warning("report_email: GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set")
        return False
    if not to_addr:
        logger.warning("report_email: no recipient")
        return False

    msg = EmailMessage()
    msg["From"] = f"RIG OSINT Desk <{sender}>"
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(html_body or "Your daily RIG OSINT intelligence brief is attached as a PDF.")
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)

    try:
        # Port 587 + STARTTLS — Hetzner blocks outbound SMTPS (465); 587 works.
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=25) as smtp:
            smtp.starttls()
            smtp.login(sender, pw)
            smtp.send_message(msg)
        logger.info("report_email: sent to %s (%d bytes)", to_addr, len(pdf_bytes))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("report_email: send failed (%s)", exc)
        return False
