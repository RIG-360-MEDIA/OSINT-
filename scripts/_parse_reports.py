"""Parse the 3 HTML extraction reports: aggregate quality + dump sample snaps."""
import base64
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

EVAL = os.path.dirname(os.path.abspath(__file__)) + "/eval_data"
REPORTS = {
    "EN Financial Express": "report_Financial_Express.html",
    "HI Dainik Bhaskar": "report_Dainik_Bhaskar.html",
    "TE Sakshi": "report_Sakshi.html",
}

CARD = re.compile(r'<div class="card">(.*?)</div>\s*</div>', re.S)
H2 = re.compile(r"<h2>#(\d+).*?&nbsp;\s*(.*?)</h2>", re.S)
CROP = re.compile(r"crop:\s*(\w+)")
TXT = re.compile(r"text:\s*(\w+)")
CONF = re.compile(r"confidence:\s*([\d.]+)")
REVIEW = re.compile(r"NEEDS REVIEW")
BODY = re.compile(r'<div class="body">(.*?)</div>', re.S)
IMG = re.compile(r'src="data:image/jpeg;base64,([^"]+)"')


def parse(path):
    raw = open(path, encoding="utf-8").read()
    cards = re.split(r'<div class="card">', raw)[1:]
    arts = []
    for c in cards:
        h = H2.search(c)
        arts.append({
            "i": h.group(1) if h else "?",
            "headline": re.sub(r"\s+", " ", (h.group(2) if h else "")).strip(),
            "crop": (CROP.search(c).group(1) if CROP.search(c) else "?"),
            "txt": (TXT.search(c).group(1) if TXT.search(c) else "—"),
            "conf": (float(CONF.search(c).group(1)) if CONF.search(c) else None),
            "review": bool(REVIEW.search(c)),
            "body": re.sub(r"\s+", " ", (BODY.search(c).group(1) if BODY.search(c) else "")).strip(),
            "img": (IMG.search(c).group(1) if IMG.search(c) else None),
        })
    return arts


for name, fn in REPORTS.items():
    path = f"{EVAL}/{fn}"
    if not os.path.exists(path):
        print(name, "MISSING"); continue
    arts = parse(path)
    n = len(arts)
    crop = {}
    txt = {}
    review = 0
    confs = []
    for a in arts:
        crop[a["crop"]] = crop.get(a["crop"], 0) + 1
        txt[a["txt"]] = txt.get(a["txt"], 0) + 1
        review += a["review"]
        if a["conf"] is not None:
            confs.append(a["conf"])
    print("=" * 70)
    print(f"{name}: {n} articles")
    print(f"  crop:  {crop}")
    print(f"  text:  {txt}")
    print(f"  needs_review: {review}/{n}")
    if confs:
        print(f"  confidence: mean={sum(confs)/len(confs):.2f} min={min(confs):.2f} max={max(confs):.2f}")
    # flagged ones
    for a in arts:
        if a["review"]:
            print(f"   FLAG #{a['i']} conf={a['conf']} :: {a['headline'][:50]}")
    # dump first 3 anchored snapshots for visual check
    tag = name.split()[0]
    dumped = 0
    for a in arts:
        if a["img"] and dumped < 3:
            with open(f"{EVAL}/snap_{tag}_{a['i']}.png", "wb") as fh:
                fh.write(base64.b64decode(a["img"]))
            dumped += 1
    # show first 4 body previews
    print("  bodies:")
    for a in arts[:4]:
        print(f"   #{a['i']} [{a['crop']}/{a['txt']}] {a['headline'][:40]!r}")
        print(f"      {a['body'][:140]!r}")
