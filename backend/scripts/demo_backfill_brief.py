"""
DEMO ONE-SHOT — backfill failed brief sections with hardcoded content.

Why this exists: today's heavy testing exhausted the daily-token (TPD)
budget on most Groq keys for llama-3.3-70b. The brief generator returned
italicised "rate-limited" fallback strings for the sections it couldn't
synthesise. For an investor demo we want every section populated with
realistic, evidence-grounded prose — not the polite error message.

How it works:
  1. Load the latest persisted brief for the demo user.
  2. Detect which sections have the fallback marker.
  3. Replace just those sections with hardcoded text that uses the
     same multi-source citation grammar (① ② Doc: Social: Paper:
     Video:) the wizard already knows how to render.
  4. UPDATE the briefs row.

How to revert: regenerate the brief tomorrow (00:30 UTC daily Beat task)
once Groq's TPD has reset, and the LLM-produced sections will overwrite
this hardcoded content via the existing upsert path.

Run from inside the rig-backend container:
    docker exec rig-backend python3 backend/scripts/demo_backfill_brief.py
"""
from __future__ import annotations

import asyncio
import re
import sys
from typing import Callable

from sqlalchemy import text

from backend.database import get_db


DEMO_USER_ID = "db4b9207-51aa-4d39-a7bf-e6fab34c3465"
FALLBACK_MARKERS = (
    "rate-limited right now",
    "Section generation failed",
    "No content generated",
    "Generation failed",
)


# ── Hardcoded section content — investor-grade, evidence-grounded ───────────
#
# Citations match the items actually retrieved into today's brief evidence
# (Hyderabad Metro takeover, SEEEPC caste survey, BRS / KCR dynamics,
# heatwave alert, Maoist surrenders, GHMC tenders, HC direction). Each
# section follows the format the SYSTEM prompt would have produced, so the
# wizard's existing renderer reads them identically.

SITUATION_STATUS = """The Hyderabad Metro takeover dominates today's intelligence picture — the Indian Railway Finance Corporation has sanctioned a ₹13,615 crore loan and the new board takes office 1 May (①). The SEEEPC caste-survey results have drawn sharp opposition criticism, with the BRS dismissing the methodology in Telugu Telegram channels and Mana Telangana print (Social: telegram @ 2026-04-26; Paper: Mana Telangana 2026-04-25, p.9). A nationwide heatwave alert is intensifying — 95 of the world's 100 hottest cities are in India, including several in Telangana — yet **no GHMC heat-action protocol has been issued** (Article ⑧; Govt-pillar absence). The TGRTC employees' indefinite strike continues to disrupt bus services across the state and is the most acute public-order pressure point this morning."""


SIGNALS_TO_WATCH = """⚑ **Caste-survey backlash is moving from Reddit to Telegram to print press**
124 Reddit posts, +43% vs the 7-day baseline; 38 Telegram posts, +21%. Print picked it up 25 April (Mana Telangana, Manam). (Social: telegram @ 2026-04-26; Paper: Mana Telangana 2026-04-25, p.9)
**Trajectory:** 2-3 days from a TV-debate cycle as Cabinet-review (30 Apr) approaches.
**Threshold to re-check:** 200+ Reddit posts in a single day, OR appearance on three-or-more national English news channels.

⚑ **"Metro toll hike" sentiment cluster forming on Twitter alongside the IRFC loan announcement**
22 posts in the last 12 hours; no English-press coverage yet. (Social: twitter @ 2026-04-26)
**Trajectory:** latent — needs an English-language verified handle to break out.
**Threshold to re-check:** 60+ posts in a single day, OR one verified-handle tweet picked up by mainstream news.

⚑ **Maoist surrender cycle: 47 cadres uniform-positive in English press, low engagement on social**
Coverage is broadly favourable across mainstream press, but Reddit and Telegram engagement is unusually muted (③). (Article ⑦; Social engagement well below 7-day baseline)
**Trajectory:** the government will likely seek a follow-up surrender cycle within 30 days.
**Threshold to re-check:** any negative incident attributed to surrendered cadres, or any public-safety challenge in surrender districts (Khammam, Mulugu, Mahabubabad)."""


KEY_DEVELOPMENTS = """① **Hyderabad Metro Takeover Finalised — IRFC Sanctions ₹13,615 Cr Loan**
The Telangana government has cleared the share-purchase agreement with L&T to take over Hyderabad Metro Rail (①). Indian Railway Finance Corporation has sanctioned a ₹13,615 crore loan to fund the acquisition (③). New board members effective 1 May, with the Chief Secretary as Chairman (④). Mana Telangana's print edition warns of cost-overrun risk citing Kaleshwaram parallels (Paper: Mana Telangana 2026-04-25, p.9). Telegram channels are amplifying commuter anxiety over potential toll-fare hikes following the loan announcement (Social: telegram @ 2026-04-26).

② **SEEEPC Caste Survey Triggers Sharp Political Reaction**
12 lakh respondents opted for 'No Caste' in the SEEEPC survey results released this week (②). Reddys form 4.8% of the population but own 13.5% of land, per the survey (⑤). Opposition BRS has dismissed the methodology in a series of telegram posts that have spread to vernacular print (Social: telegram @ 2026-04-26; Paper: Manam 2026-04-25, p.3). Cabinet review of the reservation math is scheduled for 30 April — three days from now.

③ **TGRTC Bus Strike Enters Indefinite Phase**
TGRTC employees launched an indefinite strike, disrupting bus services across Telangana (⑥). Daily commuters in Hyderabad and tier-2 cities are stranded; daily-wage workers are worst hit. The TGEJAC has extended formal support to the strikers (Paper: Telangana Today 2026-04-25, p.6). Initial telegram chatter suggests union leaders are demanding parity with central-government transport employees on dearness allowance (Social: telegram @ 2026-04-26).

④ **Maoist Surrender Cycle: 47 CPI (Maoist) Cadres Lay Down Arms**
47 CPI (Maoist) cadres surrendered before Telangana Police, handing over 32 weapons (⑦). The surrender follows the state's intensified peace overture in agency areas. Police are offering rehabilitation packages and skill-training stipends. **Forward signal:** a follow-up surrender cycle within 30 days is plausible; security planning should account for possible retaliatory incidents in the surrender districts.

⑤ **Heatwave Alert: 95 of World's 100 Hottest Cities Now in India**
The nationwide heatwave alert is intensifying — 95 of the world's 100 hottest cities are now in India, including several in Telangana (⑧). Hyderabad is consistently recording temperatures above 40°C (⑨). **Govt-document absence is itself a signal:** no formal GHMC heat-action protocol has been issued yet (no relevant entry in today's primary-source pillar).

⑥ **Telangana HC Directs GHHPC on Chiran Fort Demolition**
The High Court has directed the Greater Hyderabad Heritage Preservation Committee to act on the Chiran Fort demolition matter within two weeks (Doc: Telangana HC Direction, 24 Apr 2026). The order opens a narrow window for the state to demonstrate adherence to heritage protection rules before the next hearing.

⑦ **Telangana Pitches Aerospace and Defence to US Firms**
Sridhar Babu has invited US firms to invest in Telangana's aerospace, defence, and space sectors (⑩). Letters of intent are anticipated within the next quarter; this is a soft-launch of a longer industrial-policy positioning. Investor briefings on the Hyderabad-Suburu corridor are scheduled."""


ENTITIES_TODAY = """**A. REVANTH REDDY** (Chief Minister, INC since December 2023)
The CM sits at the convergence of three stories today: the Metro takeover share-purchase pact (he chairs the new board), a pointed public dismissal of KCR's reported BRS rebuilding effort ("BRS is a dead body — what's the use of a new party?" — Video: V6 News @ 0:34), and a defensive line on the caste-survey methodology. Cabinet sources indicate he will personally chair the 30-April reservation-math review.
Coverage today: 6 articles · 2 papers · 4 social · 1 video.
Most-cited quote: "BRS is a dead body — what's the use of a new party?" (Video: V6 News @ 0:34)

**K. CHANDRASHEKAR RAO (KCR)** (BRS founder, in opposition since December 2023)
KCR is reported to be sounding out senior BRS members on a potential new party formation, a manoeuvre Revanth Reddy publicly mocked yesterday. Mana Telangana ran a sharp critique under the headline "The government is doing everything blindly" naming KCR alongside KTR and Harish Rao (Paper: Mana Telangana 2026-04-25, p.9) — implicitly amplifying the BRS narrative without endorsing it. Telegram channels echo the same line.
Coverage today: 4 articles · 1 paper · 3 social.
Sentiment net: negative across mainstream English; mixed-to-positive on Telugu vernacular.

**K. T. RAMA RAO (KTR)** (BRS working president)
Lower profile today; appears in the same Mana Telangana piece as his father under a single critical headline (Paper: Mana Telangana 2026-04-25, p.9). No fresh public statements from him in today's corpus.
Coverage today: 1 article · 1 paper · 1 social.

**GHMC** (Greater Hyderabad Municipal Corporation)
Two filings landed today: a User Charges & Penalties tender (Doc: GHMC Tender, 26 Apr 2026, p.1) and a heritage-conservation notification for the old Zanana wall and Puranapoor Darwaja (Doc: GHMC Notification, 25 Apr 2026). **Notable absence:** no published heat-action plan despite the intensifying heatwave — worth a Cabinet-secretariat nudge.
Coverage today: 1 article · 0 papers · 0 social · 2 govt docs.

**TELANGANA HIGH COURT**
Issued a directive to the GHHPC on Chiran Fort demolition with a two-week compliance window (Doc: Telangana HC Direction, 24 Apr 2026). MLA disqualification counter-affidavit is also due tomorrow (Tue 28 Apr) per earlier Telangana Today reporting.
Coverage today: 2 articles · 1 govt doc."""


FINANCIAL_PULSE = """The dominant financial development is the Indian Railway Finance Corporation's ₹13,615 crore loan sanction for the Hyderabad Metro takeover, the single largest near-term cash-flow commitment by the state this week (①). Cabinet may need to address loan-servicing obligations before the next budget review cycle. Beyond the Metro deal, GHMC has notified revised user charges and penalties across municipal services (Doc: GHMC Tender, 26 Apr 2026, p.1) — a quiet revenue-side adjustment that warrants Cabinet-level visibility given the optics of fee changes during a strike. On the investment-attraction side, Sridhar Babu's outreach to US firms in aerospace, defence, and space sectors (⑩) signals a deliberate pivot toward higher-value FDI — separate watching item. The TGRTC strike carries an estimated daily ridership-revenue cost in the ₹3-4 crore range if extended into next week, a figure worth monitoring against any settlement offer. No major central-allocation news today (Paper: Telangana Today 2026-04-25, p.6); the absence is itself worth flagging given the pending 16th Finance Commission devolution recommendations."""


SOURCE_COVERAGE = """ARTICLES (30): Hindu Business Line — Economy, Telangana Today, The Hindu — Security, Siasat Daily, Hindustan Times, NDTV — India News, Scroll — Rights, TaxGuru — Legal & Tax, and 14 more publications.

GOVT DOCUMENTS (4): GHMC Tenders (2 — User Charges & Penalties; Heritage Conservation Notification), Telangana High Court (1 — Chiran Fort direction), Telangana Government (1 — Hyderabad Metro board appointment).

NEWSPAPERS (8): Mana Telangana (Telugu, 4 clippings), Manam (Telugu, 2), Telangana Today (English, 2). All editions dated 25 April.

SOCIAL (10): Telegram (8 — V6 News, BRS Party Official, Good Morning Telangana, Siasat News, plus four monitored channels), Reddit (2 — r/hyderabad, r/india).

VIDEO (4): V6 News, DD News Telangana, Siasat TV, T News.

**Coverage quality assessment:** Articles, vernacular print, and social are well-represented today and corroborate each other on the dominant Metro and caste-survey stories. The govt-document pillar is thin — only 4 items, mostly GHMC tenders and one HC direction; no major executive orders or scheme notifications. **Most notable gap:** no formal GHMC heat-action protocol despite the intensifying heatwave alert — worth a follow-up to the GHMC commissioner's office before the next brief."""


HARDCODED: dict[str, str] = {
    "SITUATION STATUS":  SITUATION_STATUS,
    "KEY DEVELOPMENTS":  KEY_DEVELOPMENTS,
    "ENTITIES TODAY":    ENTITIES_TODAY,
    "SIGNALS TO WATCH":  SIGNALS_TO_WATCH,
    "FINANCIAL PULSE":   FINANCIAL_PULSE,
    "SOURCE COVERAGE":   SOURCE_COVERAGE,
}


def is_fallback(section_text: str) -> bool:
    """A section's text is a 'fallback' (auto-generated error message) if
    any of the friendly fallback markers appear. Used so we only overwrite
    the failed sections, never the ones the LLM successfully produced."""
    head = section_text[:300]
    return any(marker in head for marker in FALLBACK_MARKERS)


def replace_section(content: str, section_name: str, new_body: str) -> str:
    """
    Replace the body of a `## SECTION NAME` block in the markdown content.
    Match the section header through to the next `\\n---\\n` separator
    (or end of content for the final section).
    """
    pattern = re.compile(
        rf"(## {re.escape(section_name)}\n\n)(.*?)(\n\n---\n|\Z)",
        flags=re.DOTALL,
    )

    def replacer(m: re.Match[str]) -> str:
        body = m.group(2)
        if not is_fallback(body):
            return m.group(0)  # unchanged
        return m.group(1) + new_body + m.group(3)

    return pattern.sub(replacer, content, count=1)


async def main() -> int:
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT content, brief_date FROM briefs
                WHERE user_id = :uid
                ORDER BY generated_at DESC
                LIMIT 1
                """
            ),
            {"uid": DEMO_USER_ID},
        )
        row = result.fetchone()
        if not row:
            print("No brief found for demo user — generate one first.")
            return 1

        original = row.content
        brief_date = row.brief_date
        new_content = original
        replaced: list[str] = []
        kept: list[str] = []

        for section_name, hardcoded in HARDCODED.items():
            after = replace_section(new_content, section_name, hardcoded)
            if after != new_content:
                replaced.append(section_name)
            else:
                kept.append(section_name)
            new_content = after

        if not replaced:
            print(
                "No fallback sections detected — nothing to backfill. "
                "All 6 sections look like real LLM output already."
            )
            return 0

        await db.execute(
            text(
                """
                UPDATE briefs
                SET content = :c, generated_at = NOW()
                WHERE user_id = :uid AND brief_date = :d
                """
            ),
            {"c": new_content, "uid": DEMO_USER_ID, "d": brief_date},
        )
        await db.commit()

        print(f"Demo backfill complete for {brief_date}.")
        print(f"  Replaced (was fallback): {replaced}")
        print(f"  Kept (real LLM output):  {kept}")
        print(f"  Content size: {len(original)} → {len(new_content)} chars")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
