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
    # green (favourable) + red (critical) FILL the whole bar, split by ratio —
    # flex-grow guarantees 100% coverage with no neutral gap. All-neutral -> grey.
    f, c = max(int(fav or 0), 0), max(int(crit or 0), 0)
    if f == 0 and c == 0:
        return "<span class='rowbar'><i class='z' style='flex:1'></i></span>"
    return (f"<span class='rowbar'><i class='p' style='flex:{f}'></i>"
            f"<i class='n' style='flex:{c}'></i></span>")


def _tel(s):
    return f"<span class='tel'>{_e(s)}</span>" if any('ఀ' <= c <= '౿' for c in (s or "")) else _e(s)


def _is_tel(s):
    return any('ఀ' <= c <= '౿' for c in (s or ""))


def _teln(text, en=None):
    """Telugu text with an English translation line underneath — shown only when
    the text is actually Telugu and a distinct translation exists."""
    out = _tel(text)
    en = (en or "").strip()
    if en and _is_tel(text) and en != (text or "").strip():
        out += f"<div class='en'>{_e(en)}</div>"
    return out


def _cite(source, url=None):
    """Source name, linked to the article when a URL is available (a citation)."""
    s = _e(source or "")
    return (f"<a href='{_e(url)}' target='_blank' rel='noopener' class='cl2'>{s}</a>"
            if url else s)


def _datauri(b64):
    if not b64:
        return None
    return b64 if str(b64).startswith("data:") else f"data:image/jpeg;base64,{b64}"


def _dcls(net):
    return ("q1" if net > -30 else "q2" if net > -45 else "q3" if net > -60 else "q4" if net > -75 else "q5")


CSS = """
:root{--paper:#fff;--ink:#14181d;--ink2:#333d47;--muted:#4f5a64;--faint:#5b6572;
--hair:#e2e6ea;--hair2:#eef1f4;--navy:#183a63;--navy2:#2b5288;--navy-soft:#eef2f8;--navy-line:#cdd8e8;
--pro:#1f7a46;--pro-soft:#e6f2ea;--anti:#b02a24;--anti-soft:#fbe9e7;--warn:#8a5a12;--warn-soft:#faf1de;
--serif:"Charter","Sitka Text",Cambria,Georgia,serif;--sans:"Inter",ui-sans-serif,"Segoe UI",Arial,sans-serif;
--mono:ui-monospace,Consolas,"DejaVu Sans Mono",monospace;--tel:"Nirmala UI","Noto Sans Telugu",sans-serif;}
*{box-sizing:border-box}body{margin:0;background:#e9edf1;color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.55}
.paper{max-width:1120px;margin:22px auto 60px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 2px rgba(16,24,32,.08),0 10px 34px rgba(16,24,32,.10);font-family:var(--serif)}
.topbar{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:17px 46px;background:linear-gradient(180deg,#202127 0%,#141519 100%);color:#fff;border-bottom:3px solid #d5352b}
.dept{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:#aeb4bd}
.brand{display:flex;flex-direction:column;align-items:flex-end;line-height:.9}
.brand .bn{font-family:var(--serif);font-size:34px;font-weight:700;letter-spacing:.015em;text-transform:uppercase;color:#fff}
.brand .bn .accent{color:#e8443b;margin-left:.16em}
.brand .bs{font-family:var(--sans);font-size:9px;font-weight:600;letter-spacing:.36em;text-transform:uppercase;color:#8d939c;margin-top:11px}
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
.cites{margin-top:9px;font-family:var(--sans);font-size:11px;line-height:1.7;color:var(--muted)}
.cites .cl{font-weight:700;text-transform:uppercase;letter-spacing:.05em;font-size:9.5px;color:var(--navy2);margin-right:7px}
.cites a{color:var(--navy2);text-decoration:none;border-bottom:1px solid var(--hair)}
.cites a:hover{border-bottom-color:var(--navy2)}
.cites .nolink{color:var(--faint,#9a978a)}
.en{font-family:var(--sans);font-size:11.5px;line-height:1.42;color:var(--muted);margin-top:4px}
.cl2{color:var(--navy2);text-decoration:none;border-bottom:1px solid var(--hair)}
.cl2:hover{border-bottom-color:var(--navy2)}
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
.rowbar i.p{background:var(--pro)}.rowbar i.n{background:var(--anti)}.rowbar i.z,.tbar i.z{background:var(--faint)}
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
.tbh .schm{font-family:var(--sans);font-size:11px;color:var(--muted);font-weight:500}
.tbh .net{margin-left:auto;font-family:var(--serif);font-size:16px;font-weight:600}
.cards{display:grid;grid-template-columns:repeat(3,1fr)}
.card{padding:12px 14px;border-right:1px solid var(--hair2)}.card:last-child{border-right:0}
.card .cm{font-family:var(--sans);font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--navy2);margin-bottom:8px}
.thumb{position:relative;height:118px;border-radius:6px;margin-bottom:10px;overflow:hidden;border:1px solid var(--hair);background:#eef2f7}
.thumb img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:1}
.thumb .phlab{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-family:var(--sans);font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);z-index:0}
.thumb.web{background:linear-gradient(135deg,#e7edf4,#d3deeb)}
.thumb.tv{background:linear-gradient(135deg,#1c1f26,#2c3442)}
.thumb.tv .phlab{color:#8b94a3}
.thumb.tv .play{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#fff;font-size:26px;opacity:.95;z-index:2;text-shadow:0 1px 6px rgba(0,0,0,.4)}
.thumb.newspaper{background:repeating-linear-gradient(#faf9f4,#faf9f4 7px,#f1efe4 8px,#f1efe4 9px);border-color:#e5e2d4}
.card.empty{opacity:.75}.card .none{font-family:var(--sans);font-size:11px;color:var(--faint);margin-top:6px}
.card h4{font-family:var(--serif);font-size:13.5px;font-weight:600;margin:0 0 6px;line-height:1.34}
.card .meta{font-family:var(--sans);font-size:10px;color:var(--muted);display:flex;align-items:center;gap:6px}
.dot{width:7px;height:7px;border-radius:50%}.dot.n{background:var(--anti)}.dot.p{background:var(--pro)}.dot.z{background:var(--faint)}
/* district map */
.dmap{display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:6px;margin:14px 0 4px}
.tile{border:1px solid var(--hair);border-radius:6px;padding:9px 11px;min-height:50px;font-family:var(--sans)}
.tile b{font-size:11px;font-weight:700;color:var(--ink);display:block;letter-spacing:.01em}
.tile .tinfo{display:flex;justify-content:space-between;align-items:baseline;margin-top:6px;font-size:10px;color:var(--ink2)}
.tile .tnet{font-family:var(--mono);font-size:10.5px;font-weight:700;font-style:normal}
.tile.q1{background:#dcefe4}.tile.q2{background:#eef4ef}.tile.q3{background:#f7efdf}.tile.q4{background:#f6d7d1}.tile.q5{background:#eab3ab}
.dnotes{display:grid;grid-template-columns:1fr 1fr;gap:12px 26px;margin-top:9px}
.dnote{border-top:1px solid var(--hair2);padding-top:9px}
.dnh{display:flex;align-items:baseline;gap:9px}
.dnh .dnm{font-family:var(--serif);font-size:14px;font-weight:600;color:var(--ink)}
.dnh .dni{font-family:var(--sans);font-size:10px;color:var(--muted)}
.dnh .net{margin-left:auto;font-family:var(--serif);font-size:14px;font-weight:600}
.dnq{font-family:var(--serif);font-size:12.5px;line-height:1.46;color:var(--ink2);margin-top:5px;padding-left:10px;border-left:2px solid var(--hair)}
.dnq.crit{border-left-color:var(--anti)}.dnq.pos{border-left-color:var(--pro)}
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
.big .bb p.stand{font-family:var(--serif);font-size:16.5px;line-height:1.55;color:var(--ink);font-weight:600;margin:0 0 16px}
.bcols{display:grid;grid-template-columns:1fr 288px;gap:26px;align-items:start}
.bmain p.nar{font-family:var(--serif);font-size:14.5px;line-height:1.62;color:var(--ink);margin:0 0 12px}
.brail{border-left:1px solid var(--hair2);padding-left:20px}
.rlab{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin:16px 0 9px}
.brail .rlab:first-child{margin-top:0}
.brail .spread{border-top:0;padding-top:0;margin:0 0 4px;gap:14px}
.brail .bignums{flex-direction:column;gap:11px}
.btwo{display:grid;grid-template-columns:1fr 1fr;gap:26px;margin-top:20px;padding-top:16px;border-top:1px solid var(--hair2)}
.daybars{display:flex;align-items:flex-end;gap:8px;height:60px}
.dbcol{flex:1;display:flex;flex-direction:column;align-items:center;gap:5px}
.dbstack{width:62%;display:flex;flex-direction:column-reverse;border-radius:2px 2px 0 0;overflow:hidden;min-height:2px}
.dbstack i{display:block}
.dw{background:var(--navy)}.dt{background:#6b8cae}.dp{background:#c3cfdd}
.dbl{font-family:var(--sans);font-size:9px;color:var(--muted)}
.dbleg{display:flex;gap:14px;margin-top:9px;font-family:var(--sans);font-size:10px;color:var(--ink2)}
.dbleg i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;vertical-align:middle}
.tline{list-style:none;margin:0;padding:0;border-left:2px solid var(--hair2)}
.tline li{position:relative;padding:0 0 12px 16px}
.tline li:before{content:'';position:absolute;left:-5px;top:3px;width:8px;height:8px;border-radius:50%;background:var(--navy);border:2px solid #fff}
.tline .tw{font-family:var(--sans);font-size:9px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--navy2)}
.tline .tt{font-family:var(--serif);font-size:13px;line-height:1.45;color:var(--ink);margin-top:2px}
.sides{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:8px}
.side{border:1px solid var(--hair);border-radius:8px;padding:14px 16px}
.side .sh{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin-bottom:7px}
.side.gov .sh{color:#2f7d4f}.side.opp .sh{color:#b3402f}
.side .sq{font-family:var(--serif);font-size:14px;line-height:1.5;color:var(--ink);margin:0}
.side .sq.none{color:var(--muted);font-style:italic}
.side .sa{font-family:var(--sans);font-size:11px;color:var(--ink2);margin-top:8px}
.silence{background:#faf4e6;border:1px solid #ecdcb6;border-radius:8px;padding:13px 16px;margin-top:16px;font-family:var(--serif);font-size:13.5px;line-height:1.5;color:var(--ink)}
.angle{margin-top:16px;border-left:3px solid var(--navy-line);padding-left:14px}
.angle p{font-family:var(--serif);font-size:13.5px;line-height:1.5;color:var(--ink2);margin:0}
.gl{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin:14px 0 6px}
.alleg{font-family:var(--sans);font-size:9px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:2px 6px;border-radius:3px;background:var(--warn-soft);color:var(--warn);margin-left:4px}
.diverge{margin-top:16px;background:var(--navy-soft);border:1px solid var(--navy-line);border-radius:8px;padding:14px 18px}
.diverge .dl{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--navy2);margin-bottom:6px}
.diverge p{margin:0;font-family:var(--serif);font-size:14px;line-height:1.5}
.src2{font-family:var(--sans);font-size:10px;color:var(--muted)}
.dcrit{font-family:var(--sans);font-size:11px;color:var(--anti);line-height:1.3}
.dpos{font-family:var(--sans);font-size:11px;color:var(--pro);line-height:1.3}
.qtag{font-family:var(--sans);font-size:8.5px;font-weight:700;text-transform:uppercase;padding:1px 5px;border-radius:3px;vertical-align:middle}
.qtag.g{background:var(--pro-soft);color:var(--pro)}.qtag.o{background:var(--anti-soft);color:var(--anti)}
.lean{font-family:var(--sans);font-size:8.5px;font-weight:700;text-transform:uppercase;padding:1px 6px;border-radius:3px;vertical-align:middle;margin-left:4px}
.lean.n{background:var(--anti-soft);color:var(--anti)}.lean.p{background:var(--pro-soft);color:var(--pro)}
.enddisc{padding:20px 46px 30px;font-family:var(--sans);font-size:10px;color:var(--muted);text-align:center;font-style:italic}
.pagefoot{position:fixed;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;gap:7px;padding:5px 0;background:linear-gradient(180deg,#202127 0%,#141519 100%);border-top:2px solid #d5352b;font-family:var(--sans);font-size:9px;letter-spacing:.05em;color:#aab0b9;z-index:100}
html.screenview .pagefoot{position:static}
.pagefoot .fb{font-weight:800;letter-spacing:.13em;text-transform:uppercase;color:#fff;font-size:9.5px}
.pagefoot .fb .accent{color:#e8443b;margin-left:.13em}
/* ── print / PDF (headless Chromium) — screen == download == print ── */
@page{size:A4;margin:11mm 12mm 20mm}
@media print{
 body{background:#fff}
 .paper{max-width:none;margin:0;border-radius:0;box-shadow:none}
 .topbar,.mast{padding-left:12mm;padding-right:12mm}
 section{padding:16px 12mm 22px;break-inside:auto}
 .kstrip{padding:0 12mm}
 .shead{break-after:avoid}
 .tblock,.card,.big,.qcols,.qcol,.panel,.fig,.ax,.qp,ol.brief li,.to,.tile{break-inside:avoid}
 tr{break-inside:avoid}
 h1,h2,h3,h4{break-after:avoid}
 .cards{break-inside:avoid}
 /* weekly-report blocks — same avoid-split protection, so nothing bleeds into
    the fixed per-page footer's reserved margin */
 .wtrend,.dnote,.side,.spark,.tspark,.wtwo,.btwo{break-inside:avoid}
 .daymark{break-after:avoid;break-inside:avoid}
 a{color:inherit;text-decoration:none}
}
"""


def render_html(r: dict[str, Any]) -> str:
    s = r["strip"]; sent = s["sentiment"]; bp = s["by_pillar"]
    o = [f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body><div class='paper'>"]
    o.append("<div class='topbar'><div class='dept'>Telangana &middot; Information &amp; Public Relations</div>"
             "<div class='brand'><span class='bn'>Robin<span class='accent'>OSINT</span></span>"
             "<span class='bs'>Daily Media Watch</span></div></div>")
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
        f"<div class='tbar'><i class='p' style='flex:{sent['favourable']}'></i>"
        f"<i class='n' style='flex:{sent['critical']}'></i></div>"
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

    # §2 Big Story — full mockup depth
    b = r.get("big_story")
    if b:
        bhead = b.get("headline") or b["label"]
        sp = b.get("spread", {}) or {}
        n_out = (sp.get("web") or 0) + (sp.get("tv") or 0) + (sp.get("newspaper") or 0)
        o.append("<section><div class='shead'><span class='num'>2</span><h2>The Big Story</h2></div><div class='big'>")
        o.append(f"<div class='bh'><div class='lead'>Most-covered story &middot; {n_out} outlets across all "
                 f"three media &middot; net tone {b['net']:+d}</div><h3>{_tel(bhead)}</h3></div><div class='bb'>")
        if b.get("standfirst"):
            o.append(f"<p class='stand'>{_tel(b['standfirst'])}</p>")
        # two columns: narrative | right rail
        o.append("<div class='bcols'><div class='bmain'>")
        for para in b.get("narrative", [])[:4]:
            o.append(f"<p class='nar'>{_tel(para)}</p>")
        o.append("</div><aside class='brail'>")
        o.append("<div class='rlab'>How far it spread</div><div class='spread'>"
                 f"<div class='sp'><b>{sp.get('web',0)}</b><span>web outlets</span></div>"
                 f"<div class='sp'><b>{sp.get('tv',0)}</b><span>TV channels</span></div>"
                 f"<div class='sp'><b>{sp.get('newspaper',0)}</b><span>newspapers</span></div></div>")
        tbp = {t['pillar']: t for t in b.get("tone_by_pillar", [])}
        if tbp:
            o.append("<div class='rlab'>Tone across the outlets that ran it</div><div class='tbp'>")
            for p, lab in [("tv", "Television"), ("web", "Online"), ("newspaper", "Newspapers")]:
                t = tbp.get(p)
                if not t:
                    continue
                o.append(f"<div class='tbprow'><span class='tl'>{lab}</span>{_bar(t['favourable'], t['critical'])}"
                         f"<span class='tn net {_net_cls(t['net'])}'>{t['net']:+d}</span></div>")
            o.append("</div>")
        if b.get("numbers"):
            o.append("<div class='rlab'>Numbers in the coverage</div><div class='bignums'>")
            for n in b["numbers"][:4]:
                o.append(f"<div class='bn'><b>{_e(n['value'])} {_e(n['unit'])}</b><span>{_e(n['context'])}</span></div>")
            o.append("</div>")
        o.append("</aside></div>")  # /bcols
        # coverage-through-the-day chart + timeline, side by side
        hy = b.get("hourly", []) or []
        tot_by_bar = [(h.get('web', 0) + h.get('tv', 0) + h.get('print', 0)) for h in hy]
        if any(tot_by_bar):
            mx = max(tot_by_bar) or 1
            o.append("<div class='btwo'><div class='bhalf'><div class='rlab'>Coverage through the day</div><div class='daybars'>")
            for h in hy:
                tt = h.get('web', 0) + h.get('tv', 0) + h.get('print', 0)
                ht = max(round(50 * tt / mx), 2 if tt else 0)
                o.append(f"<div class='dbcol'><div class='dbstack' style='height:{ht}px'>"
                         + (f"<i class='dw' style='flex:{h['web']}'></i>" if h.get('web') else "")
                         + (f"<i class='dt' style='flex:{h['tv']}'></i>" if h.get('tv') else "")
                         + (f"<i class='dp' style='flex:{h['print']}'></i>" if h.get('print') else "")
                         + f"</div><span class='dbl'>{_e(h['label'])}</span></div>")
            o.append("</div><div class='dbleg'><span><i class='dw'></i>Web</span>"
                     "<span><i class='dt'></i>TV</span><span><i class='dp'></i>Print</span></div></div>")
            if b.get("timeline"):
                o.append("<div class='bhalf'><div class='rlab'>How the story developed</div><ul class='tline'>")
                for t in b.get("timeline", [])[:5]:
                    when = " &middot; ".join(_e(x) for x in [t.get('when', ''), t.get('medium', '')] if x)
                    o.append(f"<li><div class='tw'>{when}</div><div class='tt'>{_tel(t.get('text', ''))}</div></li>")
                o.append("</ul></div>")
            o.append("</div>")  # /btwo
        # what each side said — gov | opp
        gs, op = b.get("gov_side"), b.get("opp_side")
        if gs or op:
            o.append("<div class='rlab'>What each side said &mdash; in the words that were published</div><div class='sides'>")
            for lab, cls, q in [("Government", "gov", gs), ("Opposition", "opp", op)]:
                if q:
                    o.append(f"<div class='side {cls}'><div class='sh'>{lab}</div>"
                             f"<p class='sq'>&ldquo;{_teln(q['text'], q.get('en'))}&rdquo;</p>"
                             f"<div class='sa'><b>{_e(q['speaker'])}</b> &middot; {_cite(q['source'], q.get('url'))}</div></div>")
                else:
                    o.append(f"<div class='side {cls} empty'><div class='sh'>{lab}</div>"
                             f"<p class='sq none'>No direct {lab.lower()} quote appeared in the day's coverage.</p></div>")
            o.append("</div>")
        if b.get("silence"):
            o.append(f"<div class='silence'><b>Where the government was not heard.</b> {_tel(b['silence'])}</div>")
        if b.get("angle"):
            o.append(f"<div class='angle'><div class='rlab'>The angle by medium</div><p>{_tel(b['angle'])}</p></div>")
        # citation line
        bsrcs = b.get("sources") or []
        _bch = []
        for s in bsrcs[:16]:
            nm = _tel(s.get("outlet") or "")
            _bch.append(f"<a href='{_e(s['url'])}' target='_blank' rel='noopener'>{nm}</a>"
                        if s.get("url") else f"<span class='nolink'>{nm}</span>")
        if len(bsrcs) > 16:
            _bch.append(f"<span class='nolink'>+{len(bsrcs)-16} more</span>")
        if _bch:
            o.append(f"<div class='cites'><span class='cl'>Sources</span>{' &middot; '.join(_bch)}</div>")
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
        _plab = {"web": "Online", "tv": "Television", "newspaper": "Newspaper"}
        for pillar, lab in [("web", "Top article"), ("tv", "Top TV clip"), ("newspaper", "Top newspaper")]:
            c = cards.get(pillar)
            if not c:
                o.append(f"<div class='card empty'><div class='cm'>{lab}</div>"
                         f"<div class='thumb {pillar}'><span class='phlab'>No {pillar} item</span></div>"
                         f"<div class='none'>Not covered in this medium.</div></div>")
                continue
            dot = "n" if c["verdict"] == "critical" else "p" if c["verdict"] == "favourable" else "z"
            # image: real scanned cutting (b64) > article/web thumbnail > TV frame.
            # a broken/absent image reveals the labelled placeholder underneath.
            _oerr = "onerror=\"this.remove()\""
            if pillar == "newspaper" and c.get("img"):
                img = f"<img src='{_e(_datauri(c['img']))}' alt=''>"
            elif c.get("thumb"):
                img = f"<img src='{_e(c['thumb'])}' alt='' {_oerr}>"
            elif pillar == "tv" and c.get("video_id"):
                img = (f"<img src='https://img.youtube.com/vi/{_e(c['video_id'])}/hqdefault.jpg' alt='' {_oerr}>"
                       "<span class='play'>&#9654;</span>")
            else:
                img = ""
            play = "<span class='play'>&#9654;</span>" if (pillar == "tv" and img and "play" not in img) else ""
            o.append(f"<div class='card'><div class='cm'>{lab}</div>"
                     f"<div class='thumb {pillar}'><span class='phlab'>{_plab[pillar]}</span>{img}{play}</div>"
                     f"<h4>{_tel((c.get('title') or '')[:90])}</h4>"
                     f"<div class='meta'><span class='dot {dot}'></span>{_e(c['source'])}</div></div>")
        o.append("</div></div>")
    o.append("</section>")

    # §4 Schemes — per-scheme block with 3-media cards (7-day trend deferred)
    sr = r.get("schemes", [])
    if sr:
        o.append("<section><div class='shead'><span class='num'>4</span><h2>How Each Scheme Was Covered</h2>"
                 f"<span class='cnt'>{len(sr)} schemes</span></div>"
                 "<p class='sf'>Each flagship programme &mdash; how much coverage it drew and the most "
                 "representative item from each medium.</p>")
        _splab = {"web": "Online", "tv": "Television", "newspaper": "Newspaper"}
        for s in sr:
            spread = ("web %d" % s.get("web", 0)
                      + (" &middot; TV %d" % s["tv"] if s.get("tv") else "")
                      + (" &middot; paper %d" % s["np"] if s.get("np") else ""))
            o.append(f"<div class='tblock'><div class='tbh'><h3>{_e(s['scheme'])}</h3>"
                     f"<span class='schm'>{s['items']} items &middot; {spread}</span>"
                     f"<span class='net {_net_cls(s['net'])}'>{s['net']:+d}</span></div><div class='cards'>")
            cards = s.get("cards", {})
            for pillar, lab in [("web", "Top article"), ("tv", "Top TV clip"), ("newspaper", "Top newspaper")]:
                c = cards.get(pillar)
                if not c:
                    o.append(f"<div class='card empty'><div class='cm'>{lab}</div>"
                             f"<div class='thumb {pillar}'><span class='phlab'>No {pillar} item</span></div>"
                             f"<div class='none'>Not covered in this medium.</div></div>")
                    continue
                dot = "n" if c["verdict"] == "critical" else "p" if c["verdict"] == "favourable" else "z"
                _oerr = "onerror=\"this.remove()\""
                if pillar == "newspaper" and c.get("img"):
                    img = f"<img src='{_e(_datauri(c['img']))}' alt=''>"
                elif c.get("thumb"):
                    img = f"<img src='{_e(c['thumb'])}' alt='' {_oerr}>"
                elif pillar == "tv" and c.get("video_id"):
                    img = (f"<img src='https://img.youtube.com/vi/{_e(c['video_id'])}/hqdefault.jpg' alt='' {_oerr}>"
                           "<span class='play'>&#9654;</span>")
                else:
                    img = ""
                play = "<span class='play'>&#9654;</span>" if (pillar == "tv" and img and "play" not in img) else ""
                o.append(f"<div class='card'><div class='cm'>{lab}</div>"
                         f"<div class='thumb {pillar}'><span class='phlab'>{_splab[pillar]}</span>{img}{play}</div>"
                         f"<h4>{_tel((c.get('title') or '')[:90])}</h4>"
                         f"<div class='meta'><span class='dot {dot}'></span>{_cite(c['source'], c.get('url'))}</div></div>")
            o.append("</div></div>")
        o.append("</section>")

    # §5 Districts (map + table)
    dr = r.get("districts", [])
    if dr:
        o.append("<section><div class='shead'><span class='num'>5</span><h2>Coverage by District</h2>"
                 f"<span class='cnt'>{len(dr)} active</span></div>"
                 "<p class='sf'>Where the day's coverage localised, and how it read &mdash; "
                 "greener is more favourable, redder more critical.</p>")
        # heatmap: one tile per district, coloured by net tone
        o.append("<div class='dmap'>")
        for d in dr[:14]:
            it = d["items"]
            o.append(f"<div class='tile {_dcls(d['net'])}'><b>{_e(d['district'])}</b>"
                     f"<span class='tinfo'>{it} item{'' if it == 1 else 's'}"
                     f"<em class='tnet'>{d['net']:+d}</em></span></div>")
        o.append("</div>")
        # notable coverage: one representative line per district (critical if the
        # district read negative, else positive) — replaces the cramped 6-col table
        notes = []
        for d in dr[:12]:
            tc, tp = d.get("top_critical"), d.get("top_positive")
            if d["net"] < 0 and tc:
                pick, tone = tc, "crit"
            elif tp:
                pick, tone = tp, "pos"
            elif tc:
                pick, tone = tc, "crit"
            else:
                continue
            if (pick.get("text") or "").strip():
                notes.append((d, pick, tone))
        if notes:
            o.append("<div class='rlab' style='margin-top:20px'>Notable district coverage</div><div class='dnotes'>")
            for d, pick, tone in notes[:8]:
                src = (f"<span class='src2'> &mdash; {_e(pick['source'])}</span>"
                       if pick.get("source") else "")
                o.append(f"<div class='dnote'><div class='dnh'><span class='dnm'>{_e(d['district'])}</span>"
                         f"<span class='dni'>{d['items']} items</span>"
                         f"<span class='net {_net_cls(d['net'])}'>{d['net']:+d}</span></div>"
                         f"<div class='dnq {tone}'>{_tel((pick['text'] or '')[:140])}{src}</div></div>")
            o.append("</div>")
        o.append("</section>")

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
                o.append(f"<blockquote>{_teln(qq['text'], qq.get('en'))}"
                         f"<div class='who'>&mdash; <b>{_e(qq['speaker'])}</b> &middot; {_cite(qq['source'], qq.get('url'))}</div></blockquote>")
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
                         f"<td>{_teln(qq['text'], qq.get('en'))}</td>"
                         f"<td class='num src2'>{_cite(qq['source'], qq.get('url'))}</td></tr>")
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
                cite = (f" <a href='{_e(f['url'])}' target='_blank' rel='noopener' class='cl2'>source &#8599;</a>"
                        if f.get("url") else "")
                o.append(f"<div class='fig'><div class='v'>{_e(f['value'])} {_e(f['unit'])}</div>"
                         f"<div class='c'>{_e(f['context'])}{flag}{cite}</div></div>")
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

    o.append("<div class='enddisc'>Prepared from published media only. Tone reflects how the "
             "government was portrayed, not the accuracy of reporting.</div>")
    o.append("</div>")  # /paper
    # fixed page-footer — repeats at the bottom of every PDF page
    o.append("<div class='pagefoot'><span class='fb'>Robin<span class='accent'>OSINT</span></span>"
             "<span class='ft'>&middot; A product of RIG 360 Media &amp; News Pvt. Ltd.</span></div>")
    # Screen-only marker (stripped for the PDF via pdf.py) so the footer sits once
    # at the end on screen instead of floating; in the PDF it stays fixed per page.
    o.append("<script>if(!window.__ISPDF__){document.documentElement.classList.add('screenview');}</script>")
    o.append("</body></html>")
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
