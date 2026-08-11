"""Inline-SVG analytics charts for the weekly report ("The Week in Charts").

Pure server-side SVG — no JS, no external assets — so the charts render
identically in the HTML endpoint and the headless-Chromium PDF. Sentiment
polarity is ALWAYS encoded by position (above/below a zero baseline, or
left/right of a centre axis) with signed labels; the brand green/red pair fails
deuteranopia separation (dE 4.8) so colour is never the only channel.

Colour jobs: navy = magnitude (single sequential hue); green/red = polarity
only; text wears text tokens, never series colours.
"""
from __future__ import annotations

from typing import Any

PRO = "#1f7a46"
ANTI = "#b02a24"
NAVY = "#2b5288"
NAVY_LIGHT = "#9db4d4"
INK = "#14181d"
MUTED = "#4f5a64"
FAINT = "#8a94a0"
HAIR = "#e2e6ea"

F = "font-family:'Inter','Segoe UI',Arial,sans-serif"


def _e(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _txt(x, y, s, size=10, fill=MUTED, anchor="middle", weight=400) -> str:
    return (f"<text x='{x:.1f}' y='{y:.1f}' text-anchor='{anchor}' "
            f"style=\"{F};font-size:{size}px;font-weight:{weight};fill:{fill}\">{_e(s)}</text>")


def _vbar(x, w, y_base, h, color, up=True) -> str:
    """Column with a 4px-rounded data end and a square baseline end."""
    r = min(4.0, w / 2, abs(h))
    if h <= 0:
        return ""
    if up:
        y = y_base - h
        return (f"<path d='M{x:.1f},{y_base:.1f} v{-(h - r):.1f} q0,{-r:.1f} {r:.1f},{-r:.1f} "
                f"h{w - 2 * r:.1f} q{r:.1f},0 {r:.1f},{r:.1f} v{h - r:.1f} z' fill='{color}'/>")
    return (f"<path d='M{x:.1f},{y_base:.1f} v{h - r:.1f} q0,{r:.1f} {r:.1f},{r:.1f} "
            f"h{w - 2 * r:.1f} q{r:.1f},0 {r:.1f},{-r:.1f} v{-(h - r):.1f} z' fill='{color}'/>")


def _hbar(x_base, y, h, w, color, right=True) -> str:
    """Horizontal bar with a 4px-rounded data end, square at the axis."""
    r = min(4.0, h / 2, abs(w))
    if w <= 0:
        return ""
    if right:
        return (f"<path d='M{x_base:.1f},{y:.1f} h{w - r:.1f} q{r:.1f},0 {r:.1f},{r:.1f} "
                f"v{h - 2 * r:.1f} q0,{r:.1f} {-r:.1f},{r:.1f} h{-(w - r):.1f} z' fill='{color}'/>")
    return (f"<path d='M{x_base:.1f},{y:.1f} h{-(w - r):.1f} q{-r:.1f},0 {-r:.1f},{r:.1f} "
            f"v{h - 2 * r:.1f} q0,{r:.1f} {r:.1f},{r:.1f} h{w - r:.1f} z' fill='{color}'/>")


def _day_lab(iso: str) -> str:
    import datetime
    d = datetime.date.fromisoformat(iso)
    return d.strftime("%a %d").upper()


# ── A. daily tone flow: diverging columns, favourable up / critical down ──────
def chart_daily_flow(daily: list[dict]) -> str:
    if not daily:
        return ""
    W, H = 700, 210
    top, bot, lx = 26, 34, 44
    plot_w = W - lx - 8
    mx = max(max(d["favourable"] for d in daily), max(d["critical"] for d in daily)) or 1
    mx = ((mx // 25) + 1) * 25  # clean axis max
    zero_y = top + (H - top - bot) / 2.0
    half = (H - top - bot) / 2.0
    band = plot_w / len(daily)
    bw = min(24.0, band * 0.42)
    o = [f"<svg viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg' role='img' "
         f"aria-label='Daily favourable and critical story counts'>"]
    for frac in (1.0, 0.5):
        v = int(mx * frac)
        for sign in (1, -1):
            y = zero_y - sign * half * frac
            o.append(f"<line x1='{lx}' y1='{y:.1f}' x2='{W - 8}' y2='{y:.1f}' stroke='{HAIR}' stroke-width='1'/>")
            o.append(_txt(lx - 6, y + 3.5, v, 9, FAINT, "end"))
    o.append(f"<line x1='{lx}' y1='{zero_y:.1f}' x2='{W - 8}' y2='{zero_y:.1f}' stroke='{FAINT}' stroke-width='1'/>")
    o.append(_txt(lx - 6, zero_y + 3.5, 0, 9, FAINT, "end"))
    for i, d in enumerate(daily):
        cx = lx + band * i + band / 2.0
        fh = half * d["favourable"] / mx
        ch = half * d["critical"] / mx
        o.append(_vbar(cx - bw - 1, bw, zero_y, fh, PRO, up=True))
        o.append(_vbar(cx + 1, bw, zero_y, ch, ANTI, up=False))
        if fh > 0:
            o.append(_txt(cx - bw / 2 - 1, zero_y - fh - 4, d["favourable"], 9, MUTED))
        if ch > 0:
            o.append(_txt(cx + bw / 2 + 1, zero_y + ch + 11, d["critical"], 9, MUTED))
        o.append(_txt(cx, H - 18, _day_lab(d["date"]), 9, MUTED, weight=600))
        net = d.get("net", 0)
        o.append(_txt(cx, H - 5, f"net {net:+d}", 9, INK, weight=600))
    o.append("</svg>")
    return "".join(o)


# ── B. sentiment split: diverging stacked bar centred on neutral ──────────────
def chart_sentiment_split(sent: dict) -> str:
    fav, neu, crit = sent["favourable"], sent["neutral"], sent["critical"]
    tot = (fav + neu + crit) or 1
    W, H, bh = 700, 64, 22
    y = 14
    cx = W / 2.0
    scale = (W - 40) / tot
    nw = neu * scale
    fw = fav * scale
    cw = crit * scale
    nx = cx - nw / 2.0
    o = [f"<svg viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg' role='img' "
         f"aria-label='Week sentiment split'>"]
    o.append(_hbar(nx - 2, y, bh, fw, PRO, right=False))
    o.append(f"<rect x='{nx:.1f}' y='{y}' width='{nw:.1f}' height='{bh}' fill='{HAIR}'/>")
    o.append(_hbar(nx + nw + 2, y, bh, cw, ANTI, right=True))
    o.append(_txt(nx - fw / 2 - 2, y + bh + 16, f"Favourable {fav} · {round(100 * fav / tot)}%", 10, MUTED, weight=600))
    o.append(_txt(cx, y + bh + 16, f"Neutral {neu} · {round(100 * neu / tot)}%", 10, FAINT))
    o.append(_txt(nx + nw + cw / 2 + 2, y + bh + 16, f"Critical {crit} · {round(100 * crit / tot)}%", 10, MUTED, weight=600))
    o.append("</svg>")
    return "".join(o)


# ── C. topics: volume (navy) + net tone (diverging), shared axis ─────────────
def chart_topics(topics: list[dict]) -> str:
    rows = [t for t in topics if t["items"] > 0][:11]
    if not rows:
        return ""
    rh = 26
    W = 700
    H = 26 + rh * len(rows)
    lab_w, vol_w, gap = 148, 250, 24
    net_x0 = lab_w + vol_w + gap
    net_w = W - net_x0 - 8
    net_c = net_x0 + net_w / 2.0
    vmax = max(t["items"] for t in rows)
    o = [f"<svg viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg' role='img' "
         f"aria-label='Coverage volume and net tone by topic'>"]
    o.append(_txt(lab_w + 2, 12, "Stories this week", 9, FAINT, "start", 600))
    o.append(_txt(net_c, 12, "Net tone  (critical ← 0 → favourable)", 9, FAINT, "middle", 600))
    o.append(f"<line x1='{net_c:.1f}' y1='18' x2='{net_c:.1f}' y2='{H - 6}' stroke='{HAIR}' stroke-width='1'/>")
    for i, t in enumerate(rows):
        y = 20 + rh * i
        bh = 14
        o.append(_txt(lab_w - 6, y + bh - 2, t["topic"], 10, INK, "end", 600))
        w = vol_w * t["items"] / vmax
        o.append(_hbar(lab_w, y, bh, w, NAVY, right=True))
        o.append(_txt(lab_w + w + 5, y + bh - 2, t["items"], 9, MUTED, "start"))
        net = t["net"]
        nw = abs(net) / 100.0 * (net_w / 2.0 - 30)
        if net >= 0:
            o.append(_hbar(net_c + 1, y + 2, 10, nw, PRO, right=True))
            o.append(_txt(net_c + 1 + nw + 5, y + bh - 3, f"{net:+d}", 9, MUTED, "start", 600))
        else:
            o.append(_hbar(net_c - 1, y + 2, 10, nw, ANTI, right=False))
            o.append(_txt(net_c - 1 - nw - 5, y + bh - 3, f"{net:+d}", 9, MUTED, "end", 600))
    o.append("</svg>")
    return "".join(o)


# ── D. media compare: net tone by pillar, volume labelled ────────────────────
def chart_media(media: list[dict]) -> str:
    if not media:
        return ""
    labs = {"web": "Web", "tv": "Television", "newspaper": "Newspapers"}
    order = [m for p in ("newspaper", "tv", "web") for m in media if m["pillar"] == p]
    rh, W = 34, 340
    H = 24 + rh * len(order)
    lab_w = 92
    net_w = W - lab_w - 12
    net_c = lab_w + net_w / 2.0
    o = [f"<svg viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg' role='img' "
         f"aria-label='Net tone by medium'>"]
    o.append(_txt(net_c, 12, "Net tone by medium", 9, FAINT, "middle", 600))
    o.append(f"<line x1='{net_c:.1f}' y1='16' x2='{net_c:.1f}' y2='{H - 4}' stroke='{HAIR}' stroke-width='1'/>")
    for i, m in enumerate(order):
        y = 22 + rh * i
        o.append(_txt(lab_w - 6, y + 12, labs.get(m["pillar"], m["pillar"]), 10, INK, "end", 600))
        net = m["net"]
        nw = abs(net) / 100.0 * (net_w / 2.0 - 26)
        if net >= 0:
            o.append(_hbar(net_c + 1, y, 12, nw, PRO, right=True))
            o.append(_txt(net_c + 1 + nw + 5, y + 10, f"{net:+d}", 9, INK, "start", 600))
        else:
            o.append(_hbar(net_c - 1, y, 12, nw, ANTI, right=False))
            o.append(_txt(net_c - 1 - nw - 5, y + 10, f"{net:+d}", 9, INK, "end", 600))
        o.append(_txt(lab_w - 6, y + 24, f"{m['favourable']}f / {m['critical']}c", 8.5, FAINT, "end"))
    o.append("</svg>")
    return "".join(o)


# ── E. movers dumbbell: last week → this week net tone, one hue two shades ───
def chart_movers(movers: list[dict]) -> str:
    if not movers:
        return ""
    rh, W = 34, 340
    H = 30 + rh * len(movers)
    lab_w = 118
    ax0, ax1 = lab_w, W - 34
    span = ax1 - ax0

    def x_of(v):
        return ax0 + (v + 100) / 200.0 * span

    o = [f"<svg viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg' role='img' "
         f"aria-label='Biggest week-over-week tone swings'>"]
    o.append(_txt((ax0 + ax1) / 2, 12, "Net tone: last week ○ → this week ●", 9, FAINT, "middle", 600))
    zx = x_of(0)
    o.append(f"<line x1='{zx:.1f}' y1='18' x2='{zx:.1f}' y2='{H - 6}' stroke='{HAIR}' stroke-width='1'/>")
    for i, m in enumerate(movers):
        y = 30 + rh * i
        o.append(_txt(lab_w - 8, y + 4, m["topic"], 10, INK, "end", 600))
        x0, x1 = x_of(m["prev_net"]), x_of(m["net"])
        o.append(f"<line x1='{x0:.1f}' y1='{y:.1f}' x2='{x1:.1f}' y2='{y:.1f}' "
                 f"stroke='{NAVY_LIGHT}' stroke-width='2' stroke-linecap='round'/>")
        o.append(f"<circle cx='{x0:.1f}' cy='{y:.1f}' r='4' fill='{NAVY_LIGHT}' stroke='#fff' stroke-width='2'/>")
        o.append(f"<circle cx='{x1:.1f}' cy='{y:.1f}' r='4.5' fill='{NAVY}' stroke='#fff' stroke-width='2'/>")
        lab_x = max(x0, x1) + 9
        o.append(_txt(lab_x, y + 3.5, f"{m['swing']:+d}", 9, INK, "start", 600))
    o.append("</svg>")
    return "".join(o)


# ── F. outlet lean: diverging net bars, volume labelled ──────────────────────
def chart_outlets(outlets: list[dict]) -> str:
    rows = sorted(outlets, key=lambda o2: o2["net"], reverse=True)[:12]
    if not rows:
        return ""
    labs = {"web": "WEB", "tv": "TV", "newspaper": "PRINT"}
    rh, W = 24, 700
    H = 26 + rh * len(rows)
    lab_w = 190
    net_w = W - lab_w - 10
    net_c = lab_w + net_w / 2.0
    o = [f"<svg viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg' role='img' "
         f"aria-label='Net tone by outlet'>"]
    o.append(_txt(net_c, 12, "Net tone by outlet  (critical ← 0 → favourable)", 9, FAINT, "middle", 600))
    o.append(f"<line x1='{net_c:.1f}' y1='16' x2='{net_c:.1f}' y2='{H - 4}' stroke='{HAIR}' stroke-width='1'/>")
    for i, ot in enumerate(rows):
        y = 22 + rh * i
        name = ot["outlet"] if len(ot["outlet"]) <= 24 else ot["outlet"][:23] + "…"
        o.append(_txt(lab_w - 8, y + 10, name, 9.5, INK, "end", 600))
        o.append(_txt(lab_w - 8, y + 19, f"{labs.get(ot['pillar'], '')} · {ot['on_govt']} stories", 8, FAINT, "end"))
        net = ot["net"]
        nw = abs(net) / 100.0 * (net_w / 2.0 - 28)
        if net >= 0:
            o.append(_hbar(net_c + 1, y + 2, 10, nw, PRO, right=True))
            o.append(_txt(net_c + 1 + nw + 5, y + 11, f"{net:+d}", 9, MUTED, "start", 600))
        else:
            o.append(_hbar(net_c - 1, y + 2, 10, nw, ANTI, right=False))
            o.append(_txt(net_c - 1 - nw - 5, y + 11, f"{net:+d}", 9, MUTED, "end", 600))
    o.append("</svg>")
    return "".join(o)


# ── G. TV share of voice: butterfly — opposition left (amber), government
# right (navy). Side is position-encoded (validated pair dE 18.9 CVD). ───────
OPP_AMBER = "#8a5a12"


def chart_tv_sov(sov: dict) -> str:
    rows = list(sov.get("channels", []))
    other = sov.get("other")
    if other and other.get("items"):
        rows.append({"channel": "Other news channels", "gov": other["gov"], "opp": other["opp"],
                     "items": other["items"]})
    if not rows:
        return ""
    rh, W = 24, 700
    H = 30 + rh * len(rows)
    lab_w = 170
    half = (W - lab_w - 20) / 2.0
    cx = lab_w + half
    vmax = max(max(r2["gov"] for r2 in rows), max(r2["opp"] for r2 in rows)) or 1
    o = [f"<svg viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg' role='img' "
         f"aria-label='Stories featuring opposition vs government figures, per channel'>"]
    o.append(_txt(cx - half / 2, 12, "Featuring OPPOSITION figures", 9, MUTED, "middle", 600))
    o.append(_txt(cx + half / 2, 12, "Featuring GOVERNMENT figures", 9, MUTED, "middle", 600))
    o.append(f"<line x1='{cx:.1f}' y1='18' x2='{cx:.1f}' y2='{H - 6}' stroke='{FAINT}' stroke-width='1'/>")
    for i, r2 in enumerate(rows):
        y = 24 + rh * i
        name = r2["channel"] if len(r2["channel"]) <= 22 else r2["channel"][:21] + "…"
        o.append(_txt(lab_w - 8, y + 11, name, 9.5, INK, "end", 600))
        gw = (half - 34) * r2["gov"] / vmax
        ow = (half - 34) * r2["opp"] / vmax
        if r2["opp"] > 0:
            o.append(_hbar(cx - 1, y + 2, 10, ow, OPP_AMBER, right=False))
            o.append(_txt(cx - 1 - ow - 5, y + 11, r2["opp"], 9, MUTED, "end", 600))
        if r2["gov"] > 0:
            o.append(_hbar(cx + 1, y + 2, 10, gw, NAVY, right=True))
            o.append(_txt(cx + 1 + gw + 5, y + 11, r2["gov"], 9, MUTED, "start", 600))
    o.append("</svg>")
    return "".join(o)


def build_week_charts(r: dict[str, Any]) -> dict[str, str]:
    """All analytics SVGs for the weekly report, keyed by chart id."""
    s = r["strip"]
    return {
        "daily_flow": chart_daily_flow(s.get("daily_totals", [])),
        "sentiment_split": chart_sentiment_split(s["sentiment"]),
        "topics": chart_topics(r.get("topics", [])),
        "media": chart_media(r.get("media_compare", [])),
        "movers": chart_movers(r.get("movers", [])),
        "outlets": chart_outlets(r.get("outlets", [])),
        "tv_sov": chart_tv_sov(r.get("tv_sov") or {}),
    }
