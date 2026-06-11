"""From the 3 HTML reports, show what each page of each newspaper contains."""
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

EVAL = os.path.dirname(os.path.abspath(__file__)) + "/eval_data"
REPORTS = {
    "EN  Financial Express": "report_Financial_Express.html",
    "HI  Dainik Bhaskar": "report_Dainik_Bhaskar.html",
    "TE  Sakshi": "report_Sakshi.html",
}

H2 = re.compile(r"<h2>#(\d+).*?&nbsp;\s*(.*?)</h2>", re.S)
PAGE = re.compile(r"page:\s*(\d+)")
SECTION = re.compile(r"section:\s*([^<]+?)\s*<")
CROP = re.compile(r"crop:\s*(\w+)")


def clean(t):
    return re.sub(r"\s+", " ", re.sub(r"&#x27;|&#39;", "'", t)).strip()


for name, fn in REPORTS.items():
    path = f"{EVAL}/{fn}"
    if not os.path.exists(path):
        continue
    raw = open(path, encoding="utf-8").read()
    cards = re.split(r'<div class="card">', raw)[1:]
    by_page = {}
    for c in cards:
        h = H2.search(c)
        if not h:
            continue
        pg = int(PAGE.search(c).group(1)) if PAGE.search(c) else 0
        sec = clean(SECTION.search(c).group(1)) if SECTION.search(c) else "—"
        crop = CROP.search(c).group(1) if CROP.search(c) else "?"
        by_page.setdefault(pg, []).append((sec, clean(h.group(2)), crop))

    print("=" * 78)
    print(name)
    for pg in sorted(by_page):
        arts = by_page[pg]
        secs = {}
        for s, _, _ in arts:
            secs[s] = secs.get(s, 0) + 1
        sec_summary = ", ".join(f"{k}×{v}" for k, v in sorted(secs.items(), key=lambda x: -x[1]))
        print(f"\n  PAGE {pg}  ({len(arts)} articles)  sections: {sec_summary}")
        for sec, head, crop in arts:
            mark = "" if crop in ("text", "body") else "  [no-snap]"
            print(f"     [{sec:<13}] {head[:58]}{mark}")
