"""Render the assembled report JSON (briefing.report) to the full designed HTML.

The complete 10-section government media briefing: Robin masthead, Key Numbers,
§1 Daily Brief, §2 Big Story, §3 Coverage by Topic (3-media image cards),
§4 Districts, §5 Media Compared, §6 What Each Side Said, §7 Figures,
§8 Which Outlet, §9 All Stories. Telugu renders inline; newspaper cuttings
embed as data-URI images (work everywhere, incl. artifact CSP).

Usage (osint-backend): python -m briefing.render <cover_date>  -> prints HTML.
"""
from __future__ import annotations

import html
from typing import Any

from sqlalchemy import text
from db import get_db

ORG = "31ad3fa9-25eb-4b3c-8a56-360696fc680a"


def _e(x: Any) -> str:
    return html.escape(str(x if x is not None else ""))


def _net_cls(n):
    if n is None:
        return "z"
    return "pos" if n > 5 else "neg" if n < -5 else "z"


def _bar(fav, crit):
    d = (fav + crit) or 1
    return (f"<span class='rowbar'><i class='p' style='width:{round(100*fav/d)}%'></i>"
            f"<i class='n' style='width:{round(100*crit/d)}%'></i></span>")


def _tel(s):
    return f"<span class='tel'>{_e(s)}</span>" if any('ఀ' <= c <= '౿' for c in (s or "")) else _e(s)


def _datauri(b64):
    if not b64:
        return None
    return b64 if str(b64).startswith("data:") else f"data:image/jpeg;base64,{b64}"


def _dcls(net):
    return ("q1" if net > -30 else "q2" if net > -45 else "q3" if net > -60 else "q4" if net > -75 else "q5")


CSS = """
:root{--paper:#fff;--ink:#14181d;--ink2:#3c4650;--muted:#66707b;--faint:#949ca6;
--hair:#e2e6ea;--hair2:#eef1f4;--navy:#183a63;--navy2:#2b5288;--navy-soft:#eef2f8;--navy-line:#cdd8e8;
--pro:#1f7a46;--pro-soft:#e6f2ea;--anti:#b02a24;--anti-soft:#fbe9e7;--warn:#8a5a12;--warn-soft:#faf1de;
--serif:"Charter","Sitka Text",Cambria,Georgia,serif;--sans:"Inter",ui-sans-serif,"Segoe UI",Arial,sans-serif;
--mono:ui-monospace,Consolas,"DejaVu Sans Mono",monospace;--tel:"Nirmala UI","Noto Sans Telugu",sans-serif;}
*{box-sizing:border-box}body{margin:0;background:#e9edf1;color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.55}
.paper{max-width:1120px;margin:22px auto 60px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 2px rgba(16,24,32,.08),0 10px 34px rgba(16,24,32,.10);font-family:var(--serif)}
.topbar{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:16px 46px;background:var(--navy);color:#fff}
.dept{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:#dfe7f2}
.brand .bn{font-family:var(--sans);font-size:15px;font-weight:800;letter-spacing:.26em;text-transform:uppercase}
.brand .bs{font-family:var(--mono);font-size:8px;letter-spacing:.32em;text-transform:uppercase;color:#9fb3cf;display:block;margin-top:3px}
.mast{padding:30px 46px 20px;border-bottom:3px solid var(--navy)}
.mast h1{font-family:var(--serif);font-size:52px;line-height:.92;margin:0;font-weight:600;letter-spacing:-.028em}
.mast .dek{font-family:var(--sans);font-size:12.5px;color:var(--muted);margin-top:13px;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
.mast .dek b{color:var(--ink);font-weight:650}
.kstrip{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--hair)}
.kt{padding:16px 18px;border-right:1px solid var(--hair)}.kt:last-child{border-right:0}
.kl{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}
.kv{font-family:var(--serif);font-size:28px;font-weight:600;line-height:1.05;margin-top:7px;font-variant-numeric:tabular-nums}
.kv.neg{color:var(--anti)}.kv.pos{color:var(--pro)}
.ks{font-family:var(--sans);font-size:11px;color:var(--muted);margin-top:5px}.ks b{color:var(--ink);font-weight:650}
.mbar{display:flex;height:8px;border-radius:2px;overflow:hidden;margin:9px 0 2px;background:var(--hair2)}
.mbar i.a{background:var(--navy)}.mbar i.b{background:#7d97bc}.mbar i.c{background:#c3d0e2}
.tbar{display:flex;height:8px;border-radius:2px;overflow:hidden;margin:8px 0 3px;background:#eef1f3}
.tbar i.p{background:var(--pro)}.tbar i.n{background:var(--anti)}
.to{display:flex;align-items:baseline;gap:6px;padding:4px 0;border-bottom:1px solid var(--hair2);font-family:var(--sans);font-size:11.5px}
.to:last-child{border-bottom:0}.to b{font-weight:650;color:var(--ink);font-family:var(--serif);font-size:13px}
.to span{color:var(--faint);font-size:9px;text-transform:uppercase}.to i{margin-left:auto;font-family:var(--mono);font-style:normal;font-variant-numeric:tabular-nums}
section{padding:30px 46px;border-bottom:1px solid var(--hair2)}
.shead{display:flex;align-items:baseline;gap:12px;border-bottom:2px solid var(--navy);padding-bottom:7px;margin-bottom:6px}
.shead .num{font-family:var(--mono);font-size:12px;color:var(--navy2);font-weight:700}
.shead h2{font-family:var(--serif);font-size:22px;font-weight:600;margin:0;letter-spacing:-.01em}
.shead .cnt{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--faint);text-transform:uppercase}
.sf{font-family:var(--sans);font-size:12.5px;color:var(--muted);margin:8px 0 0}
ol.brief{list-style:none;counter-reset:b;margin:16px 0 0;padding:0}
ol.brief li{counter-increment:b;display:grid;grid-template-columns:30px 1fr;gap:16px;padding:16px 0;border-bottom:1px solid var(--hair2)}
ol.brief li:last-child{border-bottom:0}
ol.brief li:before{content:counter(b,decimal-leading-zero);font-family:var(--mono);font-size:12px;color:var(--navy2);font-weight:700;padding-top:3px}
ol.brief h3{font-family:var(--serif);font-size:16.5px;font-weight:600;margin:0 0 5px;line-height:1.3}
.tel{font-family:var(--tel)}
ol.brief .ev{font-family:var(--serif);font-size:14px;color:var(--ink2);line-height:1.5;margin:0 0 8px}
.tags{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.tag{font-family:var(--sans);font-size:9.5px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;padding:3px 8px;border-radius:4px;background:var(--hair2);color:var(--ink2)}
.cites{margin-top:9px;font-family:var(--sans);font-size:11px;line-height:1.7;color:var(--faint2,#8a8778)}
.cites .cl{font-weight:700;text-transform:uppercase;letter-spacing:.05em;font-size:9.5px;color:var(--navy2);margin-right:7px}
.cites a{color:var(--navy2);text-decoration:none;border-bottom:1px solid var(--hair)}
.cites a:hover{border-bottom-color:var(--navy2)}
.cites .nolink{color:var(--faint,#9a978a)}
.tag.p{background:var(--pro-soft);color:var(--pro)}.tag.n{background:var(--anti-soft);color:var(--anti)}.tag.g{background:var(--navy-soft);color:var(--navy2)}
.big{margin-top:16px;border:1px solid var(--hair);border-radius:10px;overflow:hidden}
.big .bh{background:var(--navy-soft);padding:18px 22px;border-bottom:1px solid var(--navy-line)}
.big .bh .lead{font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--navy2)}
.big .bh h3{font-family:var(--serif);font-size:22px;font-weight:600;margin:5px 0 0;line-height:1.2}
.big .bb{padding:18px 22px}
.big .bb p.nar{font-family:var(--serif);font-size:15px;line-height:1.62;color:var(--ink);margin:0 0 12px}
.big .bb p.nar:first-child{font-size:16px}
.spread{display:flex;gap:16px;flex-wrap:wrap;margin:4px 0 14px;padding-top:12px;border-top:1px solid var(--hair2)}
.sp b{font-family:var(--serif);font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.sp span{font-family:var(--sans);font-size:10px;color:var(--muted);text-transform:uppercase;display:block}
.qp{border-left:3px solid var(--navy-line);padding:3px 0 3px 13px;margin:10px 0;font-family:var(--serif);font-size:14px;line-height:1.5}
.qp.n{border-left-color:var(--anti)}.qp.p{border-left-color:var(--pro)}
.qp .src{font-family:var(--sans);font-size:10.5px;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;margin-top:14px;font-size:13px}
th{font-family:var(--sans);font-size:9px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--faint);text-align:left;padding:0 10px 7px 0;border-bottom:1px solid var(--hair);white-space:nowrap}
td{padding:9px 10px 9px 0;border-bottom:1px solid var(--hair2);vertical-align:top}
td.nm{font-weight:600;font-family:var(--serif)}
td.num,th.num{text-align:right;font-family:var(--mono);font-size:11.5px;font-variant-numeric:tabular-nums;padding-right:0}
.rowbar{width:58px;height:7px;border-radius:2px;overflow:hidden;display:inline-flex;background:#eef1f3;vertical-align:middle}
.rowbar i.p{background:var(--pro)}.rowbar i.n{background:var(--anti)}
.net{font-family:var(--mono);font-variant-numeric:tabular-nums}.net.neg{color:var(--anti)}.net.pos{color:var(--pro)}.net.z{color:var(--muted)}
.panels{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:16px}
.panel{border:1px solid var(--hair);border-radius:10px;padding:16px}
.panel .ph{font-family:var(--sans);font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--navy2)}
.panel .pn{font-family:var(--serif);font-size:30px;font-weight:600;margin-top:8px;font-variant-numeric:tabular-nums}
.panel .pn.neg{color:var(--anti)}.panel .pn.pos{color:var(--pro)}
.figs{display:grid;grid-template-columns:repeat(2,1fr);gap:12px 26px;margin-top:14px}
.fig{border-top:2px solid var(--navy);padding-top:8px}
.fig .v{font-family:var(--serif);font-size:19px;font-weight:600;color:var(--navy);font-variant-numeric:tabular-nums}
.fig .c{font-family:var(--sans);font-size:11px;color:var(--ink2);margin-top:3px}
/* topic cards */
.tblock{border:1px solid var(--hair);border-radius:10px;overflow:hidden;margin-top:14px}
.tbh{display:flex;align-items:center;gap:12px;padding:11px 16px;background:#f6f8fa;border-bottom:1px solid var(--hair)}
.tbh h3{font-family:var(--serif);font-size:16px;font-weight:600;margin:0}
.tbh .net{margin-left:auto;font-family:var(--serif);font-size:16px;font-weight:600}
.cards{display:grid;grid-template-columns:repeat(3,1fr)}
.card{padding:12px 14px;border-right:1px solid var(--hair2)}.card:last-child{border-right:0}
.card .cm{font-family:var(--sans);font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--navy2);margin-bottom:8px}
.thumb{height:96px;border-radius:6px;margin-bottom:9px;overflow:hidden;border:1px solid var(--hair);background:#eef2f7;display:flex;align-items:center;justify-content:center}
.thumb img{width:100%;height:100%;object-fit:cover}
.thumb.tv{background:linear-gradient(135deg,#1c1f26,#2c3442);position:relative}
.thumb.tv .play{position:absolute;color:#fff;font-size:24px;opacity:.92}
.thumb.web{background:linear-gradient(135deg,#e7edf4,#d3deeb)}
.thumb.newspaper{background:#faf9f4;border-color:#e5e2d4}
.thumb.ph{background-image:none}
.thumb.ph.web{background:linear-gradient(135deg,#e7edf4,#d3deeb)}
.thumb.ph.newspaper{background:repeating-linear-gradient(#faf9f4,#faf9f4 8px,#f0eee2 9px,#f0eee2 10px)}
.card.empty{opacity:.7}.card .none{font-family:var(--sans);font-size:11px;color:var(--faint);margin-top:2px}
.card h4{font-family:var(--serif);font-size:13px;font-weight:600;margin:0 0 5px;line-height:1.3}
.card .meta{font-family:var(--sans);font-size:10px;color:var(--muted);display:flex;align-items:center;gap:6px}
.dot{width:7px;height:7px;border-radius:50%}.dot.n{background:var(--anti)}.dot.p{background:var(--pro)}.dot.z{background:var(--faint)}
/* district map */
.dmap{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin:14px 0 6px}
.tile{border:1px solid var(--hair);border-radius:4px;padding:7px;min-height:46px;font-family:var(--sans);font-size:9px;line-height:1.2}
.tile b{font-weight:650;color:var(--ink);display:block}.tile span{font-family:var(--mono);font-size:8.5px;color:var(--ink2)}
.tile.q1{background:#e2f0e8}.tile.q2{background:#eef4ef}.tile.q3{background:#f8f1e4}.tile.q4{background:#f8ddd8}.tile.q5{background:#efbdb6}
/* quote contrast */
.qcols{display:grid;grid-template-columns:1fr 1fr;gap:0;border:1px solid var(--hair);border-radius:10px;overflow:hidden;margin-top:14px}
.qcol{padding:16px 18px}.qcol+.qcol{border-left:1px solid var(--hair)}
.qcol .qs{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px}
.qcol.g .qs{color:var(--pro)}.qcol.o .qs{color:var(--anti)}
.qcol blockquote{margin:0 0 12px;font-family:var(--serif);font-size:14px;line-height:1.5;padding-bottom:10px;border-bottom:1px solid var(--hair2)}
.qcol blockquote:last-child{border-bottom:0;margin-bottom:0}
.qcol .who{font-family:var(--sans);font-size:10.5px;color:var(--muted);margin-top:5px}.qcol .who b{color:var(--ink)}
/* annexure */
.anx{margin-top:12px}
.ax{display:grid;grid-template-columns:24px 1fr auto;gap:12px;padding:9px 0;border-bottom:1px solid var(--hair2);align-items:baseline}
.ax .r{font-family:var(--mono);font-size:10px;color:var(--navy2);font-weight:700}
.ax h4{font-family:var(--serif);font-size:13.5px;font-weight:600;margin:0}
.ax .amt{font-family:var(--sans);font-size:10px;color:var(--muted)}
.ax .amt .med{font-weight:700;text-transform:uppercase;font-size:9px;color:var(--ink2)}
.ax a{font-family:var(--sans);font-size:11px;color:var(--navy2);white-space:nowrap;text-decoration:none;border:1px solid var(--navy-line);border-radius:5px;padding:4px 9px;align-self:center}
.lab2{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin:16px 0 8px}
.tbp{display:flex;flex-direction:column;gap:6px;max-width:420px}
.tbprow{display:grid;grid-template-columns:90px 1fr 40px;gap:10px;align-items:center;font-family:var(--sans);font-size:12px}
.tbprow .tl{color:var(--ink2)}.tbprow .tn{text-align:right;font-family:var(--mono);font-size:11px}
.bignums{display:flex;flex-wrap:wrap;gap:16px}
.bn{border-top:2px solid var(--navy);padding-top:7px;min-width:130px}
.bn b{font-family:var(--serif);font-size:17px;font-weight:600;color:var(--navy);font-variant-numeric:tabular-nums;display:block}
.bn span{font-family:var(--sans);font-size:10.5px;color:var(--ink2);line-height:1.35;display:block;margin-top:2px}
.gl{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin:14px 0 6px}
.alleg{font-family:var(--sans);font-size:9px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:2px 6px;border-radius:3px;background:var(--warn-soft);color:var(--warn);margin-left:4px}
.diverge{margin-top:16px;background:var(--navy-soft);border:1px solid var(--navy-line);border-radius:8px;padding:14px 18px}
.diverge .dl{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--navy2);margin-bottom:6px}
.diverge p{margin:0;font-family:var(--serif);font-size:14px;line-height:1.5}
.src2{font-family:var(--sans);font-size:10px;color:var(--faint)}
.dcrit{font-family:var(--sans);font-size:11px;color:var(--anti);line-height:1.3}
.dpos{font-family:var(--sans);font-size:11px;color:var(--pro);line-height:1.3}
.qtag{font-family:var(--sans);font-size:8.5px;font-weight:700;text-transform:uppercase;padding:1px 5px;border-radius:3px;vertical-align:middle}
.qtag.g{background:var(--pro-soft);color:var(--pro)}.qtag.o{background:var(--anti-soft);color:var(--anti)}
.lean{font-family:var(--sans);font-size:8.5px;font-weight:700;text-transform:uppercase;padding:1px 6px;border-radius:3px;vertical-align:middle;margin-left:4px}
.lean.n{background:var(--anti-soft);color:var(--anti)}.lean.p{background:var(--pro-soft);color:var(--pro)}
.colo{padding:22px 46px;background:var(--navy);color:#c7d3e4;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;font-family:var(--sans);font-size:10.5px;line-height:1.7}
.colo b{color:#fff}.colo .rb{font-weight:800;letter-spacing:.14em;text-transform:uppercase;font-size:11px;color:#fff}
/* ── print / PDF (headless Chromium) — screen == download == print ── */
@page{size:A4;margin:11mm 12mm}
@media print{
 body{background:#fff}
 .paper{max-width:none;margin:0;border-radius:0;box-shadow:none}
 .topbar,.mast,.colo{padding-left:12mm;padding-right:12mm}
 section{padding:16px 12mm;break-inside:auto}
 .kstrip{padding:0 12mm}
 .shead{break-after:avoid}
 .tblock,.card,.big,.qcols,.qcol,.panel,.fig,.ax,.qp,ol.brief li,.to,.tile{break-inside:avoid}
 tr{break-inside:avoid}
 h1,h2,h3,h4{break-after:avoid}
 .cards{break-inside:avoid}
 a{color:inherit;text-decoration:none}
}
"""


def render_html(r: dict[str, Any]) -> str:
    s = r["strip"]; sent = s["sentiment"]; bp = s["by_pillar"]
    o = [f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body><div class='paper'>"]
    o.append("<div class='topbar'><div class='dept'>Telangana &middot; Information &amp; Public Relations</div>"
             "<div class='brand'><span class='bn'>Robin</span><span class='bs'>Media Watch</span></div></div>")
    o.append(f"<div class='mast'><h1>Daily Media Briefing</h1><div class='dek'>"
             f"<b>Covering {_e(r['cover_date'])} &middot; 00:00&ndash;23:59 IST</b>"
             f"<span>Newspapers &middot; Television &middot; Online</span></div></div>")
    tot = s["total"] or 1
    top = s.get("top_outlet_by_medium", {})
    outrows = "".join(
        f"<div class='to'><b>{_e((top.get(p) or {}).get('outlet','—'))}</b><span>{lab}</span>"
        f"<i>{(top.get(p) or {}).get('n','')}</i></div>"
        for p, lab in [("newspaper", "Paper"), ("tv", "TV"), ("web", "Web")] if top.get(p))
    fc = (sent['favourable'] + sent['critical']) or 1
    o.append(
        "<div class='kstrip'>"
        f"<div class='kt'><div class='kl'>Total Stories</div><div class='kv'>{s['total']:,}</div>"
        f"<div class='mbar'><i class='a' style='width:{round(100*bp['web']/tot)}%'></i>"
        f"<i class='b' style='width:{round(100*bp['newspaper']/tot)}%'></i>"
        f"<i class='c' style='width:{round(100*bp['tv']/tot)}%'></i></div>"
        f"<div class='ks'>Web <b>{bp['web']}</b> &middot; Papers <b>{bp['newspaper']}</b> &middot; TV <b>{bp['tv']}</b> &middot; from {s.get('scanned', s['total']):,} scanned</div></div>"
        f"<div class='kt'><div class='kl'>Biggest Subject</div><div class='kv'>{_e(s['biggest_subject']['topic'] or '—')}</div>"
        f"<div class='ks'>{s['biggest_subject']['items']} of {s['total']} government stories</div></div>"
        f"<div class='kt'><div class='kl'>Sentiment</div><div class='kv {_net_cls(sent['net'])}'>{sent['net']:+d}</div>"
        f"<div class='tbar'><i class='p' style='width:{round(100*sent['favourable']/fc)}%'></i>"
        f"<i class='n' style='width:{round(100*sent['critical']/fc)}%'></i></div>"
        f"<div class='ks'>{sent['favourable']} for &middot; {sent['critical']} against &middot; {sent['neutral']} no side</div></div>"
        f"<div class='kt'><div class='kl'>Top Outlet, each medium</div>{outrows}</div></div>")

    # §1 Daily Brief
    o.append("<section><div class='shead'><span class='num'>1</span><h2>Daily Brief</h2>"
             f"<span class='cnt'>{min(len(r.get('events',[])),6)} stories</span></div>"
             "<p class='sf'>The day's biggest government stories, grouped across newspapers, television and online.</p><ol class='brief'>")
    for e in r.get("events", [])[:6]:
        net = e.get("net") or 0
        vcls = "n" if net < -5 else "p" if net > 5 else "g"
        vlabel = "critical" if net < -5 else "favourable" if net > 5 else "mixed"
        sp = f"web {e['spread_web']}" + (f" &middot; TV {e['spread_tv']}" if e['spread_tv'] else "") + (f" &middot; paper {e['spread_np']}" if e['spread_np'] else "")
        head = e.get("headline") or e["label"]
        body = e.get("paragraph") or e.get("evidence") or ""
        # citations — each contributing outlet, linked to the original report
        srcs = e.get("sources") or []
        _cap = 12
        _chips = []
        for s in srcs[:_cap]:
            nm = _tel(s.get("outlet") or "")
            if s.get("url"):
                _chips.append(f"<a href='{_e(s['url'])}' target='_blank' rel='noopener'>{nm}</a>")
            else:
                _chips.append(f"<span class='nolink'>{nm}</span>")
        _more = len(srcs) - _cap
        if _more > 0:
            _chips.append(f"<span class='nolink'>+{_more} more</span>")
        cites = (f"<div class='cites'><span class='cl'>Sources</span>{' &middot; '.join(_chips)}</div>"
                 if _chips else "")
        o.append(f"<li><div><h3>{_tel(head)}</h3>"
                 + (f"<p class='ev'>{_tel(body)}</p>" if body else "")
                 + "<div class='tags'>"
                 + (f"<span class='tag g'>{_e(e['topic'])}</span>" if e.get("topic") else "")
                 + (f"<span class='tag g'>{_e(e['department'])}</span>" if e.get("department") else "")
                 + f"<span class='tag {vcls}'>{vlabel} &middot; net {net:+d}</span>"
                 + f"<span class='tag'>{sp} &middot; {e['size']} reports</span></div>"
                 + cites + "</div></li>")
    o.append("</ol></section>")

    # §2 Big Story
    b = r.get("big_story")
    if b:
        bhead = b.get("headline") or b["label"]
        o.append("<section><div class='shead'><span class='num'>2</span><h2>The Big Story</h2></div><div class='big'>"
                 f"<div class='bh'><div class='lead'>Most-covered story &middot; net tone {b['net']:+d}</div>"
                 f"<h3>{_tel(bhead)}</h3></div><div class='bb'>")
        for para in b.get("narrative", [])[:3]:
            o.append(f"<p class='nar'>{_e(para)}</p>")
        o.append("<div class='spread'>"
                 f"<div class='sp'><b>{b['spread']['web']}</b><span>web outlets</span></div>"
                 f"<div class='sp'><b>{b['spread']['tv']}</b><span>TV channels</span></div>"
                 f"<div class='sp'><b>{b['spread']['newspaper']}</b><span>newspapers</span></div>"
                 f"<div class='sp'><b>{b['size']}</b><span>total reports</span></div></div>")
        tbp = {t['pillar']: t for t in b.get("tone_by_pillar", [])}
        if tbp:
            o.append("<div class='lab2'>Tone across the media that ran it</div><div class='tbp'>")
            for p, lab in [("newspaper", "Newspapers"), ("tv", "Television"), ("web", "Online")]:
                t = tbp.get(p)
                if not t:
                    continue
                o.append(f"<div class='tbprow'><span class='tl'>{lab}</span>{_bar(t['favourable'], t['critical'])}"
                         f"<span class='tn net {_net_cls(t['net'])}'>{t['net']:+d}</span></div>")
            o.append("</div>")
        if b.get("numbers"):
            o.append("<div class='lab2'>Numbers in the coverage</div><div class='bignums'>")
            for n in b["numbers"][:4]:
                o.append(f"<div class='bn'><b>{_e(n['value'])} {_e(n['unit'])}</b><span>{_e(n['context'])}</span></div>")
            o.append("</div>")
        o.append("<div class='lab2'>What the coverage said</div>")
        for q in b.get("evidence", [])[:6]:
            qc = "n" if q["verdict"] == "critical" else "p" if q["verdict"] == "favourable" else ""
            o.append(f"<div class='qp {qc}'>{_tel(q['text'])}<div class='src'>&mdash; {_e(q['source'])} &middot; {_e(q['pillar'])}"
                     + (f" &middot; {_e(q['lands_on'])}" if q.get("lands_on") else "") + "</div></div>")
        o.append("</div></div></section>")

    # §3 Coverage by Topic — media cards
    tc = r.get("topic_cards", {})
    topic_order = [t["topic"] for t in r.get("topics", [])]
    o.append("<section><div class='shead'><span class='num'>3</span><h2>Coverage by Topic</h2>"
             f"<span class='cnt'>{len(tc)} topics</span></div>"
             "<p class='sf'>For each subject, the most representative item from each medium.</p>")
    tnet = {t["topic"]: t for t in r.get("topics", [])}
    for tname in topic_order:
        cards = tc.get(tname)
        if not cards:
            continue
        tr = tnet.get(tname, {})
        o.append(f"<div class='tblock'><div class='tbh'><h3>{_e(tname)}</h3>"
                 f"<span class='net {_net_cls(tr.get('net',0))}'>{tr.get('net',0):+d}</span></div><div class='cards'>")
        for pillar, lab in [("web", "Top article"), ("tv", "Top TV clip"), ("newspaper", "Top cutting")]:
            c = cards.get(pillar)
            if not c:
                o.append(f"<div class='card empty'><div class='cm'>{lab}</div>"
                         f"<div class='thumb {pillar} ph'></div><div class='none'>No {pillar} coverage on this topic</div></div>")
                continue
            dot = "n" if c["verdict"] == "critical" else "p" if c["verdict"] == "favourable" else "z"
            if pillar == "newspaper" and c.get("img"):
                thumb = f"<div class='thumb'><img src='{_e(_datauri(c['img']))}' alt=''></div>"
            elif pillar == "newspaper" and c.get("thumb"):
                thumb = f"<div class='thumb newspaper'><img src='{_e(c['thumb'])}' alt='' onerror=\"this.parentNode.classList.add('ph')\"></div>"
            elif pillar == "tv" and c.get("video_id"):
                thumb = (f"<div class='thumb tv'><img src='https://img.youtube.com/vi/"
                         f"{_e(c['video_id'])}/hqdefault.jpg' alt='' onerror=\"this.style.display='none'\"><span class='play'>&#9654;</span></div>")
            elif pillar == "web" and c.get("thumb"):
                thumb = f"<div class='thumb web'><img src='{_e(c['thumb'])}' alt='' onerror=\"this.parentNode.classList.add('ph')\"></div>"
            else:
                thumb = f"<div class='thumb {pillar} ph'></div>"
            o.append(f"<div class='card'><div class='cm'>{lab}</div>{thumb}"
                     f"<h4>{_tel((c.get('title') or '')[:80])}</h4>"
                     f"<div class='meta'><span class='dot {dot}'></span>{_e(c['source'])}</div></div>")
        o.append("</div></div>")
    o.append("</section>")

    # §4 Schemes
    sr = r.get("schemes", [])
    if sr:
        o.append("<section><div class='shead'><span class='num'>4</span><h2>How Each Scheme Was Covered</h2>"
                 f"<span class='cnt'>{len(sr)} schemes</span></div>"
                 "<p class='sf'>Flagship programmes and how the press treated them. The last column is the most repeated complaint.</p>"
                 "<table><thead><tr><th>Scheme</th><th class='num'>Items</th><th>Tone</th><th class='num'>Net</th><th>Most repeated complaint</th></tr></thead><tbody>")
        for s in sr:
            o.append(f"<tr><td class='nm'>{_e(s['scheme'])}</td><td class='num'>{s['items']}</td>"
                     f"<td>{_bar(s['favourable'], s['critical'])}</td>"
                     f"<td class='num net {_net_cls(s['net'])}'>{s['net']:+d}</td>"
                     f"<td>{_tel((s.get('note') or '—')[:90])}"
                     + (f" <span class='src2'>{_e(s['source'])}</span>" if s.get('source') else "") + "</td></tr>")
        o.append("</tbody></table></section>")

    # §5 Districts (map + table)
    dr = r.get("districts", [])
    if dr:
        o.append("<section><div class='shead'><span class='num'>5</span><h2>Coverage by District</h2>"
                 f"<span class='cnt'>{len(dr)} active</span></div>"
                 "<p class='sf'>Where coverage localised, and how it read. Darker red = more critical.</p><div class='dmap'>")
        for d in dr[:14]:
            o.append(f"<div class='tile {_dcls(d['net'])}'><b>{_e(d['district'])}</b>"
                     f"<span>{d['items']} &middot; {d['net']:+d}</span></div>")
        o.append("</div><table><thead><tr><th>District</th><th class='num'>Items</th><th>Tone</th><th class='num'>Net</th>"
                 "<th>&#9650; Top critical</th><th>&#9660; Top positive</th></tr></thead><tbody>")
        for d in dr[:12]:
            tc = d.get("top_critical"); tp = d.get("top_positive")
            tc_c = f"<span class='dcrit'>{_tel((tc['text'] or '')[:60])}</span>" if tc else "<span class='src2'>—</span>"
            tp_c = f"<span class='dpos'>{_tel((tp['text'] or '')[:60])}</span>" if tp else "<span class='src2'>—</span>"
            o.append(f"<tr><td class='nm'>{_e(d['district'])}</td><td class='num'>{d['items']}</td>"
                     f"<td>{_bar(d['favourable'], d['critical'])}</td>"
                     f"<td class='num net {_net_cls(d['net'])}'>{d['net']:+d}</td>"
                     f"<td>{tc_c}</td><td>{tp_c}</td></tr>")
        o.append("</tbody></table></section>")

    # §5 Media compared
    mp = {m["pillar"]: m for m in r.get("media_compare", [])}
    o.append("<section><div class='shead'><span class='num'>6</span><h2>Newspapers, TV and Websites Compared</h2></div>"
             "<p class='sf'>The three do not move together. Where they diverge is where a response is most worth making.</p><div class='panels'>")
    for p, lab in [("newspaper", "Newspapers"), ("tv", "Television"), ("web", "Online")]:
        m = mp.get(p, {"net": 0, "favourable": 0, "critical": 0})
        o.append(f"<div class='panel'><div class='ph'>{lab}</div><div class='pn {_net_cls(m['net'])}'>{m['net']:+d}</div>"
                 f"<div class='tbar'>{_bar(m['favourable'], m['critical'])}</div>"
                 f"<div class='ks' style='margin-top:8px'>{m['favourable']} for &middot; {m['critical']} against</div></div>")
    o.append("</div>")
    dv = r.get("divergence")
    if dv:
        o.append("<div class='diverge'><div class='dl'>Where they diverge</div>"
                 f"<p><b>{_e(dv['hostile'].title())}</b> is running <b>{dv['gap']} points more critical</b> "
                 f"than {_e(dv['soft'])} today ({dv['hostile_net']:+d} vs {dv['soft_net']:+d}) &mdash; the sharpest gap in the day's coverage.</p></div>")
    o.append("</section>")

    # §6 What Each Side Said
    q = r.get("quotes", {})
    if q.get("government") or q.get("opposition"):
        o.append("<section><div class='shead'><span class='num'>7</span><h2>What Each Side Said</h2></div><div class='qcols'>")
        for side, cls, lab in [("government", "g", "Government"), ("opposition", "o", "Opposition")]:
            o.append(f"<div class='qcol {cls}'><div class='qs'>{lab}</div>")
            for qq in q.get(side, [])[:2]:
                o.append(f"<blockquote>{_tel(qq['text'])}<div class='who'>&mdash; <b>{_e(qq['speaker'])}</b> &middot; {_e(qq['source'])}</div></blockquote>")
            if not q.get(side):
                o.append("<div class='who'>No quotes on record.</div>")
            o.append("</div>")
        o.append("</div>")
        also = [(s, qq) for s, qq in ([('gov', x) for x in q.get('government', [])[2:]] +
                                       [('opp', x) for x in q.get('opposition', [])[2:]])]
        if also:
            o.append("<div class='lab2'>Also on record</div><table><tbody>")
            for s, qq in also[:6]:
                sidelab = "<span class='qtag g'>Govt</span>" if s == 'gov' else "<span class='qtag o'>Opp</span>"
                o.append(f"<tr><td class='nm' style='width:160px'>{_e(qq['speaker'])} {sidelab}</td>"
                         f"<td>{_tel(qq['text'])}</td><td class='num src2'>{_e(qq['source'])}</td></tr>")
            o.append("</tbody></table>")
        o.append("</section>")

    # §7 Figures
    if r.get("figures"):
        o.append("<section><div class='shead'><span class='num'>8</span><h2>Figures Quoted in the Press</h2></div>"
                 "<p class='sf'>Numbers attached to a government scheme or commitment. Contested figures are flagged.</p>")
        figs = r["figures"]
        for grp in ("Money", "People", "Other"):
            gf = [f for f in figs if f.get("group") == grp]
            if not gf:
                continue
            o.append(f"<div class='gl'>{grp}</div><div class='figs'>")
            for f in gf[:8]:
                flag = " <span class='alleg'>&#9888; alleged</span>" if f.get("alleged") else ""
                o.append(f"<div class='fig'><div class='v'>{_e(f['value'])} {_e(f['unit'])}</div>"
                         f"<div class='c'>{_e(f['context'])}{flag}</div></div>")
            o.append("</div>")
        o.append("</section>")

    # §8 Which Outlet
    o.append("<section><div class='shead'><span class='num'>9</span><h2>Which Outlet Said What</h2></div>"
             "<table><thead><tr><th>Outlet</th><th>Medium</th><th class='num'>On govt</th><th>Tone</th><th class='num'>Net</th></tr></thead><tbody>")
    for ot in r.get("outlets", [])[:12]:
        n = ot['net']
        lean = ("<span class='lean n'>critical-leaning</span>" if n <= -30 else
                "<span class='lean p'>govt-leaning</span>" if n >= 30 else "")
        o.append(f"<tr><td class='nm'>{_e(ot['outlet'])} {lean}</td><td>{_e(ot['pillar'])}</td><td class='num'>{ot['on_govt']}</td>"
                 f"<td>{_bar(ot['favourable'], ot['critical'])}</td><td class='num net {_net_cls(ot['net'])}'>{ot['net']:+d}</td></tr>")
    o.append("</tbody></table><p class='sf'>Outlets running consistently critical coverage are the ones worth engaging directly.</p></section>")

    # §9 Annexure
    anx = r.get("annexure", [])
    if anx:
        o.append("<section><div class='shead'><span class='num'>10</span><h2>All Stories, with Links</h2>"
                 f"<span class='cnt'>{len(anx)} cited</span></div><div class='anx'>")
        for i, a in enumerate(anx, 1):
            link = f"<a href='{_e(a['url'])}'>Open &rarr;</a>" if a.get("url") else "<a>—</a>"
            o.append(f"<div class='ax'><span class='r'>{i}</span><div><h4>{_tel((a.get('title') or '')[:90])}</h4>"
                     f"<div class='amt'><span class='med'>{_e(a['pillar'])}</span> &middot; {_e(a['source'])} &middot; {_e(a['lang'])}</div></div>{link}</div>")
        o.append("</div></section>")

    o.append("<div class='colo'><div><b>Telangana &mdash; Information &amp; Public Relations.</b> "
             "Prepared from published media only. Tone reflects how the government was portrayed, not the accuracy of reporting.</div>"
             "<div style='text-align:right'><span class='rb'>Robin</span><br>A product of RIG 360 Media &amp; News Pvt. Ltd.</div></div>")
    o.append("</div></body></html>")
    return "".join(o)


async def render_for(org_id: str, cover_date) -> str:
    async with get_db() as db:
        row = (await db.execute(text("""
            SELECT rp.json FROM briefing.report rp JOIN briefing.runs ru ON ru.id=rp.run_id
             WHERE ru.org_id=CAST(:o AS uuid) AND ru.cover_date=:d
        """), {"o": org_id, "d": cover_date})).fetchone()
        if not row:
            return "<html><body>No report</body></html>"
        return render_html(row.json)


if __name__ == "__main__":
    import asyncio
    import sys
    from datetime import date
    d = sys.argv[1] if len(sys.argv) > 1 else "2026-07-23"
    y, m, dd = map(int, d.split("-"))
    print(asyncio.run(render_for(ORG, date(y, m, dd))))
