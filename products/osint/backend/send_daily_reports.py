"""Daily job: build + render + email the State Intelligence Brief to every persona
with an email on file. Invoked by cron (see /etc/cron.d/rig-osint-daily-report).

Runs in the morning (IST) so the LLM daily token quota has reset, giving the rich
narrative rather than templates. Failures are isolated per-recipient.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

import report_builder
import report_email
import report_render
from brief_prefs import load_prefs
from db import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("daily_report")


async def main() -> None:
    async with get_db() as db:
        rows = (await db.execute(text(
            "SELECT p.user_id, u.email FROM analytics.user_brief_prefs p "
            "JOIN analytics.users u ON u.id = p.user_id "
            "WHERE u.email IS NOT NULL AND u.email <> ''"
        ))).fetchall()
    log.info("daily report: %d recipients", len(rows))
    sent = 0
    for r in rows:
        try:
            async with get_db() as db:
                prefs = await load_prefs(db, r.user_id)
                if not prefs:
                    continue
                rep = await report_builder.build_report(db, prefs)
            pdf = report_render.render_pdf(rep)
            subject = f"RIG OSINT · {rep['state']} Daily Brief · {str(rep['generated_at'])[:10]}"
            body = (f"<p>Your daily <b>{rep['state']}</b> intelligence brief is attached.</p>"
                    f"<p>{rep['kpis']['n24']} stories tracked · net sentiment "
                    f"{rep['kpis']['net_sentiment']:+d}% · confidence {rep['confidence']}.</p>"
                    f"<p style='color:#888'>— RIG OSINT Desk</p>")
            if report_email.send_report_email(r.email, subject, pdf,
                                              f"RIG-OSINT-{rep['state_code']}-brief.pdf", body):
                sent += 1
        except Exception as exc:  # noqa: BLE001 — isolate per recipient
            log.warning("daily report failed for %s: %s", r.user_id, exc)
    log.info("daily report: sent %d/%d", sent, len(rows))


if __name__ == "__main__":
    asyncio.run(main())
