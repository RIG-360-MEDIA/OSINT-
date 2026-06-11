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
ul.exec li{position:relative;padding:10px 0 10px 22px;border-bottom:1px solid var(--line);}
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
.dev{border:1px solid var(--line);border-radius:8px;padding:17px 19px;margin:14px 0;background:var(--panel);page-break-inside:avoid;}
.dev .theme{font-family:var(--mono);font-size:8.5px;letter-spacing:.13em;color:var(--gold);text-transform:uppercase;}
.dev h3{font-family:var(--serif);font-size:15px;margin:6px 0 7px;font-weight:600;}
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
.card .bd{padding:14px 16px;min-height:66px;}
.card .ti{font-size:13px;font-weight:600;line-height:1.38;}
.card .en{font-size:11px;color:var(--muted);margin-top:6px;}
.card .mt{font-family:var(--mono);font-size:8.5px;color:var(--faint);margin-top:10px;}
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
/* news-feed story rows (thumb left, text right — table, WeasyPrint-safe) */
table.feed{width:100%;border-collapse:collapse;margin-top:8px;}
table.feed td.story{padding:0 0 11px;}
table.feed td.story+td.story{padding-left:0;}
.nrow{border:1px solid var(--line);border-radius:9px;overflow:hidden;background:var(--panel);page-break-inside:avoid;}
table.nrow{width:100%;border-collapse:collapse;}
table.nrow td.th{width:96px;padding:0;vertical-align:top;}
table.nrow td.th .img{width:96px;height:74px;background:#14131d;background-size:cover;background-position:center;}
table.nrow td.th .ph{width:96px;height:74px;background:linear-gradient(135deg,#1b1a26,#121119);}
table.nrow td.bd{padding:11px 13px;vertical-align:top;}
.nrow .ti{font-size:11.5px;font-weight:600;line-height:1.36;}
.nrow .en{font-size:10px;color:var(--muted);margin-top:4px;}
.nrow .gl{font-size:10.5px;color:var(--muted);margin-top:5px;line-height:1.55;}
.nrow .mt{font-family:var(--mono);font-size:8px;color:var(--faint);margin-top:7px;}
/* deep-dive blocks — a proper news article: thumbnail, headline, EN translation, body.
   Stories FLOW continuously with NO forced breaks: the section-03 header is immediately
   followed by the first story (no orphaned header) and pages fill top-to-bottom with no
   big empty gaps. We deliberately DO NOT use page-break-inside:avoid — on a ~1-page block
   it can't fit the remaining space after the header, so it jumps to the next page and
   orphans the header behind a blank gap. A story may spill a few lines onto the next page;
   with sources moved to the section-08 appendix the blocks are small enough that any spill
   is minor. */
.deep{border:1px solid var(--line);border-radius:10px;padding:20px 22px;margin:16px 0;background:var(--panel);}
.deep .lead{width:100%;height:185px;border-radius:8px;background:#14131d;background-size:cover;background-position:center;border:1px solid var(--line);margin-bottom:14px;}
.deep .leadph{width:100%;height:185px;border-radius:8px;background:linear-gradient(135deg,#1b1a26,#121119);border:1px solid var(--line);margin-bottom:14px;position:relative;}
.deep .leadph span{position:absolute;bottom:12px;left:14px;font-family:var(--mono);font-size:9px;color:var(--faint);letter-spacing:.12em;}
.deep .dh{font-family:var(--serif);font-size:17px;font-weight:600;line-height:1.24;}
.deep .dhen{font-size:11.5px;color:var(--muted);margin-top:4px;}
.deep .why1{color:var(--gold);font-size:11px;font-style:italic;margin:6px 0 2px;}
.deep .lbl{font-family:var(--mono);font-size:9px;letter-spacing:.13em;color:var(--gold-d);text-transform:uppercase;margin:15px 0 4px;}
.deep p.body{margin:0;font-size:11px;line-height:1.72;color:var(--ink);}
.deep .metric{font-family:var(--mono);font-size:9px;color:var(--faint);margin-top:13px;letter-spacing:.04em;}
/* section-08 sources appendix — every article behind the deep dives, grouped by story.
   The section as a whole may flow across pages; only each per-story block avoids splitting. */
.srcsec .sblk{margin:0 0 16px;padding-bottom:13px;border-bottom:1px solid var(--line);page-break-inside:avoid;}
.srcsec .stitle{font-family:var(--serif);font-size:12px;font-weight:600;line-height:1.3;color:var(--ink);}
.srcsec .sten{font-size:9.5px;color:var(--muted);margin-top:2px;}
.srcsec .slinks{font-size:9.5px;color:var(--muted);line-height:1.85;margin-top:6px;}
.srcsec .slinks a,.srcsec .slinks span.s{color:var(--muted);}
/* light plain-prose blocks */
.plain{font-size:11.5px;line-height:1.72;color:var(--ink);margin-top:8px;}
.voices{font-size:11px;color:var(--muted);margin-top:8px;line-height:1.8;}
.voices b{color:var(--ink);}
table.coming{width:100%;border-collapse:collapse;margin-top:6px;font-size:10.5px;}
table.coming td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top;}
table.coming td.dt{width:120px;font-family:var(--mono);font-size:9px;color:var(--gold);}
/* No page-break-inside:avoid — that orphaned the section-07 header onto an otherwise-empty
   page; the analyst block now flows directly under its header and breaks naturally. */
.analyst{border:1px solid var(--gold-d);border-radius:10px;padding:18px 21px;margin-top:12px;background:var(--panel);}
.analyst p{margin:0 0 10px;font-size:11.5px;line-height:1.72;}
.analyst ul.exec{margin-top:4px;}
.analyst .lbl{font-family:var(--mono);font-size:8.5px;letter-spacing:.13em;color:var(--gold-d);text-transform:uppercase;margin:13px 0 3px;}
/* executive summary paragraph (top of brief) */
.execlede{border:1px solid var(--gold-d);border-radius:10px;padding:16px 19px;margin:18px 0 4px;background:var(--panel);}
.execlede .lbl0{font-family:var(--mono);font-size:8px;letter-spacing:.16em;color:var(--gold);text-transform:uppercase;margin-bottom:6px;}
.execlede p{margin:0;font-size:12px;line-height:1.74;color:var(--ink);}
/* at-a-glance strip (table, WeasyPrint-safe) */
table.glance{width:100%;border-collapse:separate;border-spacing:10px 0;margin:8px -10px 4px;}
table.glance td{width:25%;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:11px 13px;vertical-align:top;}
.glance .gl-l{font-family:var(--mono);font-size:8px;letter-spacing:.1em;color:var(--faint);text-transform:uppercase;}
.glance .gl-v{font-size:15px;font-weight:600;font-family:var(--serif);line-height:1.15;margin:3px 0 2px;}
.glance .gl-n{font-size:9.5px;color:var(--muted);line-height:1.5;}
/* deep-dive extras */
.deep .dtopic{display:inline-block;font-family:var(--mono);font-size:8px;letter-spacing:.13em;color:var(--gold);text-transform:uppercase;margin-bottom:4px;}
.deep .dq{border-left:2px solid var(--gold-d);padding:3px 0 3px 12px;margin:8px 0;}
.deep .dq p{margin:0;font-family:var(--serif);font-style:italic;font-size:11.5px;line-height:1.6;}
.deep .dqw{font-family:var(--mono);font-size:8px;color:var(--faint);margin-top:2px;}
table.dnums{width:100%;border-collapse:collapse;margin-top:3px;}
table.dnums td{padding:4px 6px;border-bottom:1px solid var(--line);vertical-align:top;font-size:10px;}
table.dnums td.nv{width:110px;font-family:var(--serif);font-weight:600;color:var(--gold);}
table.dnums td.nc{color:var(--muted);}
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


def _short_time(ca: str) -> str:
    """'2026-06-09 14:30:…' -> 'Jun 09 · 14:30'. Best-effort; blank on junk."""
    if not ca or len(ca) < 16:
        return ""
    mons = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    try:
        mo = int(ca[5:7])
        return f"{mons[mo]} {ca[8:10]} &middot; {ca[11:16]}"
    except (ValueError, IndexError):
        return ""


def _gloss(st: dict[str, Any]) -> str:
    """One-line plain 'what happened' gloss: prefer the standfirst, else a tone read."""
    sm = (st.get("summary") or "").strip()
    if sm:
        sm = sm.replace("\n", " ")
        return (sm[:155].rstrip() + "…") if len(sm) > 155 else sm
    tone = st.get("tone", "neutral")
    b = st.get("breadth", 1)
    spread = f"Running across {b} outlets" if b > 1 else "Single-outlet so far"
    mood = {"supportive": "favourable coverage", "hostile": "critical coverage"}.get(tone, "straight reporting")
    return f"{spread}; {mood}."


def _news_row(st: dict[str, Any]) -> str:
    """A horizontal news-feed card: thumbnail left, headline + gloss + meta right."""
    if st.get("thumb"):
        img = f"<div class='img' style=\"background-image:url('{_e(st['thumb'])}')\"></div>"
    else:
        img = "<div class='ph'></div>"
    en = f"<div class='en'>{_e(st['title_en'])}</div>" if st.get("title_en") else ""
    when = _short_time(st.get("ca", ""))
    meta_bits = [_e(st.get("source", ""))]
    if when:
        meta_bits.append(when)
    if st.get("breadth", 1) > 1:
        meta_bits.append(f"{st['breadth']} outlets")
    meta = " &middot; ".join(b for b in meta_bits if b)
    dot = f"<span class='dot' style='background:{_TONE_COLOR.get(st.get('tone','neutral'))}'></span>"
    return (f"<div class='nrow'><table class='nrow'><tr><td class='th'>{img}</td>"
            f"<td class='bd'><div class='ti'>{_e(st['title'])}</div>{en}"
            f"<div class='gl'>{_e(_gloss(st))}</div>"
            f"<div class='mt'>{dot}{meta}</div></td></tr></table></div>")


def _feed(stories: list[dict[str, Any]], cols: int = 2) -> str:
    """News rows laid out in a border-spaced table (WeasyPrint-safe multi-col)."""
    cells = [_news_row(st) for st in stories]
    rows = []
    for i in range(0, len(cells), cols):
        chunk = cells[i:i + cols]
        while len(chunk) < cols:
            chunk.append("")
        tds = "".join(f"<td class='story' style='width:50%;padding:0 7px 11px'>{c}</td>" for c in chunk)
        rows.append(f"<tr>{tds}</tr>")
    return "<table class='feed' style='margin:8px -7px 0'>" + "".join(rows) + "</table>"


def _src_links(sources: list[dict[str, Any]]) -> str:
    """The Sources line for a deep-dive — every underlying article, no cap."""
    parts = []
    for s in sources:
        label = _e(s.get("outlet") or s.get("url") or "source")
        url = s.get("url")
        if url:
            parts.append(f"<a href='{_e(url)}'>{label}</a>")
        else:
            parts.append(f"<span class='s'>{label}</span>")
    return " &middot; ".join(parts)


def _deep_quotes(quotes: list[dict[str, Any]]) -> str:
    """Verbatim quote block inside a deep-dive (speaker + outlet)."""
    parts = []
    for q in quotes:
        line = (q.get("q_en") or q.get("q") or "").strip()
        if not line:
            continue
        who = _e(q.get("who") or "—")
        src = f" &middot; {_e(q['src'])}" if q.get("src") else ""
        parts.append(f"<div class='dq'><p>&ldquo;{_e(line)}&rdquo;</p>"
                     f"<div class='dqw'>{who}{src}</div></div>")
    if not parts:
        return ""
    return "<div class='lbl'>In their words</div>" + "".join(parts)


def _deep_numbers(numbers: list[dict[str, Any]]) -> str:
    """The figures running through a deep-dive's coverage."""
    rows = []
    for n in numbers:
        ctx = _e(n.get("context", ""))
        val = f"{_e(n.get('value',''))} {_e(n.get('unit',''))}".strip()
        if not val:
            continue
        rows.append(f"<tr><td class='nv'>{val}</td><td class='nc'>{ctx}</td></tr>")
    if not rows:
        return ""
    return ("<div class='lbl'>The numbers</div>"
            "<table class='dnums'>" + "".join(rows) + "</table>")


def _deep_block(d: dict[str, Any]) -> str:
    # Lead thumbnail (the story's own image), or a labelled placeholder block when
    # absent — mirrors the top-story cards so every deep-dive reads like a real article.
    if d.get("thumb"):
        lead = f"<div class='lead' style=\"background-image:url('{_e(d['thumb'])}')\"></div>"
    else:
        lead = "<div class='leadph'><span>NO IMAGE</span></div>"
    # When the headline is non-English, its English translation sits on the line
    # directly below the headline (headline_en), only if it actually differs.
    hl, hlen = d.get("headline", ""), d.get("headline_en")
    en = f"<div class='dhen'>{_e(hlen)}</div>" if (hlen and hlen != hl) else ""
    dot = f"<span class='dot' style='background:{_TONE_COLOR.get(d.get('tone','neutral'))}'></span>"
    topic = f"<span class='dtopic'>{_e(d['topic'])}</span>" if d.get("topic") else ""
    why1 = f"<div class='why1'>{_e(d['why1'])}</div>" if d.get("why1") else ""
    drivers = ""
    if d.get("drivers"):
        names = ", ".join(_e(x) for x in d["drivers"][:3])
        drivers = (f"<div class='lbl'>Who's driving it</div>"
                   f"<p class='body'>{names}.</p>")
    quotes = _deep_quotes(d.get("quotes", []))
    numbers = _deep_numbers(d.get("numbers", []))
    # Per-dive sources removed — they are collected into the section-08 Sources appendix.
    return (f"<div class='deep'>{lead}{topic}<div class='dh'>{dot}{_e(d['headline'])}</div>{en}{why1}"
            f"<div class='lbl'>What happened</div><p class='body'>{_e(d['happened'])}</p>"
            f"<div class='lbl'>Why it matters to you</div><p class='body'>{_e(d['matters'])}</p>"
            f"{drivers}{quotes}{numbers}"
            f"<div class='metric'>{_e(d.get('metric_line',''))}</div></div>")


def _sources_section(deep: list[dict[str, Any]]) -> str:
    """The section-08 appendix: per-story source links, same order as the deep dives.

    Flows across pages as needed; only each per-story block (.sblk) avoids splitting.
    """
    blocks = []
    for d in deep:
        sources = d.get("sources") or []
        if not sources:
            continue
        hl = d.get("headline", "")
        hlen = d.get("headline_en")
        en = f"<div class='sten'>{_e(hlen)}</div>" if (hlen and hlen != hl) else ""
        blocks.append(
            f"<div class='sblk'><div class='stitle'>{_e(hl)}</div>{en}"
            f"<div class='slinks'>{_src_links(sources)}</div></div>")
    if not blocks:
        return ""
    return "<div class='srcsec'>" + "".join(blocks) + "</div>"


def _h2(ix: str, title: str, sub: str = "", brk: bool = False) -> str:
    """A numbered section heading with optional sub-line. brk=True starts a new page."""
    pb = " style='page-break-before:always'" if brk else ""
    head = f"<h2{pb}><span class='ix'>{ix}</span>{_e(title)}</h2>"
    if sub:
        head += f"<div class='sub'>{sub}</div>"
    return head


def render_html(r: dict[str, Any]) -> str:
    n = r.get("narrative", {})
    k = r["kpis"]
    out: list[str] = [f"<!doctype html><html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>"]

    # ── 1. Masthead + executive summary ──
    out.append(
        "<table class='mast'><tr><td>"
        f"<div class='eyebrow'>RIG OSINT &middot; DAILY STATE INTELLIGENCE BRIEF</div>"
        f"<h1>{_e(r['state'])} &mdash; Today's Brief</h1>"
        f"<div class='sub'>Prepared for the <b style='color:var(--ink)'>{_e(r['principal'])} desk</b> &middot; the last 24 hours</div>"
        "</td><td style='text-align:right'>"
        f"<div class='stamp'>{_e(r['generated_at'])[:16]} IST<br>{k['n24']} stories today<br>Confidence: {_e(r['confidence']).title()}</div>"
        "</td></tr></table>")
    exec_para = n.get("exec_paragraph") or ""
    if exec_para:
        out.append("<div class='execlede'><div class='lbl0'>Executive Summary</div>"
                   f"<p>{_e(exec_para)}</p></div>")

    # ── 2. At a glance ──
    glance = r.get("at_a_glance", [])
    if glance:
        md = r.get("mood")
        # Make explicit that 'Overall mood' is DIRECTED toward the principal and over
        # the shared 3-day window (so it can't be read as the day's undirected tone).
        glance_sub = "Where the day stands, in four reads."
        if md:
            glance_sub += (f" Mood is directed toward {_e(r['principal'])}, "
                           f"{_e(md['window_label'])}.")
        out.append(_h2("01", "At a Glance", glance_sub))
        cells = []
        for g in glance[:4]:
            cells.append(f"<td><div class='gl-l'>{_e(g.get('label',''))}</div>"
                         f"<div class='gl-v'>{_e(g.get('value',''))}</div>"
                         f"<div class='gl-n'>{_e(g.get('note',''))}</div></td>")
        while len(cells) < 4:
            cells.append("<td></td>")
        out.append("<table class='glance'><tr>" + "".join(cells) + "</tr></table>")

    # ── 3. Today's top stories — the news feed (10-15 stories) ──
    out.append(_h2("02", "Today's Top Stories",
                   "The stories moving across the state's press right now &mdash; most-covered first."))
    out.append(_feed(r["top_stories"][:14]))

    # ── 4. The big stories, explained — dedicated deep-dive per top story ──
    # Starts on a fresh page so the section heading sits at the top with its first
    # story, instead of trailing a lone leftover top-story card.
    deep = r.get("deep_dives", [])
    if deep:
        out.append(_h2("03", "The Big Stories, Explained",
                       "What each of today's leading stories is, and what it means for you.", brk=True))
        for d in deep:
            out.append(_deep_block(d))

    # ── 5. The coverage landscape — outlets, voices, districts ──
    si = r.get("source_intel", {})
    outlets = si.get("top_outlets", [])
    quotes = r.get("quotes", [])
    districts = r.get("districts", [])
    if outlets or quotes or districts:
        out.append(_h2("04", "The Coverage Landscape",
                       "Who is covering you, how they lean, and where it is landing."))
        if outlets:
            names = ", ".join(f"<b>{_e(o['name'])}</b> ({o['n']})" for o in outlets[:6])
            out.append(f"<div class='voices'>Leading the coverage today: {names} &mdash; the number in "
                       "brackets is how many of today's stories each ran.</div>")
        for q in quotes[:4]:
            line = q.get("q_en") or q.get("q") or ""
            if not line:
                continue
            who = _e(q.get("who") or "—")
            src = f" &mdash; {_e(q['src'])}" if q.get("src") else ""
            out.append(f"<div class='quote'><p>&ldquo;{_e(line)}&rdquo;</p><div class='who'>{who}{src}</div></div>")
        if districts:
            out.append("<div class='sub' style='margin-top:12px'>Where it's landing &mdash; the parts of "
                       "the state generating the most coverage.</div><table class='bars'>")
            maxd = max((d["n24"] for d in districts), default=1) or 1
            for d in districts[:8]:
                out.append(f"<tr><td class='nm'>{_e(d['name'])}</td><td><div class='track'>"
                           f"<i style='width:{round(100*d['n24']/maxd)}%'></i></div></td>"
                           f"<td class='vv'>{d['n24']} {_arrow(d['delta_pct'])}</td></tr>")
            out.append("</table>")
        if n.get("hotspot_read"):
            out.append(f"<div class='plain'>{_e(n['hotspot_read'])}</div>")

    # ── 6. The mood — the SHARED 3-day directed mood (matches Home + War Room). The
    # bar + split read from the shared mood over its window; cold-start (no principal)
    # falls back to the 24h undirected sentiment split. ──
    md = r.get("mood")
    s3 = r["sentiment"]
    m_pos, m_neu, m_neg = (md["pos"], md["neu"], md["neg"]) if md else (s3["pos"], s3["neu"], s3["neg"])
    tot = (m_pos + m_neu + m_neg) or 1
    win = _e(md["window_label"]) if md else "last 24 hours"
    out.append(_h2("05", "The Mood",
                   (f"Directed toward {_e(r['principal'])} &middot; {win}." if md
                    else f"Overall coverage tone &middot; {win}.")))
    out.append("<table class='senti'><tr>"
               f"<td style='width:{100*m_pos//tot}%;background:var(--pos)'></td>"
               f"<td style='width:{100*m_neu//tot}%;background:var(--neu)'></td>"
               f"<td style='width:{100*m_neg//tot}%;background:var(--neg)'></td></tr></table>"
               f"<div class='sub'>{m_pos} supportive &middot; {m_neu} neutral &middot; {m_neg} critical "
               f"&middot; {win}</div>")
    mood_word = md["word"] if md else (
        "broadly positive" if s3["net_pct"] > 8 else "broadly negative" if s3["net_pct"] < -8 else "mixed")
    subj = (f" toward the {_e(r['principal'])} desk" if md else "")
    out.append(f"<div class='plain'>Taken together, the mood{subj} over the {win} is <b>{mood_word}</b>. "
               "For every story written in a supportive light there were others that ran critical, and most "
               "reporting sat somewhere in between.</div>")
    if n.get("sentiment_narrative"):
        out.append(f"<div class='plain'>{_e(n['sentiment_narrative'])}</div>")

    # ── 7. What's coming — upcoming dated events (rising signals as a proxy) ──
    early = r.get("early_warning", [])
    if early:
        out.append(_h2("06", "What's Coming",
                       "Threads gathering pace that are likely to grow over the coming days."))
        out.append("<table class='coming'>")
        for e in early:
            out.append(f"<tr><td class='dt'>{_e(e.get('kind','').title())}</td><td><b>{_e(e['label'])}</b> &mdash; "
                       f"coverage is climbing ({e['prior']} &rarr; {e['now']} stories), worth keeping an eye on.</td></tr>")
        out.append("</table>")

    # ── 8. The analyst's read — the single heavy-analysis block, last ──
    out.append(_h2("07", "The Analyst's Read",
                   "One desk-level assessment of where the day leaves you."))
    out.append("<div class='analyst'>")
    es = n.get("exec_summary") or []
    if es:
        out.append("<ul class='exec'>" + "".join(f"<li>{_e(b)}</li>" for b in es) + "</ul>")
    for dv in n.get("developments", [])[:3]:
        body = dv.get("body", "")
        if body:
            out.append(f"<p><b>{_e(dv.get('headline',''))}.</b> {_e(body)}</p>")
    acts = n.get("actions") or []
    if acts:
        out.append("<div class='lbl' style='margin-top:8px'>Recommended actions</div>")
        out.append("<ol class='act'>" + "".join(f"<li>{_e(a)}</li>" for a in acts[:5]) + "</ol>")
    out.append("</div>")

    # ── 9. Sources — every article behind today's deep dives, grouped by story ──
    if deep:
        sources_html = _sources_section(deep)
        if sources_html:
            out.append(_h2("08", "Sources",
                           "Every article behind today's deep dives, grouped by story."))
            out.append(sources_html)

    out.append("<table class='footer'><tr><td>RIG OSINT &middot; Daily State Intelligence Brief &middot; "
               "generated " + _e(r['generated_at'])[:16] + " IST &middot; every figure corpus-grounded "
               "from the last 24 hours of state press</td><td style='text-align:right'>"
               + f"{_e(r['state'])} desk &middot; Confidence: {_e(r['confidence']).title()}</td></tr></table>")
    out.append("</body></html>")
    return "".join(out)


def render_pdf(r: dict[str, Any]) -> bytes:
    from weasyprint import HTML  # lazy — heavy
    return HTML(string=render_html(r)).write_pdf()
