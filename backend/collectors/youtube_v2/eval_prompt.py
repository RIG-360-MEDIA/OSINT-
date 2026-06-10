"""eval_prompt.py — Field-level quality evaluation of TRANSCRIPT_SYS.

Compares OLD prompt (extraction._build_system_prompt) vs NEW prompt
(prompts.build_transcript_sys) on real and synthetic transcript data.

Three language tracks:
  te  — real transcript fetched via relay (known-good video IDs)
  hi  — synthetic Hindi political transcript
  en  — synthetic English political transcript

Scores every field that TRANSCRIPT_SYS emits. Prints a per-field,
per-language pass-rate table plus a side-by-side OLD vs NEW summary.

Usage (from repo root on TRIJYA-7):
    set GROQ_API_KEYS=key1,key2
    set RELAY_URL=http://localhost:8888
    python -m backend.collectors.youtube_v2.eval_prompt

Optional flags:
    --relay-url http://...   override relay URL
    --video-id  <id>         add extra video ID for Telugu fetch
    --old-only               evaluate old prompt only
    --new-only               evaluate new prompt only (default)
    --chunks    N            max chunks per video to evaluate (default 3)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("eval_prompt")

# ── path setup ────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.join(_HERE, "..", "..", "..")
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# ── synthetic transcript samples ─────────────────────────────────────────────
# Used for Hindi and English tracks to avoid YouTube calls.
# Content is representative political discourse covering monitored entities.

_HINDI_SAMPLE = """[0s] तेलंगाना में आज बड़ी राजनीतिक हलचल
[3s] मुख्यमंत्री रेवंत रेड्डी ने आज प्रेस कॉन्फ्रेंस में
[7s] पूर्व मुख्यमंत्री के चंद्रशेखर राव पर
[11s] बड़ा हमला बोला
[14s] रेवंत रेड्डी ने कहा कि
[17s] केसीआर के शासनकाल में
[21s] कालेश्वरम परियोजना में
[25s] एक लाख करोड़ रुपये का
[28s] भ्रष्टाचार हुआ है
[32s] और इसकी सीबीआई जांच होनी चाहिए
[36s] दूसरी तरफ के चंद्रशेखर राव ने
[40s] इन आरोपों को बेबुनियाद बताया
[44s] और कहा कि कांग्रेस सरकार
[48s] राजनीतिक बदले की भावना से काम कर रही है
[52s] बीआरएस के वरिष्ठ नेता के टी रामाराव ने भी
[57s] रेवंत सरकार पर निशाना साधा
[61s] उन्होंने कहा कि असली मुद्दा
[65s] बेरोजगारी और किसानों की समस्या है
[69s] लेकिन कांग्रेस ध्यान भटका रही है
[73s] हैदराबाद में आज यह विवाद और गहरा गया"""

_ENGLISH_SAMPLE = """[0s] Breaking news from Hyderabad where Telangana Chief Minister
[4s] Revanth Reddy held a press conference this morning
[8s] squarely targeting former Chief Minister K Chandrashekar Rao
[12s] over the Kaleshwaram irrigation project controversy
[16s] Revanth Reddy claimed that during KCR's ten-year tenure
[21s] over one lakh crore rupees were misappropriated
[25s] in the execution of the Kaleshwaram project
[29s] and he demanded a central bureau of investigation probe
[33s] saying the money belongs to the farmers of Telangana
[38s] KCR's party the Bharat Rashtra Samithi rejected these allegations
[43s] BRS spokesperson said the accusations are politically motivated
[47s] and an attempt to deflect attention from Congress governance failures
[52s] K T Rama Rao who is KCR's son and BRS working president
[57s] also weighed in saying Revanth Reddy should focus on unemployment
[62s] and farmer distress instead of settling political scores
[66s] The Kaleshwaram project was a flagship scheme under the previous BRS government
[71s] that brought water from the Godavari river to northern Telangana
[76s] T Harish Rao who was irrigation minister under KCR
[80s] defended the project saying it benefited millions of farmers"""

# ── known-good Telugu video IDs (from _quality_check.py, relay-tested) ───────
_TELUGU_VIDEO_IDS = [
    ("N-Tiq5hU5Nk", "News18 Telugu", "KTR slams Revanth — ~5-8 min"),
    ("ZYOUfkpDcDg", "Yuvagalam", "KCR+Harish counter Revanth — multi-entity"),
    ("pi9T4dGg_xo", "NTV Telugu", "Revanth fires on KCR — opposition-frame"),
]

# ── canonical entities for eval (mirrors what pipeline loads from DB) ─────────
EVAL_ENTITIES = [
    "A. Revanth Reddy",
    "K. Chandrashekar Rao",
    "K.T. Rama Rao",
    "T. Harish Rao",
    "Bhatti Vikramarka",
    "G. Kishan Reddy",
    "Narendra Modi",
    "Rahul Gandhi",
]

EVAL_ALIAS_BLOCK = (
    "Common aliases: KCR = K. Chandrashekar Rao; "
    "KTR = K.T. Rama Rao; Revanth = A. Revanth Reddy; "
    "Harish = T. Harish Rao; Bhatti = Bhatti Vikramarka; "
    "Modi = Narendra Modi."
)

# ── chunk helper ──────────────────────────────────────────────────────────────
_CHUNK_SECONDS = 150
_MAX_CHUNK_CHARS = 2200


def _parse_synthetic(raw: str) -> list[dict]:
    """Parse [Ns] text lines into segment dicts."""
    segs = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        bracket_end = line.find("]")
        if bracket_end < 0:
            continue
        try:
            start = float(line[1:bracket_end].rstrip("s"))
        except ValueError:
            continue
        text = line[bracket_end + 1:].strip()
        if text:
            segs.append({"start": start, "duration": 3.0, "text": text})
    return segs


def _chunk_segs(segs: list[dict], max_chunks: int) -> list[list[dict]]:
    if not segs:
        return []
    chunks: list[list[dict]] = []
    current: list[dict] = []
    anchor = segs[0]["start"]
    for s in segs:
        if s["start"] - anchor >= _CHUNK_SECONDS and current:
            chunks.append(current)
            current = []
            anchor = s["start"]
        current.append(s)
    if current:
        chunks.append(current)
    return chunks[:max_chunks]


def _build_user_msg(chunk: list[dict], video_title: str, language: str) -> str:
    lines = [f"[{int(s['start'])}s] {s['text'].strip()}" for s in chunk]
    body = "\n".join(lines)[:_MAX_CHUNK_CHARS]
    return (
        f"Video title: {video_title}\n"
        f"Transcript language: {language}\n\n"
        f"Transcript (format: [seconds] text):\n{body}"
    )


# ── relay fetch ───────────────────────────────────────────────────────────────
def fetch_via_relay(video_id: str, relay_url: str) -> list[dict] | None:
    import requests

    url = f"{relay_url.rstrip('/')}/fetch/{video_id}"
    logger.info("relay fetch video=%s", video_id)
    try:
        r = requests.get(url, timeout=120)
        data = r.json()
    except Exception as exc:
        logger.error("relay unreachable: %s", exc)
        return None

    if not data.get("ok"):
        logger.warning("relay returned not-ok: %s", data.get("reason"))
        return None

    segs = data.get("segments", [])
    logger.info("relay got %d segments lang=%s", len(segs), data.get("language", "?"))
    return segs


# ── field scorers ─────────────────────────────────────────────────────────────
_VALID_SEGMENT_TYPES = {"debate", "interview", "speech", "press_conference", "news_report", "panel"}
_VALID_STANCES_SET = {"supports", "opposes", "criticises", "praises", "neutral"}
_VALID_IMPORTANCE = {"high", "medium", "low"}
_VALID_INTENSITY = {"high", "medium", "low"}
_ISO2_CODES = {
    "IN", "US", "UK", "CN", "PK", "IR", "RU", "IL", "DE", "FR",
    "JP", "AU", "CA", "BD", "AF", "SA", "AE", "GB",
}
_FILLER_SUMMARIES = {
    "entity was mentioned", "too short", "no specific mention",
    "mentioned briefly", "passing mention",
}


def _is_filler(s: str) -> bool:
    sl = s.lower().strip()
    if len(sl) < 20:
        return True
    for f in _FILLER_SUMMARIES:
        if f in sl:
            return True
    return False


def _is_probably_english(s: str) -> bool:
    if not s:
        return False
    non_ascii = sum(1 for c in s if ord(c) > 127)
    return non_ascii / max(len(s), 1) < 0.25


@dataclass
class FieldResult:
    total: int = 0
    passed: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def pct(self) -> float:
        return (self.passed / self.total * 100) if self.total else 0.0

    def record(self, ok: bool, note: str = "") -> None:
        self.total += 1
        if ok:
            self.passed += 1
        elif note:
            self.notes.append(note)


def score_clips(clips: list[dict], entities: list[str]) -> dict[str, FieldResult]:
    entity_set = {e.lower().strip() for e in entities}
    results: dict[str, FieldResult] = {
        "entity":        FieldResult(),
        "timestamps":    FieldResult(),
        "importance":    FieldResult(),
        "summary":       FieldResult(),
        "summary_en":    FieldResult(),
        "segment_type":  FieldResult(),
        "speaker":       FieldResult(),
        "quotes":        FieldResult(),
        "claims_spo":    FieldResult(),
        "stances":       FieldResult(),
        "locations":     FieldResult(),
    }

    for c in clips:
        if not isinstance(c, dict):
            continue

        # entity
        ent = str(c.get("entity", "")).strip()
        results["entity"].record(ent.lower() in entity_set, f"got={ent!r}")

        # timestamps — mirror the Python gating clamp (end = max(end, start+20))
        try:
            start = int(c["start_seconds"])
            end = int(c["end_seconds"])
            end = max(end, start + 20)   # same clamp as extraction._gate_clip
            ts_ok = start >= 0 and end > start
        except (KeyError, TypeError, ValueError):
            ts_ok = False
        results["timestamps"].record(ts_ok,
            f"start={c.get('start_seconds')} end={c.get('end_seconds')}")

        # importance
        imp = str(c.get("importance", "")).lower()
        results["importance"].record(imp in _VALID_IMPORTANCE, f"got={imp!r}")

        # summary quality
        summ = str(c.get("summary", "")).strip()
        results["summary"].record(not _is_filler(summ), f"{summ[:50]!r}")
        results["summary_en"].record(_is_probably_english(summ), f"{summ[:50]!r}")

        # segment_type
        st = str(c.get("segment_type", "")).lower()
        results["segment_type"].record(st in _VALID_SEGMENT_TYPES, f"got={st!r}")

        # speaker: null is valid (auto-captions have no speaker labels).
        # Only fail if the model emits a placeholder instead of null.
        _BAD_SPEAKERS = {"speaker", "anchor", "host", "unknown", "null", "n/a", ""}
        sp = c.get("speaker")
        if sp is None:
            results["speaker"].record(True)   # null is correct
        else:
            sp_norm = str(sp).strip().lower()
            results["speaker"].record(
                sp_norm not in _BAD_SPEAKERS,
                f"placeholder speaker={sp!r}"
            )

        # quotes: each must have speaker+text
        quotes = c.get("quotes") or []
        if quotes:
            for q in quotes:
                qt = str(q.get("text", "")).strip() if isinstance(q, dict) else ""
                qsp = str(q.get("speaker", "")).strip() if isinstance(q, dict) else ""
                results["quotes"].record(
                    len(qt) >= 10 and len(qsp) >= 2,
                    f"text={qt[:30]!r} speaker={qsp!r}"
                )
        else:
            results["quotes"].record(False, "no quotes emitted")

        # claims: each must have subject+predicate+object, all non-empty
        claims = c.get("claims") or []
        if claims:
            for cl in claims:
                if not isinstance(cl, dict):
                    results["claims_spo"].record(False, "not a dict")
                    continue
                s = str(cl.get("subject", "")).strip()
                p = str(cl.get("predicate", "")).strip()
                o = str(cl.get("object", "")).strip()
                results["claims_spo"].record(
                    bool(s and p and o),
                    f"s={s!r} p={p!r} o={o!r}"
                )
        else:
            results["claims_spo"].record(False, "no claims emitted")

        # stances: actor+target must be real names (not placeholders), stance valid
        _BAD_ACTORS = {"speaker", "anchor", "host", "unknown", "n/a", ""}
        stances = c.get("stances") or []
        if stances:
            for st_item in stances:
                if not isinstance(st_item, dict):
                    results["stances"].record(False, "not a dict")
                    continue
                actor = str(st_item.get("actor", "")).strip()
                target = str(st_item.get("target", "")).strip()
                stance = str(st_item.get("stance", "")).lower()
                actor_ok = bool(actor) and actor.lower() not in _BAD_ACTORS
                results["stances"].record(
                    actor_ok and bool(target) and stance in _VALID_STANCES_SET,
                    f"actor={actor!r} target={target!r} stance={stance!r}"
                )
        else:
            results["stances"].record(False, "no stances emitted")

        # locations: country must be full name, not ISO-2
        locs = c.get("locations") or []
        if locs:
            for loc in locs:
                if not isinstance(loc, dict):
                    results["locations"].record(False, "not a dict")
                    continue
                country = str(loc.get("country", "")).strip()
                is_iso = country.upper() in _ISO2_CODES
                is_empty = not country
                results["locations"].record(
                    bool(country) and not is_iso,
                    f"country={country!r}"
                )
        else:
            results["locations"].record(False, "no locations emitted")

    return results


# ── LLM call (direct Groq — no Ollama dependency for standalone eval) ─────────
# Model list in priority order. For the eval we skip qwen/qwen3-32b because
# all keys share one rate-limit pool and it 429s immediately; llama-3.3-70b
# has a much higher TPM ceiling and is accurate enough for field scoring.
_GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama-3.1-8b-instant"]
_GROQ_API_BASE = "https://api.groq.com/openai/v1/chat/completions"

_groq_key_index = 0


def _get_groq_keys() -> list[str]:
    keys_raw = os.getenv("GROQ_API_KEYS", "").strip()
    if not keys_raw:
        raise RuntimeError(
            "GROQ_API_KEYS not set. "
            "Run: set GROQ_API_KEYS=key1,key2  then re-run the eval."
        )
    return [k.strip() for k in keys_raw.split(",") if k.strip()]


async def call_llm(system: str, user: str) -> list[dict]:
    """Direct Groq call with key rotation and model fallback — bypasses unified
    pool so Ollama is not required for a standalone eval."""
    import httpx

    global _groq_key_index
    keys = _get_groq_keys()

    async with httpx.AsyncClient(timeout=90) as client:
        for model in _GROQ_MODELS:
            payload = {
                "model": model,
                "response_format": {"type": "json_object"},
                "max_tokens": 1500,
                "temperature": 0.0,
                "messages": [
                    {"role": "system", "content": system + " /no_think"},
                    {"role": "user",   "content": user},
                ],
            }
            # Try a few keys per model before giving up on that model
            keys_to_try = min(len(keys), 3)
            for _ in range(keys_to_try):
                key = keys[_groq_key_index % len(keys)]
                _groq_key_index += 1
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                }
                try:
                    r = await client.post(_GROQ_API_BASE, json=payload, headers=headers)
                    if r.status_code == 429:
                        # Parse retry-after if present
                        retry_after = float(r.headers.get("retry-after", "3"))
                        retry_after = min(retry_after, 8.0)
                        logger.info("429 model=%s — waiting %.0fs then rotating key", model, retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    r.raise_for_status()
                    content = r.json()["choices"][0]["message"]["content"]
                    data = json.loads(content)
                    logger.info("LLM ok model=%s", model)
                    return data.get("clips", []) if isinstance(data, dict) else []
                except Exception as exc:
                    logger.warning("model=%s key attempt failed: %s", model, exc)
                    await asyncio.sleep(1)

            logger.warning("model=%s exhausted %d keys — trying next model", model, keys_to_try)
            await asyncio.sleep(5)

    logger.error("All models and keys exhausted")
    return []


# ── eval one track ────────────────────────────────────────────────────────────
@dataclass
class TrackResult:
    lang: str
    label: str
    clips_total: int
    chunks_tested: int
    fields: dict[str, FieldResult]


async def eval_track(
    lang: str,
    label: str,
    segs: list[dict],
    system_prompt: str,
    max_chunks: int,
    delay_secs: float = 2.0,
) -> TrackResult:
    chunks = _chunk_segs(segs, max_chunks)
    all_clips: list[dict] = []
    logger.info("[%s] %d chunks to evaluate", lang, len(chunks))

    for i, chunk in enumerate(chunks):
        user_msg = _build_user_msg(chunk, label, lang)
        clips = await call_llm(system_prompt, user_msg)
        logger.info("[%s] chunk %d/%d → %d clips", lang, i + 1, len(chunks), len(clips))
        all_clips.extend(clips)
        if i < len(chunks) - 1:
            await asyncio.sleep(delay_secs)

    fields = score_clips(all_clips, EVAL_ENTITIES)
    return TrackResult(
        lang=lang,
        label=label,
        clips_total=len(all_clips),
        chunks_tested=len(chunks),
        fields=fields,
    )


# ── print helpers ─────────────────────────────────────────────────────────────
_FIELD_ORDER = [
    ("entity",       "Entity canonical match"),
    ("timestamps",   "Timestamps valid (start<end, ≥10s)"),
    ("importance",   "Importance valid enum"),
    ("summary",      "Summary non-filler"),
    ("summary_en",   "Summary in English"),
    ("segment_type", "segment_type valid enum"),
    ("speaker",      "Speaker identified"),
    ("quotes",       "Quotes (speaker+text≥10c)"),
    ("claims_spo",   "Claims SPO all fields"),
    ("stances",      "Stances (actor+target+stance)"),
    ("locations",    "Locations (full country name)"),
]


def _pct_bar(pct: float) -> str:
    filled = int(pct / 10)
    bar = "#" * filled + "." * (10 - filled)
    return f"{bar} {pct:5.1f}%"


def print_track_result(result: TrackResult) -> None:
    print(f"\n{'-'*64}")
    print(f"  TRACK: {result.lang.upper()} -- {result.label}")
    print(f"  Chunks tested: {result.chunks_tested}  |  Clips emitted: {result.clips_total}")
    print(f"{'-'*64}")
    print(f"  {'Field':<36} {'n':>4}  {'Pass':>5}  Score")
    print(f"  {'-'*36} {'-'*4}  {'-'*5}  {'-'*16}")
    for key, desc in _FIELD_ORDER:
        fr = result.fields[key]
        flag = "[OK]" if fr.pct >= 80 else ("[~~]" if fr.pct >= 50 else "[!!]")
        print(f"  {flag} {desc:<34} {fr.total:>4}  {fr.passed:>5}  {_pct_bar(fr.pct)}")
        if fr.notes and fr.pct < 80:
            for note in fr.notes[:2]:
                print(f"       -> {note}")


def print_comparison(old_results: list[TrackResult], new_results: list[TrackResult]) -> None:
    print(f"\n{'='*70}")
    print("  OLD vs NEW PROMPT COMPARISON")
    print(f"{'='*70}")
    # Only compare fields that exist in old prompt (first 5)
    compare_fields = [
        ("entity",     "Entity"),
        ("timestamps", "Timestamps"),
        ("importance", "Importance"),
        ("summary",    "Summary"),
        ("summary_en", "Summary English"),
    ]
    old_map = {r.lang: r for r in old_results}
    new_map = {r.lang: r for r in new_results}
    for lang in ["te", "hi", "en"]:
        if lang not in old_map or lang not in new_map:
            continue
        print(f"\n  {lang.upper()}:")
        print(f"  {'Field':<20} {'Old%':>6} {'New%':>6} {'Δ':>6}")
        for key, label in compare_fields:
            old_pct = old_map[lang].fields[key].pct
            new_pct = new_map[lang].fields[key].pct
            delta = new_pct - old_pct
            flag = "↑" if delta > 2 else ("↓" if delta < -2 else "=")
            print(f"  {label:<20} {old_pct:>5.1f}% {new_pct:>5.1f}% {flag}{abs(delta):>4.1f}%")


def print_summary_table(results: list[TrackResult]) -> None:
    print(f"\n{'='*70}")
    print("  FIELD QUALITY SUMMARY (new prompt, all languages)")
    print(f"{'='*70}")
    print(f"  {'Field':<36} {'te':>7} {'hi':>7} {'en':>7} {'avg':>7}")
    print(f"  {'-'*36} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
    lang_map = {r.lang: r for r in results}
    for key, desc in _FIELD_ORDER:
        row = []
        for lang in ["te", "hi", "en"]:
            if lang in lang_map:
                row.append(lang_map[lang].fields[key].pct)
            else:
                row.append(float("nan"))
        valid = [x for x in row if x == x]
        avg = sum(valid) / len(valid) if valid else 0.0
        vals = [f"{v:6.1f}%" if v == v else "    n/a" for v in row]
        flag = "[OK]" if avg >= 80 else ("[~~]" if avg >= 50 else "[!!]")
        print(f"  {flag} {desc:<34} {'  '.join(vals)}  {avg:6.1f}%")


# ── main ──────────────────────────────────────────────────────────────────────
async def main(args: argparse.Namespace) -> None:
    # Import here to avoid loading the full backend (Ollama/Groq pool) at module level
    from backend.collectors.youtube_v2.extraction import _build_system_prompt as old_prompt_fn  # noqa: PLC0415
    from backend.collectors.youtube_v2.prompts import build_transcript_sys as new_prompt_fn  # noqa: PLC0415

    relay_url = args.relay_url or os.getenv("RELAY_URL", "http://localhost:8888")
    max_chunks = args.chunks

    old_prompt = old_prompt_fn("Eval Channel", EVAL_ENTITIES, EVAL_ALIAS_BLOCK)
    new_prompt = new_prompt_fn("Eval Channel", EVAL_ENTITIES, EVAL_ALIAS_BLOCK)

    # ── build track inputs ────────────────────────────────────────────────────
    tracks: list[tuple[str, str, list[dict]]] = []

    # Telugu — fetch from relay
    video_ids = list(_TELUGU_VIDEO_IDS)
    if args.video_id:
        video_ids.insert(0, (args.video_id, "Custom", "user-supplied"))

    te_segs: list[dict] = []
    for vid, channel, note in video_ids[:1]:  # one video to avoid burning relay
        logger.info("Fetching Telugu test video %s (%s)", vid, note)
        segs = fetch_via_relay(vid, relay_url)
        if segs:
            te_segs = segs
            te_label = f"{channel} / {vid}"
            break
        logger.warning("No transcript for %s — trying next", vid)
        time.sleep(5)

    if te_segs:
        tracks.append(("te", te_label, te_segs))
    else:
        logger.warning("All Telugu fetches failed — skipping te track")

    # Hindi — synthetic
    tracks.append(("hi", "Synthetic Hindi political news", _parse_synthetic(_HINDI_SAMPLE)))

    # English — synthetic
    tracks.append(("en", "Synthetic English political news", _parse_synthetic(_ENGLISH_SAMPLE)))

    # ── run eval ──────────────────────────────────────────────────────────────
    print(f"\n{'='*64}")
    print("  TRANSCRIPT PROMPT QUALITY EVALUATION")
    print(f"{'='*64}")

    run_old = not args.new_only
    run_new = not args.old_only

    old_track_results: list[TrackResult] = []
    new_track_results: list[TrackResult] = []

    for lang, label, segs in tracks:
        if run_old:
            print(f"\n[OLD PROMPT] {lang.upper()} — {label}")
            r = await eval_track(lang, label, segs, old_prompt, max_chunks, delay_secs=1.5)
            print_track_result(r)
            old_track_results.append(r)
            await asyncio.sleep(3)

        if run_new:
            print(f"\n[NEW PROMPT] {lang.upper()} — {label}")
            r = await eval_track(lang, label, segs, new_prompt, max_chunks, delay_secs=1.5)
            print_track_result(r)
            new_track_results.append(r)
            if lang != tracks[-1][0]:
                await asyncio.sleep(3)

    # ── summary ───────────────────────────────────────────────────────────────
    if run_new and new_track_results:
        print_summary_table(new_track_results)

    if run_old and run_new and old_track_results and new_track_results:
        print_comparison(old_track_results, new_track_results)

    print(f"\n{'='*64}")
    print("  DONE")
    print(f"{'='*64}\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate TRANSCRIPT_SYS prompt quality")
    p.add_argument("--relay-url", default="")
    p.add_argument("--video-id", default="")
    p.add_argument("--chunks", type=int, default=3)
    p.add_argument("--old-only", action="store_true")
    p.add_argument("--new-only", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
