"""Probe: fetch captions the way the relay will — yt-dlp Python API + cookies,
grab the caption track URL from extract_info, fetch json3 directly (no CLI
format selection). Proves the design on the currently IP-blocked desktop."""
import json
import sys

from yt_dlp import YoutubeDL

COOKIE = r"D:\cookies (5).txt"
PREFERRED = ("en", "en-orig", "en-US", "te", "hi", "kn", "ta", "ur")
VID = sys.argv[1] if len(sys.argv) > 1 else "dQw4w9WgXcQ"


def pick(man, auto):
    for lang in PREFERRED:
        if lang in man:
            return lang, man[lang], False
    for lang in PREFERRED:
        if lang in auto:
            return lang, auto[lang], True
    if man:
        k = next(iter(man)); return k, man[k], False
    if auto:
        k = next(iter(auto)); return k, auto[k], True
    return None, None, None


opts = {"skip_download": True, "quiet": True, "no_warnings": True,
        "cookiefile": COOKIE, "ignore_no_formats_error": True}
with YoutubeDL(opts) as ydl:
    # process=False → return the extractor's info (incl. caption tracks) WITHOUT
    # running video-format selection, which fails when only image formats exist.
    info = ydl.extract_info(
        f"https://www.youtube.com/watch?v={VID}", download=False, process=False)
    man = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    lang, tracks, is_auto = pick(man, auto)
    if not lang:
        print("NO_TRANSCRIPT"); sys.exit(0)
    j3 = next((t for t in tracks if t.get("ext") == "json3"), tracks[0])
    raw = ydl.urlopen(j3["url"]).read()

data = json.loads(raw)
events = data.get("events", [])
segs = []
for e in events:
    if "segs" not in e:
        continue
    text = "".join(s.get("utf8", "") for s in e["segs"]).strip()
    if text:
        segs.append({"start": e.get("tStartMs", 0) / 1000.0,
                     "duration": e.get("dDurationMs", 0) / 1000.0, "text": text})
print(f"OK lang={lang} auto={is_auto} segments={len(segs)} bytes={len(raw)}")
print("first 2:", [s["text"] for s in segs[:2]])
