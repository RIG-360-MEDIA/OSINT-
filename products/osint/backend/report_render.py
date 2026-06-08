"""Render a built report (report_builder.build_report) to HTML and PDF.

WeasyPrint has weak flexbox/grid support, so ALL multi-column layout here is
table-based (border-spacing for gaps) — that renders cleanly and aligns. Dark,
gold-accented intelligence-brief styling. Presentational only.
"""
from __future__ import annotations

import html
from typing import Any

_SEV = {
    "CRITICAL": ("crit", "CRITICAL"), "HIGH": ("high", "HIGH"),
    "MODERATE": ("mod", "MODERATE"), "LOW": ("low", "LOW"),
}
_TONE_COLOR = {"supportive": "#46c98a", "hostile": "#ef5d5d", "neutral": "#6b7691"}

_CSS = """
:root{--ink:#ece7da;--muted:#a59f8e;--faint:#7b7565;--line:#2a2833;--panel:#13121b;--panel2:#1a1924;
--gold:#d8b45a;--gold-d:#9c8136;--pos:#46c98a;--neu:#6b7691;--neg:#ef5d5d;--hi:#f0913e;
--serif:Georgia,'Times New Roman',serif;--mono:'DejaVu Sans Mono',monospace;}
*{box-sizing:border-box}
@page{size:A4;margin:15mm 14mm;background:#07060d;}
body{margin:0;background:#07060d;color:var(--ink);font-family:'Helvetica Neue',Arial,sans-serif;font-size:11px;line-height:1.6;}
.eyebrow{font-family:var(--mono);font-size:8px;letter-spacing:.22em;color:var(--gold);text-transform:uppercase;}
h1{font-family:var(--serif);font-weight:600;font-size:26px;line-height:1.1;margin:7px 0 4px;}
h2{font-family:var(--serif);font-weight:600;font-size:18px;margin:30px 0 4px;border-left:3px solid var(--gold);padding-left:12px;page-break-after:avoid;}
h2 .ix{font-family:var(--mono);font-size:10px;color:var(--gold-d);letter-spacing:.1em;margin-right:7px;}
h3{margin:0;}
.sub{color:var(--muted);font-size:10.5px;margin-bottom:4px;}
.lede{color:var(--muted);}
/* masthead */
table.mast{width:100%;border-collapse:collapse;border-bottom:2px solid var(--gold-d);padding-bottom:0;}
table.mast td{vertical-align:bottom;padding-bottom:12px;}
.stamp{font-family:var(--mono);font-size:8.5px;color:var(--faint);text-align:right;line-height:1.8;}
/* kpi strip */
table.kpis{width:100%;border-collapse:separate;border-spacing:10px 0;margin:18px -10px 4px;}
table.kpis td{width:25%;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:13px 15px;vertical-align:top;}
.kpi .v{font-size:20px;font-weight:600;font-family:var(--serif);line-height:1.1;}
.kpi .l{font-family:var(--mono);font-size:8px;letter-spacing:.1em;color:var(--faint);text-transform:uppercase;}
.kpi .d{font-size:9.5px;margin-top:3px;color:var(--muted);}
.up{color:var(--pos)}.down{color:var(--neg)}.flat{color:var(--neu)}
/* exec list */
ul.exec{list-style:none;padding:0;margin:8px 0 0;}
ul.exec li{position:relative;padding:8px 0 8px 22px;border-bottom:1px solid var(--line);}
ul.exec li:before{content:'>';position:absolute;left:3px;color:var(--gold);font-family:var(--mono);}
/* tables */
table.heat{width:100%;border-collapse:collapse;margin-top:8px;font-size:10.5px;}
table.heat th{font-family:var(--mono);font-size:8px;letter-spacing:.1em;color:var(--faint);text-transform:uppercase;text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);}
table.heat td{padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:top;}
.sev{display:inline-block;font-family:var(--mono);font-size:8.5px;font-weight:700;padding:3px 9px;border-radius:3px;}
.sev.crit{background:rgba(239,93,93,.18);color:#ff8585;}
.sev.high{background:rgba(240,145,62,.16);color:var(--hi);}
.sev.mod{background:rgba(216,180,90,.14);color:var(--gold);}
.sev.low{background:rgba(70,201,138,.13);color:var(--pos);}
/* developments */
.dev{border:1px solid var(--line);border-radius:8px;padding:15px 17px;margin:12px 0;background:var(--panel);page-break-inside:avoid;}
.dev .theme{font-family:var(--mono);font-size:8.5px;letter-spacing:.13em;color:var(--gold);text-transform:uppercase;}
.dev h3{font-family:var(--serif);font-size:15px;margin:5px 0 6px;font-weight:600;}
/* district bars */
table.bars{width:100%;border-collapse:collapse;}
table.bars td{padding:5px 0;vertical-align:middle;}
table.bars td.nm{width:150px;font-size:11px;}
table.bars td.vv{width:90px;text-align:right;font-family:var(--mono);font-size:10.5px;}
.track{height:8px;background:var(--panel2);border-radius:4px;overflow:hidden;}
.track i{display:block;height:100%;background:#c79b3e;}
/* sentiment bar */
table.senti{width:100%;border-collapse:collapse;height:14px;border-radius:6px;overflow:hidden;margin:8px 0 3px;}
table.senti td{height:14px;}
/* stories grid (2-col table) */
table.grid{width:100%;border-collapse:separate;border-spacing:14px;margin:8px -14px 0;}
table.grid td{width:50%;vertical-align:top;}
.card{border:1px solid var(--line);border-radius:9px;overflow:hidden;background:var(--panel);page-break-inside:avoid;}
.card .img{height:172px;background:#14131d;background-size:cover;background-position:center;border-bottom:1px solid var(--line);}
.card .ph{height:172px;background:linear-gradient(135deg,#1b1a26,#121119);border-bottom:1px solid var(--line);position:relative;}
.card .ph span{position:absolute;bottom:10px;left:12px;font-family:var(--mono);font-size:9px;color:var(--faint);letter-spacing:.12em;}
.card .bd{padding:12px 14px;min-height:66px;}
.card .ti{font-size:13px;font-weight:600;line-height:1.34;}
.card .en{font-size:11px;color:var(--muted);margin-top:5px;}
.card .mt{font-family:var(--mono);font-size:8.5px;color:var(--faint);margin-top:9px;}
.dot{display:inline-block;width:6px;height:6px;border-radius:6px;margin-right:5px;vertical-align:middle;}
/* quotes + figures (2-col table) */
table.cols{width:100%;border-collapse:separate;border-spacing:20px 0;margin:0 -20px;}
table.cols>tbody>tr>td{width:50%;vertical-align:top;}
.quote{border-left:2px solid var(--gold-d);padding:3px 0 3px 13px;margin:10px 0;}
.quote p{margin:0;font-family:var(--serif);font-style:italic;font-size:12px;}
.quote .en{font-style:normal;font-size:10px;color:var(--muted);margin-top:2px;}
.quote .who{font-family:var(--mono);font-size:8.5px;color:var(--faint);margin-top:3px;}
.fig{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:11px 13px;margin-bottom:9px;}
.fig .v{font-family:var(--serif);font-size:16px;font-weight:600;color:var(--gold);}
.fig .c{font-size:10px;color:var(--muted);}
/* actions */
ol.act{counter-reset:a;list-style:none;padding:0;margin-top:6px;}
ol.act li{counter-increment:a;position:relative;padding:9px 0 9px 34px;border-bottom:1px solid var(--line);}
ol.act li:before{content:counter(a);position:absolute;left:0;top:8px;width:23px;height:23px;border-radius:50%;background:rgba(216,180,90,.15);border:1px solid var(--gold-d);color:var(--gold);font-family:var(--mono);font-size:11px;text-align:center;line-height:22px;}
.chip{display:inline-block;font-family:var(--mono);font-size:8px;padding:2px 7px;border-radius:4px;border:1px solid var(--line);color:var(--muted);margin-left:5px;}
.footer{margin-top:26px;border-top:1px solid var(--line);padding-top:10px;font-family:var(--mono);font-size:8px;color:var(--faint);}
.footer td{font-family:var(--mono);font-size:8px;color:var(--faint);}
"""


def _e(x: Any) -> str:
    return html.escape(str(x if x is not None else ""))


def _arrow(d: int) -> str:
    cls = "up" if d > 0 else "down" if d < 0 else "flat"
    sym = "&#9650;" if d > 0 else "&#9660;" if d < 0 else "&#183;"
    return f"<span class='{cls}'>{sym} {abs(d)}%</span>"


def _story_card(st: dict[str, Any]) -> str:
    if st.get("thumb"):
        img = f"<div class='img' style=\"background-image:url('{_e(st['thumb'])}')\"></div>"
    else:
        img = f"<div class='ph'><span>{_e(st.get('source',''))}</span></div>"
    en = f"<div class='en'>EN &middot; {_e(st['title_en'])}</div>" if st.get("title_en") else ""
    breadth = f" &middot; {st['breadth']} outlets" if st.get("breadth", 1) > 1 else ""
    geo = f" &middot; {_e(st['geo'])}" if st.get("geo") else ""
    return (f"<div class='card'>{img}<div class='bd'><div class='ti'>{_e(st['title'])}</div>{en}"
            f"<div class='mt'><span class='dot' style='background:{_TONE_COLOR.get(st['tone'])}'></span>"
            f"{_e(st['source'])} &middot; Tier {_e(st['tier'])}{breadth}{geo}</div></div></div>")


def _grid(cells: list[str], cols: int = 2) -> str:
    """Lay out cards in a border-spaced table (WeasyPrint-safe 2-col grid)."""
    rows = []
    for i in range(0, len(cells), cols):
        chunk = cells[i:i + cols]
        while len(chunk) < cols:
            chunk.append("")
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in chunk) + "</tr>")
    return "<table class='grid'>" + "".join(rows) + "</table>"


def render_html(r: dict[str, Any]) -> str:
    n = r.get("narrative", {})
    k = r["kpis"]
    out: list[str] = [f"<!doctype html><html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>"]

    # masthead
    out.append(
        "<table class='mast'><tr><td>"
        f"<div class='eyebrow'>RIG OSINT &middot; DAILY STATE INTELLIGENCE BRIEF</div>"
        f"<h1>{_e(r['state'])} &mdash; Situation Snapshot</h1>"
        f"<div class='sub'>Prepared for <b style='color:var(--ink)'>{_e(r['principal'])} desk</b> &middot; 24-hour window</div>"
        "</td><td style='text-align:right'>"
        f"<div class='stamp'>{_e(r['generated_at'])[:16]} IST<br>WINDOW 24H &middot; vs PRIOR 24H<br>"
        f"CONFIDENCE &middot; {_e(r['confidence'])} ({k['n24']} stories)<br>CLASSIFICATION &middot; INTERNAL</div>"
        "</td></tr></table>")

    # kpis
    kpis = [
        ("Stories &middot; 24h", k["n24"], f"{_arrow(k['delta_pct'])} vs prior"),
        ("Net sentiment", f"{k['net_sentiment']:+d}%", f"{k['pos']} for &middot; {k['neg']} against"),
        ("Districts active", k["districts_active"], (_e(r['districts'][0]['name']) + " leads") if r["districts"] else ""),
        ("Adverse share", f"{k['adverse_pct']}%", "see risk heatmap"),
    ]
    out.append("<table class='kpis'><tr>" + "".join(
        f"<td class='kpi'><div class='l'>{l}</div><div class='v'>{v}</div><div class='d'>{d}</div></td>"
        for l, v, d in kpis) + "</tr></table>")

    # 1. Geographic Intelligence
    out.append("<h2><span class='ix'>1</span>Geography Intelligence</h2><div class='sub'>District-level coverage and movers.</div><table class='bars'>")
    maxd = max((d["n24"] for d in r["districts"]), default=1) or 1
    for d in r["districts"][:8]:
        out.append(f"<tr><td class='nm'>{_e(d['name'])}</td><td><div class='track'><i style='width:{round(100*d['n24']/maxd)}%'></i></div></td>"
                   f"<td class='vv'>{d['n24']} {_arrow(d['delta_pct'])}</td></tr>")
    out.append("</table>")
    if n.get("hotspot_read"):
        out.append(f"<div class='sub' style='margin-top:8px'><b>Hotspot read:</b> {_e(n['hotspot_read'])}</div>")

    # 2. Top Stories
    out.append("<h2><span class='ix'>2</span>Top Stories</h2><div class='sub'>Ranked by coverage breadth &mdash; the day's most-covered stories.</div>")
    out.append(_grid([_story_card(st) for st in r["top_stories"][:4]]))

    # 3. Heat Risk
    out.append("<h2><span class='ix'>3</span>Heat Risk</h2><div class='sub'>Severity = volume &times; adverse share &times; 24h velocity, by domain.</div>"
               "<table class='heat'><tr><th>Domain</th><th>Severity</th><th>Read</th><th style='text-align:right'>24h &middot; adverse</th></tr>")
    for d in r["domains"]:
        cls, lbl = _SEV[d["severity"]]
        out.append(f"<tr><td><b>{_e(d['domain'])}</b></td><td><span class='sev {cls}'>{lbl}</span></td>"
                   f"<td class='lede'>{d['adverse_pct']}% adverse &middot; {d['delta_pct']:+d}% vs prior</td>"
                   f"<td style='text-align:right;font-family:var(--mono)'>{d['n24']} &middot; {d['neg']}</td></tr>")
    out.append("</table>")

    # 4. Sentiment Analysis
    s3 = r["sentiment"]; tot = (s3["pos"] + s3["neu"] + s3["neg"]) or 1
    out.append("<h2><span class='ix'>4</span>Sentiment Analysis</h2>"
               "<table class='senti'><tr>"
               f"<td style='width:{100*s3['pos']//tot}%;background:var(--pos)'></td>"
               f"<td style='width:{100*s3['neu']//tot}%;background:var(--neu)'></td>"
               f"<td style='width:{100*s3['neg']//tot}%;background:var(--neg)'></td></tr></table>"
               f"<div class='sub'>{s3['pos']} supportive &middot; {s3['neu']} neutral &middot; {s3['neg']} critical &middot; net {s3['net_pct']:+d}%</div>")
    if n.get("sentiment_narrative"):
        out.append(f"<div class='lede' style='margin-top:6px'>{_e(n['sentiment_narrative'])}</div>")

    # 5. Key Developments
    out.append("<h2><span class='ix'>5</span>Key Developments</h2><div class='sub'>Clustered by theme, rewritten and contextualised.</div>")
    for dv in n.get("developments", []):
        out.append(f"<div class='dev'><div class='theme'>{_e(dv.get('theme',''))}</div>"
                   f"<h3>{_e(dv.get('headline',''))}</h3><div class='lede'>{_e(dv.get('body',''))}</div></div>")

    out.append("<table class='footer'><tr><td>RIG OSINT &middot; generated " + _e(r['generated_at'])[:16]
               + " IST &middot; auto-refreshed daily &middot; narrative:" + str(n.get('_source', '?'))
               + f"</td><td style='text-align:right'>{_e(r['state'])} desk</td></tr></table>")
    out.append("</body></html>")
    return "".join(out)


def render_pdf(r: dict[str, Any]) -> bytes:
    from weasyprint import HTML  # lazy — heavy
    return HTML(string=render_html(r)).write_pdf()
