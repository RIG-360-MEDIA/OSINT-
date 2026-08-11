"""Render the weekly (multi-day) report JSON (weekly_assemble.assemble_weekly)
into the same designed HTML system as the daily briefing — same masthead, same
CSS, same helpers (_e/_bar/_tel/_teln/_cite/_datauri) — but with the sections a
single day can't show: a day-by-day sentiment trend, and REAL per-day tone
trends for schemes and outlets (the daily report defers these; here there is
genuine dated history to draw from).

Usage (osint-backend): python -m briefing.weekly_render <start> <end> -> prints HTML.
"""
from __future__ import annotations

from typing import Any

from briefing.render import CSS, _bar, _cite, _datauri, _dcls, _e, _net_cls, _teln, _tel


def _day_label(iso: str) -> str:
    import datetime
    d = datetime.date.fromisoformat(iso)
    return d.strftime("%a %d").upper()


def _valunit(value: str, unit: str) -> str:
    """Join a figure's value and unit without doubling the unit — the extractor
    sometimes stores value='56%' unit='percent', which rendered as '56% percent'."""
    v, u = (value or "").strip(), (unit or "").strip()
    if u.lower() in ("percent", "per cent", "%") and "%" in v:
        return v
    if u.lower() in ("count", "number", "numbers"):
        return v
    if u and v.lower().endswith(u.lower()):
        return v
    return f"{v} {u}".strip()


def _spark(daily: list[dict], cls: str = "") -> str:
    """Compact day-by-day tone trend: one bar per day, height = volume,
    colour = that day's net tone. This is the feature the daily report defers
    ('empty at launch') — now real because dated history actually exists."""
    if not daily:
        return ""
    mx = max((d.get("items") or 0) for d in daily) or 1
    bars = []
    for d in daily:
        items = d.get("items") or 0
        net = d.get("net") or 0
        lab = _day_label(d["date"])
        h = max(round(28 * items / mx), 2) if items else 2
        c = "sp-pos" if net > 5 else "sp-neg" if net < -5 else "sp-z"
        title = f"{_e(lab)}: {items} items, {net:+d}"
        bars.append(
            f"<div class='sbar' title='{title}'>"
            f"<i class='{c}' style='height:{h}px'></i><span>{_e(lab[:2])}</span></div>")
    return f"<div class='spark {cls}'>{''.join(bars)}</div>"


def render_weekly_html(r: dict[str, Any]) -> str:
    p = r["period"]
    days = p["days"]
    s = r["strip"]; sent = s["sentiment"]; bp = s["by_pillar"]
    fc = (sent["favourable"] + sent["critical"]) or 1
    tot = s["total"] or 1

    o = ["<!doctype html><html><head><meta charset='utf-8'><style>", CSS, WEEKLY_CSS,
         "</style></head><body><div class='paper'>"]

    o.append("<div class='topbar'><div class='dept'>Telangana &middot; Information &amp; Public Relations</div>"
             "<div class='brand'><span class='bn'>Robin<span class='accent'>OSINT</span></span>"
             "<span class='bs'>Weekly Media Watch</span></div></div>")
    o.append("<div class='mast'><h1>Weekly Media Briefing</h1>"
             f"<div class='dek'><span>Covering <b>{_e(p['start'])}</b> &ndash; <b>{_e(p['end'])}</b> "
             f"&middot; <b>{len(days)}</b> day{'s' if len(days) != 1 else ''} of judged coverage</span>"
             "<span>Web + Television + Newspapers</span></div></div>")

    # KPI strip + day-by-day sentiment trend (the new, only-possible-weekly view).
    # When the prior week has judged runs, Total Stories and Sentiment carry a
    # week-over-week delta chip.
    prev = r.get("previous")

    def _delta_chip(cur: int, prv: int, suffix: str = "") -> str:
        d = cur - prv
        if d == 0:
            return "<span class='dchip z'>= last wk</span>"
        cls = "u" if d > 0 else "d"
        return f"<span class='dchip {cls}'>{d:+d}{suffix} vs last wk</span>"

    outrows = "".join(
        f"<div class='to'><b>{_e(v['outlet'])}</b><span>{p2.upper()}</span><i>{v['n']}</i></div>"
        for p2, v in s.get("top_outlet_by_medium", {}).items())
    vol_chip = _delta_chip(s["total"], prev["total"]) if prev else ""
    net_chip = _delta_chip(sent["net"], prev["net"], " pts") if prev else ""
    o.append(
        "<div class='kstrip'>"
        f"<div class='kt'><div class='kl'>Total Stories</div><div class='kv'>{s['total']:,}{vol_chip}</div>"
        f"<div class='mbar'><i class='a' style='width:{round(100*bp['web']/tot)}%'></i>"
        f"<i class='b' style='width:{round(100*bp['newspaper']/tot)}%'></i>"
        f"<i class='c' style='width:{round(100*bp['tv']/tot)}%'></i></div>"
        f"<div class='ks'>Web <b>{bp['web']}</b> &middot; Papers <b>{bp['newspaper']}</b> &middot; "
        f"TV <b>{bp['tv']}</b> &middot; from {s.get('scanned', s['total']):,} scanned</div></div>"
        f"<div class='kt'><div class='kl'>Biggest Subject</div><div class='kv'>{_e(s['biggest_subject']['topic'] or '—')}</div>"
        f"<div class='ks'>{s['biggest_subject']['items']} of {s['total']} government stories this week</div></div>"
        f"<div class='kt'><div class='kl'>Sentiment (week)</div><div class='kv {_net_cls(sent['net'])}'>{sent['net']:+d}{net_chip}</div>"
        f"<div class='tbar'><i class='p' style='flex:{sent['favourable']}'></i>"
        f"<i class='n' style='flex:{sent['critical']}'></i></div>"
        f"<div class='ks'>{sent['favourable']} for &middot; {sent['critical']} against &middot; {sent['neutral']} no side</div></div>"
        f"<div class='kt'><div class='kl'>Top Outlet, each medium</div>{outrows}</div></div>")

    # The Week at a Glance — LLM executive paragraph + week-over-week movers
    glance = (r.get("glance") or "").strip()
    movers = r.get("movers") or []
    if glance or movers:
        o.append("<div class='glance'>")
        if glance:
            o.append("<div class='rlab'>The week at a glance</div>"
                     f"<p>{_e(glance)}</p>")
        if movers:
            chips = "".join(
                f"<span class='mchip {'u' if m['swing'] > 0 else 'd'}'>"
                f"{_e(m['topic'])} <i>{m['prev_net']:+d} &rarr; {m['net']:+d}</i></span>"
                for m in movers)
            o.append(f"<div class='movers'><span class='ml'>Biggest tone swings vs last week</span>{chips}</div>")
        if prev:
            o.append(f"<div class='glance-note'>Compared against {_e(prev['start'])} &ndash; "
                     f"{_e(prev['end'])} ({prev['days']} judged days, {prev['total']} stories, "
                     f"net {prev['net']:+d}).</div>")
        o.append("</div>")

    # ═ Analytics dashboard — "The Week in Charts" (client request 2026-08-10).
    # Server-side inline SVG (weekly_charts.py) so HTML and PDF render alike.
    # Supersedes the old one-line sentiment sparkline that used to sit here.
    from briefing.weekly_charts import build_week_charts
    ch = build_week_charts(r)
    if any(ch.values()):
        o.append("<section class='chartsec'><div class='shead'><h2>The Week in Charts</h2>"
                 "<span class='cnt'>analytics</span></div>"
                 "<p class='sf'>The week's coverage as data: how sentiment flowed day by day, "
                 "where the volume sat, and who drove the tone.</p>"
                 "<div class='chleg'><span class='k'><i style='background:#1f7a46'></i>Favourable</span>"
                 "<span class='k'><i style='background:#b02a24'></i>Critical</span>"
                 "<span class='k'><i style='background:#2b5288'></i>Story volume</span></div>")
        if ch["daily_flow"]:
            o.append(f"<div class='chbox'><h3>Favourable vs critical, day by day</h3>{ch['daily_flow']}</div>")
        if ch["sentiment_split"]:
            o.append(f"<div class='chbox'><h3>The week's sentiment split</h3>{ch['sentiment_split']}</div>")
        if ch["topics"]:
            o.append(f"<div class='chbox'><h3>Each subject: how much coverage, and how it leaned</h3>{ch['topics']}</div>")
        row = ""
        if ch["media"]:
            row += f"<div class='chbox half'><h3>How each medium leaned</h3>{ch['media']}</div>"
        if ch["movers"]:
            row += f"<div class='chbox half'><h3>Biggest swings vs last week</h3>{ch['movers']}</div>"
        if row:
            o.append(f"<div class='chrow'>{row}</div>")
        if ch["outlets"]:
            o.append(f"<div class='chbox'><h3>Which outlets drove the tone</h3>{ch['outlets']}</div>")
        o.append("</section>")

    # §1 Week in Brief — grouped by day, most recent first. Each story leads
    # with an LLM headline + 3-4 sentence paragraph (same depth as the daily
    # report's §1) when available; falls back to the raw evidence sentence
    # only if the enrichment call failed for that item.
    wb = r.get("week_brief", [])
    if wb:
        o.append("<section><div class='shead'><span class='num'>1</span><h2>The Week in Brief</h2>"
                 f"<span class='cnt'>{len(wb)} stories</span></div>"
                 "<p class='sf'>The strongest government stories of the week, day by day, most recent first.</p><ol class='brief'>")
        last_date = None
        for b in wb:
            if b["date"] != last_date:
                o.append(f"<div class='daymark'>{_e(_day_label(b['date']))} &middot; {_e(b['date'])}</div>")
                last_date = b["date"]
            net_lab = "critical" if b["verdict"] == "critical" else "favourable" if b["verdict"] == "favourable" else "mixed"
            vcls = "n" if b["verdict"] == "critical" else "p" if b["verdict"] == "favourable" else "g"
            head = b.get("headline") or b.get("title") or ""
            body = b.get("paragraph") or b.get("evidence") or ""
            link = f"<div class='cites'><span class='cl'>Source</span>{_cite(b['source'], b.get('url'))}</div>" if b.get("source") else ""
            o.append(f"<li><div><h3>{_tel(head[:110])}</h3>"
                     + (f"<p class='ev'>{_tel(body)}</p>" if body else "")
                     + "<div class='tags'>"
                     + (f"<span class='tag g'>{_e(b['topic'])}</span>" if b.get("topic") else "")
                     + (f"<span class='tag g'>{_e(b['department'])}</span>"
                        if b.get("department")
                        and (b.get("department") or "").lower() != (b.get("topic") or "").lower() else "")
                     + f"<span class='tag {vcls}'>{net_lab}</span></div>" + link + "</div></li>")
        o.append("</ol></section>")

    # §2 The Week's Big Story — the full daily-report-depth package (standfirst,
    # multi-paragraph narrative, timeline, silence/angle, gov-vs-opp quotes)
    # PLUS three media cards with real images so the week's lead story is
    # illustrated from web, TV and newspaper all at once.
    b = r.get("big_story")
    if b:
        o.append("<section><div class='shead'><span class='num'>2</span><h2>The Week's Big Story</h2></div><div class='big'>")
        sp = b.get("spread", {})
        n_out = (sp.get("web") or 0) + (sp.get("tv") or 0) + (sp.get("newspaper") or 0)
        bhead = b.get("headline") or b.get("label", "")
        o.append(f"<div class='bh'><div class='lead'>The subject that dominated the week &middot; "
                 f"{n_out} stories across all three media &middot; net tone {b['net']:+d}</div>"
                 f"<h3>{_tel(bhead)}</h3></div><div class='bb'>")
        if b.get("standfirst"):
            o.append(f"<p class='stand'>{_tel(b['standfirst'])}</p>")
        for para in (b.get("narrative") or [])[:6]:
            o.append(f"<p class='nar'>{_tel(para)}</p>")
        if not b.get("narrative") and b.get("evidence"):
            for ev in b["evidence"][:6]:
                o.append(f"<p class='nar'>{_tel(ev.get('text', ''))}</p>")

        # three media cards — the week's single best web/TV/newspaper item on
        # this topic, with real images ("images from all three sources")
        cards = b.get("cards") or {}
        if cards:
            o.append("<div class='rlab'>The story, in each medium</div><div class='cards big-cards'>")
            _splab = {"web": "Online", "tv": "Television", "newspaper": "Newspaper"}
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
            o.append("</div>")

        o.append("<div class='spread'>"
                 f"<div class='sp'><b>{sp.get('web',0)}</b><span>web stories</span></div>"
                 f"<div class='sp'><b>{sp.get('tv',0)}</b><span>TV segments</span></div>"
                 f"<div class='sp'><b>{sp.get('newspaper',0)}</b><span>newspaper items</span></div>"
                 f"<div class='sp'><b>{b['size']}</b><span>total, this week</span></div></div>")

        if b.get("numbers"):
            o.append("<div class='rlab'>Numbers in the coverage</div><div class='bignums'>")
            for n in b["numbers"][:4]:
                o.append(f"<div class='bn'><b>{_e(_valunit(n['value'], n['unit']))}</b><span>{_e(n['context'])}</span></div>")
            o.append("</div>")

        if b.get("daily"):
            o.append("<div class='rlab'>How it moved through the week</div>" + _spark(b["daily"], "big"))
        if b.get("timeline"):
            o.append("<div class='rlab'>How the story developed, day by day</div><ul class='tline'>")
            for t in b.get("timeline", [])[:8]:
                when = " &middot; ".join(_e(x) for x in [t.get('when', ''), t.get('medium', '')] if x)
                o.append(f"<li><div class='tw'>{when}</div><div class='tt'>{_tel(t.get('text', ''))}</div></li>")
            o.append("</ul>")

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
                             f"<p class='sq none'>No direct {lab.lower()} quote appeared in the week's coverage.</p></div>")
            o.append("</div>")
        if b.get("silence"):
            o.append(f"<div class='silence'><b>Where the government was not heard.</b> {_tel(b['silence'])}</div>")
        if b.get("angle"):
            o.append(f"<div class='angle'><div class='rlab'>The angle by medium</div><p>{_tel(b['angle'])}</p></div>")
        o.append("</div></div></section>")

    # §3 Coverage by Topic (week) — each with a daily tone sparkline
    tc = r.get("topic_cards", {})
    topic_order = [t["topic"] for t in r.get("topics", [])]
    tnet = {t["topic"]: t for t in r.get("topics", [])}
    if tc:
        o.append("<section><div class='shead'><span class='num'>3</span><h2>Coverage by Topic</h2>"
                 f"<span class='cnt'>{len(tc)} topics</span></div>"
                 "<p class='sf'>For each subject, the most representative item from each medium across the week, "
                 "with how its tone moved day by day.</p>")
        _splab = {"web": "Online", "tv": "Television", "newspaper": "Newspaper"}
        for tname in topic_order:
            cards = tc.get(tname)
            if not cards:
                continue
            tr = tnet.get(tname, {})
            o.append(f"<div class='tblock'><div class='tbh'><h3>{_e(tname)}</h3>"
                     f"<span class='schm'>{tr.get('items',0)} items this week</span>"
                     f"<span class='net {_net_cls(tr.get('net',0))}'>{tr.get('net',0):+d}</span></div>")
            if tr.get("daily"):
                o.append(f"<div class='tspark'>{_spark(tr['daily'])}</div>")
            o.append("<div class='cards'>")
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

    # §4 Scheme Scorecard — REAL 7-day tone trend (was deferred in the daily report)
    sr = r.get("schemes", [])
    if sr:
        o.append("<section><div class='shead'><span class='num'>4</span><h2>How Each Scheme Was Covered</h2>"
                 f"<span class='cnt'>{len(sr)} schemes</span></div>"
                 "<p class='sf'>Flagship programmes over the week &mdash; volume, tone, and the day-by-day trend "
                 "that a single day cannot show.</p>")
        _splab = {"web": "Online", "tv": "Television", "newspaper": "Newspaper"}
        for s2 in sr:
            spread = ("web %d" % s2.get("web", 0)
                      + (" &middot; TV %d" % s2["tv"] if s2.get("tv") else "")
                      + (" &middot; paper %d" % s2["np"] if s2.get("np") else ""))
            o.append(f"<div class='tblock'><div class='tbh'><h3>{_e(s2['scheme'])}</h3>"
                     f"<span class='schm'>{s2['items']} items &middot; {spread}</span>"
                     f"<span class='net {_net_cls(s2['net'])}'>{s2['net']:+d}</span></div>")
            if s2.get("daily"):
                o.append(f"<div class='tspark'>{_spark(s2['daily'])}</div>")
            cards = s2.get("cards", {})
            o.append("<div class='cards'>")
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

    # §5 Districts (week)
    dr = r.get("districts", [])
    if dr:
        o.append("<section><div class='shead'><span class='num'>5</span><h2>Coverage by District</h2>"
                 f"<span class='cnt'>{len(dr)} active</span></div>"
                 "<p class='sf'>Where the week's coverage localised, district by district, and how it read.</p><div class='dmap'>")
        for d in dr[:14]:
            it = d["items"]
            o.append(f"<div class='tile {_dcls(d['net'])}'><b>{_e(d['district'])}</b>"
                     f"<span class='tinfo'>{it} item{'' if it == 1 else 's'}"
                     f"<em class='tnet'>{d['net']:+d}</em></span></div>")
        o.append("</div>")
        notes = []
        for d in dr[:12]:
            tcc, tp = d.get("top_critical"), d.get("top_positive")
            if d["net"] < 0 and tcc:
                pick, tone = tcc, "crit"
            elif tp:
                pick, tone = tp, "pos"
            elif tcc:
                pick, tone = tcc, "crit"
            else:
                continue
            if (pick.get("text") or "").strip():
                notes.append((d, pick, tone))
        if notes:
            o.append("<div class='rlab' style='margin-top:20px'>Notable district coverage</div><div class='dnotes'>")
            for d, pick, tone in notes[:8]:
                src = f"<span class='src2'> &mdash; {_e(pick['source'])}</span>" if pick.get("source") else ""
                o.append(f"<div class='dnote'><div class='dnh'><span class='dnm'>{_e(d['district'])}</span>"
                         f"<span class='dni'>{d['items']} items</span>"
                         f"<span class='net {_net_cls(d['net'])}'>{d['net']:+d}</span></div>"
                         f"<div class='dnq {tone}'>{_tel((pick['text'] or '')[:140])}{src}</div></div>")
            o.append("</div>")
        o.append("</section>")

    # §6 Media Compared (week) with per-pillar daily mini trend
    mp = {m["pillar"]: m for m in r.get("media_compare", [])}
    o.append("<section><div class='shead'><span class='num'>6</span><h2>Newspapers, TV and Websites Compared</h2></div>"
             "<p class='sf'>The three do not move together across a week either.</p><div class='panels'>")
    for pl, lab in [("newspaper", "Newspapers"), ("tv", "Television"), ("web", "Online")]:
        m = mp.get(pl, {"net": 0, "favourable": 0, "critical": 0})
        o.append(f"<div class='panel'><div class='ph'>{lab}</div><div class='pn {_net_cls(m['net'])}'>{m['net']:+d}</div>"
                 f"<div class='tbar'>{_bar(m['favourable'], m['critical'])}</div>"
                 f"<div class='ks' style='margin-top:8px'>{m['favourable']} for &middot; {m['critical']} against</div>")
        if m.get("daily"):
            o.append(_spark(m["daily"]))
        o.append("</div>")
    o.append("</div></section>")

    # §7 TV share of voice — government vs opposition figures on television
    # (client request 2026-08-10): butterfly chart + LLM analysis + stat strip.
    sov = r.get("tv_sov") or {}
    if sov.get("total"):
        attributed = (sov["total"] - sov.get("unattributed", 0)) or 1
        o.append("<section><div class='shead'><span class='num'>7</span>"
                 "<h2>Government vs Opposition on Television</h2>"
                 "<span class='cnt'>share of voice</span></div>"
                 f"<p class='sf'>Of the week's <b>{sov['total']}</b> television stories on the government, "
                 f"<b>{sov['gov']}</b> featured government-side figures and <b>{sov['opp']}</b> featured "
                 f"opposition figures ({sov.get('both', 0)} featured both; "
                 f"{sov.get('unattributed', 0)} named no political actor)"
                 + (f" &mdash; a <b>{sov['ratio']}&thinsp;:&thinsp;1</b> government-to-opposition "
                    f"share of voice." if sov.get("ratio") else ".") + "</p>")
        o.append("<div class='sovstrip'>"
                 f"<div class='kt'><div class='kl'>Featuring government</div>"
                 f"<div class='kv'>{sov['gov']}</div>"
                 f"<div class='ks'>{round(100 * sov['gov'] / attributed)}% of actor-attributed stories</div></div>"
                 f"<div class='kt'><div class='kl'>Featuring opposition</div>"
                 f"<div class='kv'>{sov['opp']}</div>"
                 f"<div class='ks'>{round(100 * sov['opp'] / attributed)}% of actor-attributed stories</div></div>"
                 f"<div class='kt'><div class='kl'>Head-to-head</div><div class='kv'>{sov.get('both', 0)}</div>"
                 f"<div class='ks'>stories featuring both sides</div></div></div>")
        if sov.get("analysis"):
            o.append(f"<div class='glance'><div class='rlab'>What the split says</div>"
                     f"<p>{_e(sov['analysis'])}</p></div>")
        if ch.get("tv_sov"):
            o.append(f"<div class='chbox'><h3>Stories featuring each side, by channel</h3>{ch['tv_sov']}</div>")
        po = sov.get("party_owned") or {}
        if po.get("items"):
            o.append(f"<p class='sf' style='margin-top:8px'>Excluded from the channel chart: "
                     f"{po['items']} stories on {po.get('n_channels', 0)} party- or "
                     f"politician-owned channels &mdash; counted in the week totals above, but not "
                     f"news coverage.</p>")
        o.append("</section>")

    # §8 What Each Side Said (week)
    q = r.get("quotes", {})
    if q.get("government") or q.get("opposition"):
        o.append("<section><div class='shead'><span class='num'>8</span><h2>What Each Side Said</h2>"
                 f"<span class='cnt'>this week</span></div><div class='qcols'>")
        for side, cls, lab in [("government", "g", "Government"), ("opposition", "o", "Opposition")]:
            o.append(f"<div class='qcol {cls}'><div class='qs'>{lab}</div>")
            for qq in q.get(side, [])[:3]:
                o.append(f"<blockquote>{_teln(qq['text'], qq.get('en'))}"
                         f"<div class='who'>&mdash; <b>{_e(qq['speaker'])}</b> &middot; {_cite(qq['source'], qq.get('url'))}</div></blockquote>")
            if not q.get(side):
                o.append("<div class='who'>No quotes on record.</div>")
            o.append("</div>")
        o.append("</div>")
        also = [(sd, qq) for sd, qq in ([('gov', x) for x in q.get('government', [])[3:]] +
                                        [('opp', x) for x in q.get('opposition', [])[3:]])]
        if also:
            o.append("<div class='lab2'>Also on record</div><table><tbody>")
            for sd, qq in also[:10]:
                sidelab = "<span class='qtag g'>Govt</span>" if sd == 'gov' else "<span class='qtag o'>Opp</span>"
                o.append(f"<tr><td class='nm' style='width:160px'>{_e(qq['speaker'])} {sidelab}</td>"
                         f"<td>{_teln(qq['text'], qq.get('en'))}</td>"
                         f"<td class='num src2'>{_cite(qq['source'], qq.get('url'))}</td></tr>")
            o.append("</tbody></table>")
        o.append("</section>")

    # §8 Figures Quoted (week)
    if r.get("figures"):
        o.append("<section><div class='shead'><span class='num'>9</span><h2>Figures Quoted in the Press</h2></div>"
                 "<p class='sf'>Numbers attached to a government scheme or commitment, this week.</p>")
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
                o.append(f"<div class='fig'><div class='v'>{_e(_valunit(f['value'], f['unit']))}</div>"
                         f"<div class='c'>{_e(f['context'])}{flag}{cite}</div></div>")
            o.append("</div>")
        o.append("</section>")

    # §9 Which Outlet (week) — grouped by medium (was one mixed table with the
    # medium buried in a column; grouping makes it scannable, and each group's
    # own table gives the 7-day trend a real column instead of a squeezed one).
    ots = r.get("outlets", [])
    if ots:
        o.append("<section><div class='shead'><span class='num'>10</span><h2>Which Outlet Said What</h2>"
                 f"<span class='cnt'>{len(ots)} outlets, this week</span></div>"
                 "<p class='sf'>Ranked by how much government coverage each outlet ran, grouped by medium.</p>")
        _medlab = {"web": "Online", "tv": "Television", "newspaper": "Newspapers"}
        by_medium: dict[str, list] = {}
        for ot in ots:
            by_medium.setdefault(ot["pillar"], []).append(ot)
        for pillar in ("newspaper", "tv", "web"):
            group = by_medium.get(pillar)
            if not group:
                continue
            o.append(f"<div class='lab2' style='margin-top:18px'>{_medlab.get(pillar, pillar)}</div>"
                     "<table><thead><tr><th>Outlet</th><th class='num'>On govt</th><th>Tone</th>"
                     "<th class='num'>Net</th><th>7-day trend</th></tr></thead><tbody>")
            for ot in group:
                n = ot['net']
                lean = ("<span class='lean n'>critical-leaning</span>" if n <= -30 else
                        "<span class='lean p'>govt-leaning</span>" if n >= 30 else "")
                trend = _spark(ot["daily"]) if ot.get("daily") else ""
                o.append(f"<tr><td class='nm'>{_e(ot['outlet'])} {lean}</td>"
                         f"<td class='num'>{ot['on_govt']}</td><td>{_bar(ot['favourable'], ot['critical'])}</td>"
                         f"<td class='num net {_net_cls(ot['net'])}'>{ot['net']:+d}</td><td>{trend}</td></tr>")
            o.append("</tbody></table>")
        o.append("</section>")

    # §10 Annexure (grouped by day)
    anx = r.get("annexure", [])
    if anx:
        o.append("<section><div class='shead'><span class='num'>11</span><h2>All Stories, with Links</h2>"
                 f"<span class='cnt'>{len(anx)} cited</span></div><div class='anx'>")
        last_date = None
        i = 0
        for a in anx:
            if a["date"] != last_date:
                o.append(f"<div class='daymark'>{_e(_day_label(a['date']))} &middot; {_e(a['date'])}</div>")
                last_date = a["date"]
            i += 1
            link = f"<a href='{_e(a['url'])}'>Open &rarr;</a>" if a.get("url") else "<a>—</a>"
            o.append(f"<div class='ax'><span class='r'>{i}</span><div><h4>{_tel((a.get('title') or '')[:90])}</h4>"
                     f"<div class='amt'><span class='med'>{_e(a['pillar'])}</span> &middot; {_e(a['source'])} &middot; {_e(a['lang'])}</div></div>{link}</div>")
        o.append("</div></section>")

    o.append("<div class='enddisc'>Prepared from published media only, across the week shown above. Tone reflects "
             "how the government was portrayed, not the accuracy of reporting.</div>")
    o.append("</div>")  # /paper
    o.append("<script>if(!window.__ISPDF__){document.documentElement.classList.add('screenview');}</script>")
    o.append("</body></html>")
    return "".join(o)


WEEKLY_CSS = """
.wtrend{padding:18px 46px;border-bottom:1px solid var(--hair2)}
.wtrend-note{font-family:var(--sans);font-size:10px;color:var(--faint);margin-top:6px}
.spark{display:flex;align-items:flex-end;gap:5px;height:40px}
.spark.big{height:44px}
.spark .sbar{display:flex;flex-direction:column;align-items:center;gap:3px}
.spark .sbar i{display:block;width:12px;border-radius:2px 2px 0 0}
.spark.big .sbar i{width:16px}
.spark .sbar span{font-family:var(--mono);font-size:8px;color:var(--muted)}
.sp-pos{background:var(--pro)}.sp-neg{background:var(--anti)}.sp-z{background:var(--faint)}
.tspark{padding:8px 16px 0;border-bottom:1px solid var(--hair2);background:#fafbfc}
.daymark{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
  color:var(--navy2);margin:18px 0 4px;padding-bottom:4px;border-bottom:1px solid var(--navy-line)}
ol.brief li:first-child, .daymark:first-child{margin-top:0}
.dchip{display:inline-block;vertical-align:middle;margin-left:8px;padding:2px 7px;border-radius:9px;
  font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.03em}
.dchip.u{background:#e8f4ec;color:#1e6b3a}.dchip.d{background:#fbebea;color:#a03530}
.dchip.z{background:#eef1f4;color:#4f5a64}
.glance{margin:14px 16px 4px;padding:14px 16px;border:1px solid var(--hair2);border-left:3px solid var(--navy2);
  background:#fafbfc;break-inside:avoid}
.glance p{margin:6px 0 0;font-size:12.5px;line-height:1.62;color:#2b333b}
.glance-note{margin-top:8px;font-family:var(--sans);font-size:9.5px;color:#4f5a64}
.movers{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.movers .ml{font-family:var(--sans);font-size:9.5px;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;color:var(--navy2);margin-right:4px}
.mchip{display:inline-block;padding:3px 9px;border-radius:10px;font-family:var(--sans);
  font-size:10px;font-weight:600}
.mchip i{font-style:normal;font-weight:700;margin-left:4px}
.mchip.u{background:#e8f4ec;color:#1e6b3a}.mchip.d{background:#fbebea;color:#a03530}
.chartsec .chbox{border:1px solid var(--hair2);background:#fff;padding:12px 14px 8px;margin:10px 0;break-inside:avoid}
.chbox h3{font-family:var(--sans);font-size:10.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
  color:var(--navy2);margin:0 0 8px}
.chbox svg{width:100%;height:auto;display:block}
.chrow{display:flex;gap:10px;margin:10px 0}
.chrow .chbox{flex:1;margin:0}
.chleg{display:flex;gap:16px;margin:2px 2px 4px;font-family:var(--sans);font-size:9.5px;color:var(--muted)}
.chleg .k{display:inline-flex;align-items:center;gap:5px}
.chleg .k i{width:10px;height:10px;border-radius:2px;display:inline-block}
.sovstrip{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid var(--hair2);margin:10px 0;break-inside:avoid}
.sovstrip .kt:last-child{border-right:none}
"""


async def render_weekly_for(org_id: str, start_date, end_date) -> str:
    from briefing.weekly_assemble import assemble_weekly
    r = await assemble_weekly(org_id, start_date, end_date)
    if r.get("error"):
        return f"<html><body style='font-family:sans-serif;padding:40px'><h2>{_e(r['error'])}</h2></body></html>"
    return render_weekly_html(r)
