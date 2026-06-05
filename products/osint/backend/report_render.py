"""Render a built report (report_builder.build_report) to HTML and PDF.

HTML mirrors the approved sample design (dark, gold-accented intelligence brief).
PDF via WeasyPrint. Kept presentational only — no data logic here.
"""
from __future__ import annotations

import html
from typing import Any

_SEV = {
    "CRITICAL": ("crit", "🔴 CRITICAL"), "HIGH": ("high", "🟠 HIGH"),
    "MODERATE": ("mod", "🟡 MODERATE"), "LOW": ("low", "🟢 LOW"),
}
_TONE_COLOR = {"supportive": "var(--pos)", "hostile": "var(--neg)", "neutral": "var(--neu)"}

_CSS = """
:root{--ink:#ece7da;--muted:#a59f8e;--faint:#7b7565;--line:#26242f;--panel:#121119;--panel2:#16151f;
--gold:#d8b45a;--gold-d:#9c8136;--pos:#46c98a;--neu:#6b7691;--neg:#ef5d5d;--hi:#f0913e;
--serif:Georgia,'Times New Roman',serif;--mono:'DejaVu Sans Mono',monospace;}
*{box-sizing:border-box}
@page{size:A4;margin:14mm 12mm;background:#070610;}
body{margin:0;background:#070610;color:var(--ink);font-family:'Helvetica Neue',Arial,sans-serif;font-size:11.5px;line-height:1.62;}
.eyebrow{font-family:var(--mono);font-size:8px;letter-spacing:.22em;color:var(--gold);text-transform:uppercase;}
h1{font-family:var(--serif);font-weight:600;font-size:25px;line-height:1.1;margin:6px 0 3px;}
h2{font-family:var(--serif);font-weight:600;font-size:18.5px;margin:34px 0 9px;border-left:3px solid var(--gold);padding-left:12px;page-break-after:avoid;}
h2 .ix{font-family:var(--mono);font-size:10px;color:var(--gold-d);letter-spacing:.1em;margin-right:7px;}
.sub{color:var(--muted);font-size:10.5px;}
.lede{color:var(--muted);}
.masthead{display:flex;justify-content:space-between;align-items:flex-end;gap:18px;border-bottom:2px solid var(--gold-d);padding-bottom:12px;}
.stamp{font-family:var(--mono);font-size:8.5px;color:var(--faint);text-align:right;line-height:1.7;}
.kpis{display:flex;gap:12px;margin:22px 0 4px;}
.kpi{flex:1;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:13px 15px;}
.kpi .v{font-size:18px;font-weight:600;font-family:var(--serif);}
.kpi .l{font-family:var(--mono);font-size:8px;letter-spacing:.1em;color:var(--faint);text-transform:uppercase;}
.kpi .d{font-size:9.5px;margin-top:2px;color:var(--muted);}
.up{color:var(--pos)}.down{color:var(--neg)}.flat{color:var(--neu)}
ul.exec{list-style:none;padding:0;margin:7px 0 0;}
ul.exec li{position:relative;padding:9px 0 9px 22px;border-bottom:1px solid var(--line);}
ul.exec li:before{content:'▸';position:absolute;left:2px;color:var(--gold);}
table.heat{width:100%;border-collapse:collapse;margin-top:8px;font-size:10.5px;}
table.heat th{font-family:var(--mono);font-size:8px;letter-spacing:.1em;color:var(--faint);text-transform:uppercase;text-align:left;padding:5px 7px;border-bottom:1px solid var(--line);}
table.heat td{padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top;}
.sev{display:inline-block;font-family:var(--mono);font-size:8.5px;font-weight:700;padding:2px 8px;border-radius:18px;}
.sev.crit{background:rgba(239,93,93,.16);color:#ff7a7a;border:1px solid rgba(239,93,93,.5)}
.sev.high{background:rgba(240,145,62,.15);color:var(--hi);border:1px solid rgba(240,145,62,.5)}
.sev.mod{background:rgba(216,180,90,.13);color:var(--gold);border:1px solid rgba(216,180,90,.4)}
.sev.low{background:rgba(70,201,138,.12);color:var(--pos);border:1px solid rgba(70,201,138,.35)}
.dev{border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin:14px 0;background:var(--panel);page-break-inside:avoid;}
.dev .theme{font-family:var(--mono);font-size:8.5px;letter-spacing:.13em;color:var(--gold);text-transform:uppercase;}
.dev h3{font-family:var(--serif);font-size:14px;margin:4px 0 5px;font-weight:600;}
.bars div{display:flex;align-items:center;gap:9px;padding:4px 0;}
.bars .nm{width:140px;font-size:10.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.bars .tr{flex:1;height:7px;background:var(--panel2);border-radius:4px;overflow:hidden;}
.bars .tr i{display:block;height:100%;background:linear-gradient(90deg,var(--gold-d),var(--gold));}
.bars .vv{width:80px;text-align:right;font-family:var(--mono);font-size:10px;}
.senti{display:flex;height:13px;border-radius:6px;overflow:hidden;margin:7px 0 3px;}
.stories{display:flex;flex-wrap:wrap;gap:16px;margin-top:14px;}
.story{width:calc(50% - 8px);border:1px solid var(--line);border-radius:9px;overflow:hidden;background:var(--panel);page-break-inside:avoid;}
.story .img{height:185px;background:#15141d;background-size:cover;background-position:center;border-bottom:1px solid var(--line);}
.story .bd{padding:13px 15px;}
.story .ti{font-size:13.5px;font-weight:600;line-height:1.32;}
.story .en{font-size:11px;color:var(--muted);margin-top:4px;}
.story .mt{font-family:var(--mono);font-size:9px;color:var(--faint);margin-top:9px;}
.dot{display:inline-block;width:6px;height:6px;border-radius:6px;margin-right:4px;}
.quote{border-left:2px solid var(--gold-d);padding:3px 0 3px 11px;margin:8px 0;}
.quote p{margin:0;font-family:var(--serif);font-style:italic;font-size:11.5px;}
.quote .en{font-style:normal;font-size:9.5px;color:var(--muted);margin-top:1px;}
.quote .who{font-family:var(--mono);font-size:8.5px;color:var(--faint);margin-top:2px;}
.figs{display:flex;flex-wrap:wrap;gap:8px;}
.fig{width:48%;background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:9px 11px;}
.fig .v{font-family:var(--serif);font-size:15px;font-weight:600;color:var(--gold);}
.fig .c{font-size:9.5px;color:var(--muted);}
ol.act{counter-reset:a;list-style:none;padding:0;}
ol.act li{counter-increment:a;position:relative;padding:8px 0 8px 32px;border-bottom:1px solid var(--line);}
ol.act li:before{content:counter(a);position:absolute;left:0;top:7px;width:22px;height:22px;border-radius:50%;background:rgba(216,180,90,.14);border:1px solid var(--gold-d);color:var(--gold);font-family:var(--mono);font-size:11px;text-align:center;line-height:21px;}
.twocol{display:flex;gap:18px;}.twocol>div{flex:1;}
.chip{display:inline-block;font-family:var(--mono);font-size:7.5px;padding:2px 6px;border-radius:4px;border:1px solid var(--line);color:var(--muted);margin-right:4px;}
.footer{margin-top:22px;border-top:1px solid var(--line);padding-top:9px;font-family:var(--mono);font-size:8px;color:var(--faint);display:flex;justify-content:space-between;}
"""


def _e(x: Any) -> str:
    return html.escape(str(x if x is not None else ""))


def render_html(r: dict[str, Any]) -> str:
    n = r.get("narrative", {})
    k = r["kpis"]
    delta = k["delta_pct"]
    out: list[str] = [f"<!doctype html><html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>"]

    # masthead
    out.append(
        f"<div class='masthead'><div><div class='eyebrow'>RIG OSINT · DAILY STATE INTELLIGENCE BRIEF</div>"
        f"<h1>{_e(r['state'])} — Situation Snapshot</h1>"
        f"<div class='sub'>Prepared for <b style='color:var(--ink)'>{_e(r['principal'])} desk</b> · 24-hour window</div></div>"
        f"<div class='stamp'>{_e(r['generated_at'])[:16]} IST<br>WINDOW 24H · vs PRIOR 24H<br>"
        f"CONFIDENCE · {_e(r['confidence'])} ({k['n24']} stories)<br>CLASSIFICATION · INTERNAL</div></div>")

    # kpis
    arrow = f"<span class='{'up' if delta>0 else 'down' if delta<0 else 'flat'}'>{'▲' if delta>0 else '▼' if delta<0 else '•'} {abs(delta)}%</span>"
    out.append("<div class='kpis'>"
        f"<div class='kpi'><div class='l'>Stories tracked</div><div class='v'>{k['n24']}</div><div class='d'>{arrow} vs prior 24h</div></div>"
        f"<div class='kpi'><div class='l'>Net sentiment</div><div class='v' style='color:var(--pos)'>{k['net_sentiment']:+d}%</div><div class='d'>{k['pos']} supportive · {k['neg']} critical</div></div>"
        f"<div class='kpi'><div class='l'>Districts active</div><div class='v'>{k['districts_active']}</div><div class='d'>{_e(r['districts'][0]['name']) if r['districts'] else '—'} leads</div></div>"
        f"<div class='kpi'><div class='l'>Adverse share</div><div class='v' style='color:var(--hi)'>{k['adverse_pct']}%</div><div class='d'>by domain, see heatmap</div></div></div>")

    # A. exec summary
    out.append("<h2><span class='ix'>A</span>Executive Summary</h2><div class='sub'>What changed in the last 24 hours, and why it matters.</div><ul class='exec'>")
    out += [f"<li>{_e(b)}</li>" for b in n.get("exec_summary", [])]
    out.append("</ul>")

    # B. risk heatmap
    out.append("<h2><span class='ix'>B</span>Risk Heatmap</h2><div class='sub'>Severity = volume × adverse share × 24h velocity, by domain.</div>"
               "<table class='heat'><tr><th>Domain</th><th>Severity</th><th>Read</th><th style='text-align:right'>24h · adverse</th></tr>")
    for d in r["domains"]:
        cls, lbl = _SEV[d["severity"]]
        read = f"{d['adverse_pct']}% adverse · {d['delta_pct']:+d}% vs prior"
        out.append(f"<tr><td><b>{_e(d['domain'])}</b></td><td><span class='sev {cls}'>{lbl}</span></td>"
                   f"<td class='lede'>{read}</td><td style='text-align:right;font-family:var(--mono)'>{d['n24']} · {d['neg']}</td></tr>")
    out.append("</table>")

    # C. developments
    out.append("<h2><span class='ix'>C</span>Key Developments</h2><div class='sub'>Clustered by theme, rewritten and contextualised.</div>")
    for dv in n.get("developments", []):
        out.append(f"<div class='dev'><div class='theme'>{_e(dv.get('theme',''))}</div>"
                   f"<h3>{_e(dv.get('headline',''))}</h3><div class='lede'>{_e(dv.get('body',''))}</div></div>")

    # D. geographic
    out.append("<h2><span class='ix'>D</span>Geographic Intelligence</h2><div class='sub'>District-level coverage and movers.</div><div class='bars'>")
    maxd = max((d["n24"] for d in r["districts"]), default=1) or 1
    for d in r["districts"][:8]:
        dl = d["delta_pct"]
        da = f"<span class='{'up' if dl>0 else 'down' if dl<0 else 'flat'}'>{('▲'+str(dl)+'%') if dl>0 else ('▼'+str(abs(dl))+'%') if dl<0 else '·'}</span>"
        out.append(f"<div><span class='nm'>{_e(d['name'])}</span><span class='tr'><i style='width:{round(100*d['n24']/maxd)}%'></i></span><span class='vv'>{d['n24']} {da}</span></div>")
    out.append("</div>")
    if n.get("hotspot_read"):
        out.append(f"<div class='sub' style='margin-top:8px'><b>Hotspot read:</b> {_e(n['hotspot_read'])}</div>")

    # E. sentiment
    s3 = r["sentiment"]; tot = (s3["pos"]+s3["neu"]+s3["neg"]) or 1
    out.append("<h2><span class='ix'>E</span>Sentiment &amp; Narrative</h2><div class='senti'>"
               f"<span style='width:{100*s3['pos']//tot}%;background:var(--pos)'></span>"
               f"<span style='width:{100*s3['neu']//tot}%;background:var(--neu)'></span>"
               f"<span style='width:{100*s3['neg']//tot}%;background:var(--neg)'></span></div>"
               f"<div class='sub'>{s3['pos']} supportive · {s3['neu']} neutral · {s3['neg']} critical · net {s3['net_pct']:+d}%</div>")
    if n.get("sentiment_narrative"):
        out.append(f"<div class='lede' style='margin-top:6px'>{_e(n['sentiment_narrative'])}</div>")

    # F. early warning
    if r["early_warning"]:
        out.append("<h2><span class='ix'>F</span>Early-Warning Signals</h2><div class='sub'>Small now, accelerating — watch before they escalate.</div>"
                   "<table class='heat'><tr><th>Signal</th><th>Now ← prior</th><th>Growth</th></tr>")
        for e in r["early_warning"]:
            out.append(f"<tr><td><b>{_e(e['label'])}</b> <span class='chip'>{_e(e['kind'])}</span></td>"
                       f"<td style='font-family:var(--mono)'>{e['now']} ← {e['prior']}</td><td class='up' style='font-family:var(--mono)'>+{e['growth']}%</td></tr>")
        out.append("</table>")

    # G. stakeholders
    out.append("<h2><span class='ix'>G</span>Stakeholder Impact</h2><div class='twocol'>"
               "<div><div class='eyebrow' style='color:var(--muted)'>WHO IS AFFECTED</div><ul class='exec'>")
    out += [f"<li>{_e(a['group'])} <span class='chip'>{a['n']} stories</span></li>" for a in r["stakeholders"]["affected"][:5]] or ["<li class='lede'>—</li>"]
    out.append("</ul></div><div><div class='eyebrow' style='color:var(--muted)'>WHO IS DRIVING IT</div><ul class='exec'>")
    out += [f"<li>{_e(d['name'])} <span class='chip'>{_e(d['type'])} · {d['n']}</span></li>" for d in r["stakeholders"]["drivers"][:5]]
    out.append("</ul></div></div>")

    # H. actions
    out.append("<h2><span class='ix'>H</span>Recommended Actions</h2><div class='sub'>Practical moves the day's signals support, prioritised.</div><ol class='act'>")
    out += [f"<li>{_e(a)}</li>" for a in n.get("actions", [])]
    out.append("</ol>")

    # top stories
    out.append("<h2><span class='ix'>+</span>Top Stories</h2><div class='stories'>")
    for st in r["top_stories"][:4]:
        img = f"background-image:url('{_e(st['thumb'])}')" if st.get("thumb") else ""
        en = f"<div class='en'>EN · {_e(st['title_en'])}</div>" if st.get("title_en") else ""
        out.append(f"<div class='story'><div class='img' style=\"{img}\"></div><div class='bd'>"
                   f"<div class='ti'>{_e(st['title'])}</div>{en}"
                   f"<div class='mt'><span class='dot' style='background:{_TONE_COLOR.get(st['tone'])}'></span>"
                   f"{_e(st['source'])} · Tier {_e(st['tier'])}"
                   f"{(' · '+str(st['breadth'])+' outlets') if st.get('breadth',1) > 1 else ''}"
                   f"{(' · '+_e(st['geo'])) if st.get('geo') else ''}</div></div></div>")
    out.append("</div>")

    # quotes + figures
    out.append("<div class='twocol' style='margin-top:12px'><div><h2 style='margin-top:4px'><span class='ix'>+</span>In Their Words</h2>")
    for q in r["quotes"][:3]:
        en = f"<div class='en'>EN · {_e(q['q_en'])}</div>" if q.get("q_en") else ""
        out.append(f"<div class='quote'><p>“{_e(q['q'])}”</p>{en}<div class='who'>— {_e(q['who'])} · {_e(q['src'])}</div></div>")
    out.append("</div><div><h2 style='margin-top:4px'><span class='ix'>+</span>Figures Watch</h2><div class='figs'>")
    for f in r["figures"][:4]:
        out.append(f"<div class='fig'><div class='v'>{_e(f['value'])}</div><div class='c'>{_e(f['context'])}</div></div>")
    out.append("</div></div></div>")

    # I. source intel
    out.append("<h2><span class='ix'>I</span>Source Intelligence</h2><div class='sub'>Reliability, spread and lean behind today's picture.</div>"
               "<table class='heat'><tr><th>Tier</th><th>Stories</th><th>Outlets</th></tr>")
    tlabel = {1: "Tier 1 · established", 2: "Tier 2 · regional", 3: "Tier 3 · long-tail"}
    for t in r["source_intel"]["tiers"]:
        out.append(f"<tr><td><b>{_e(tlabel.get(t['tier'], 'Tier '+str(t['tier'])))}</b></td><td>{t['stories']}</td><td>{t['outlets']}</td></tr>")
    out.append("</table><div class='sub' style='margin-top:7px'><b>Top outlets:</b> "
               + ", ".join(f"{_e(o['name'])} (T{o['tier']}, health {o['health']})" for o in r["source_intel"]["top_outlets"][:5]) + ".</div>")
    xv = r["source_intel"].get("cross")
    if xv:
        out.append(f"<div class='sub' style='margin-top:5px'><b>Cross-verification:</b> {xv['corroborated']} storylines corroborated "
                   f"across 3+ outlets; {xv['single_source']} single-source (treat with caution).</div>")

    out.append(f"<div class='footer'><span>RIG OSINT · generated {_e(r['generated_at'])[:16]} IST · auto-refreshed daily · narrative:{n.get('_source','?')}</span>"
               f"<span>{_e(r['state'])} desk</span></div>")
    out.append("</body></html>")
    return "".join(out)


def render_pdf(r: dict[str, Any]) -> bytes:
    from weasyprint import HTML  # lazy import — heavy
    return HTML(string=render_html(r)).write_pdf()
