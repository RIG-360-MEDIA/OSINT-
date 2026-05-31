"""Generic delivery & export render engine (Category-4).

Turns a user's brief data into deliverable artifacts — HTML newsletter, print
1-pager, CSV (Sheets-importable), and channel-composed text (email/Slack/
WhatsApp). Pure function of prefs + corpus (via the posture engine), so it is
per-recipient personalised by construction. LLM-free: renders the posture data
deterministically; textual prose is optional (passed in) to keep exports cheap.

Actual *delivery* (SMTP / Gmail API / Sheets API / WhatsApp) is credential- and
permission-gated and lives in thin connectors that the operator wires with their
own secrets — never sent automatically from here.
"""
from __future__ import annotations

import csv
import html
import io
from typing import Any

from posture import compute_posture

CHANNELS = ("email", "slack", "whatsapp")


async def gather_brief(db, prefs: dict[str, Any], window_hours: int = 504,
                       textual: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assemble the renderable brief from the (LLM-free) posture engine + optional prose."""
    p = await compute_posture(db, prefs, window_hours)
    if not p.get("personalized"):
        return {"personalized": False, "subject": None, "sections": {}}
    m = p["metrics"]
    fav = m["outlet_favourability"]["items"]
    ffc = m["friend_foe_fence"]
    heat = m["target_heat"]["items"]
    iss = m["issue_ownership"]["items"]
    clg = m["cross_language_gap"]
    return {
        "personalized": True,
        "subject": p["subject"],
        "window_hours": p["window_hours"],
        "sections": {
            "pressure": m["weighted_pressure"],
            "share_of_voice": m["share_of_voice"].get("principal_sov_pct"),
            "hostile_outlets": ffc["hostile"][:5],
            "ally_outlets": ffc["ally"][:5],
            "fav_low": fav[:3], "fav_high": fav[-3:],
            "target_heat": heat[:6],
            "issue_ownership": iss[:6],
            "cross_language_gap": clg,
            "narrative_half_life": m["narrative_half_life"],
            "trajectory": m["stance_trajectory"],
        },
        "prose": textual or {},
    }


def _bluf(brief: dict[str, Any]) -> str:
    p = brief.get("prose", {}) or {}
    t = (p.get("executive_bluf") or {}).get("text") or (p.get("situation_room") or {}).get("text")
    return t or ""


def one_pager_text(brief: dict[str, Any]) -> str:
    """Print-ready minister 'red folder' 1-pager (plain text)."""
    if not brief.get("personalized"):
        return "No principal configured — nothing to brief."
    s = brief["sections"]
    L = [f"SITUATION BRIEF — {brief['subject']}", "=" * 56]
    bluf = _bluf(brief)
    if bluf:
        L += ["", bluf]
    L += ["", f"Pressure on you: {s['pressure']['pressure']} ({s['pressure']['negative_signals']} hostile signals)",
          f"Your share of voice: {s['share_of_voice']}%",
          f"Coverage trend: {s['trajectory'].get('direction')} ({s['trajectory'].get('slope_per_day')}/day)"]
    if s["hostile_outlets"]:
        L += ["", "MOST HOSTILE OUTLETS:"] + [f"  - {o['outlet']} ({o['favourability']:+})" for o in s["hostile_outlets"]]
    if s["target_heat"]:
        L += ["", "OPPOSITION UNDER FIRE:"] + [f"  - {t['name']}: heat {t['heat']}" for t in s["target_heat"][:5]]
    if s["issue_ownership"]:
        L += ["", "ISSUES:"] + [f"  - {i['topic']}: {i['verdict']} ({i['favourability']:+})" for i in s["issue_ownership"][:5]]
    g = s["cross_language_gap"].get("gap")
    if g is not None:
        L += ["", f"Cross-language gap: {g} pts (regional vs English coverage)"]
    L += ["", "— RIG OSINT"]
    return "\n".join(L)


def newsletter_html(brief: dict[str, Any]) -> str:
    """Responsive HTML email body — per-recipient by construction."""
    if not brief.get("personalized"):
        return "<p>No principal configured.</p>"
    e = html.escape
    s = brief["sections"]
    bluf = _bluf(brief)
    rows = "".join(f"<tr><td>{e(o['outlet'])}</td><td style='color:#c0392b'>{o['favourability']:+}</td></tr>"
                   for o in s["hostile_outlets"])
    heat = "".join(f"<li>{e(t['name'])} — heat {t['heat']}</li>" for t in s["target_heat"][:5])
    return f"""<div style="font-family:Georgia,serif;max-width:640px;margin:auto;color:#1a1a1a">
<h1 style="border-bottom:2px solid #000;padding-bottom:6px">Situation Brief — {e(brief['subject'])}</h1>
{f'<p style="font-size:16px">{e(bluf)}</p>' if bluf else ''}
<p><b>Pressure on you:</b> {s['pressure']['pressure']} · <b>Share of voice:</b> {s['share_of_voice']}% ·
<b>Trend:</b> {e(str(s['trajectory'].get('direction')))}</p>
<h3>Most hostile outlets</h3><table style="width:100%;border-collapse:collapse">{rows or '<tr><td>—</td></tr>'}</table>
<h3>Opposition under fire</h3><ul>{heat or '<li>—</li>'}</ul>
<p style="color:#888;font-size:12px">RIG OSINT · window {brief['window_hours']}h</p></div>"""


def export_csv(brief: dict[str, Any]) -> str:
    """Sheets-importable CSV of the key posture tables."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "label", "value"])
    if brief.get("personalized"):
        s = brief["sections"]
        for o in s["fav_low"] + s["fav_high"]:
            w.writerow(["outlet_favourability", o["outlet"], o["favourability"]])
        for t in s["target_heat"]:
            w.writerow(["target_heat", t["name"], t["heat"]])
        for i in s["issue_ownership"]:
            w.writerow(["issue_ownership", i["topic"], i["favourability"]])
    return buf.getvalue()


def compose(brief: dict[str, Any], channel: str) -> str:
    """Multi-channel single-compose: same brief, channel-appropriate formatting."""
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")
    if not brief.get("personalized"):
        return "No principal configured."
    s = brief["sections"]
    bluf = _bluf(brief)
    foes = ", ".join(o["outlet"] for o in s["hostile_outlets"][:3]) or "—"
    if channel == "slack":
        return (f":newspaper: *Situation Brief — {brief['subject']}*\n"
                f"{bluf}\n• Pressure: {s['pressure']['pressure']} • SoV: {s['share_of_voice']}%\n"
                f"• Hostile: {foes}")
    if channel == "whatsapp":
        return (f"*Brief — {brief['subject']}*\n{bluf}\nPressure {s['pressure']['pressure']} · "
                f"SoV {s['share_of_voice']}%\nHostile: {foes}")
    return (f"Situation Brief — {brief['subject']}\n\n{bluf}\n\nPressure: {s['pressure']['pressure']}, "
            f"share of voice {s['share_of_voice']}%. Most hostile outlets: {foes}.")
