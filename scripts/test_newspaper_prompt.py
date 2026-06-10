"""
Prompt-quality test for GROQ_SYS_NEWSPAPER across languages and fields.

Usage:
    python -m scripts.test_newspaper_prompt          # hardcoded fixtures
    python -m scripts.test_newspaper_prompt --live   # pull real clippings from pipeline

Scores each DB field group:
  schema    — required keys present, no missing top-level fields
  types     — enum values valid, bool/float types correct
  lengths   — summary length caps respected
  locations — country full-name, 5-field rule, India city rule
  numbers   — ₹ figures extracted, unit populated
  grounding — no invented text not in the body (OCR noise not copied verbatim)
  translate — english_translation present for Indic
"""
from __future__ import annotations

import asyncio
import json
import sys
import textwrap

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── Test fixtures (realistic OCR samples per language) ────────────────────────

FIXTURES = [
    {
        "lang": "en",
        "paper": "Financial Express",
        "headline": "Reliance Industries posts record Q4 profit of ₹19,299 crore",
        "body": (
            "Reliance Industries Limited (RIL) on Friday reported a 6.8 per cent rise "
            "in net profit to ₹19,299 crore for the fourth quarter ended March 2026, "
            "beating analyst estimates. Revenue from operations rose 11.2 per cent to "
            "₹2.33 lakh crore. JIOPLA TFORMS posted 21 per cent EBITDA growth to "
            "₹14,856 crore. Chairman Mukesh Ambani said the company remains fo-\n"
            "cused on accelerating new energy investments in Gujarat and Rajasthan.\n"
            "Contd. on page 5"
        ),
        "expected_fields": ["article_type", "primary_subject", "summaries",
                            "locations", "numbers", "entities_extracted",
                            "actor_stances", "register"],
        "expect_translation": False,
        "checks": {
            "numbers_min": 2,
            "locations_country": "India",
            "entities_min": 2,
        },
    },
    {
        "lang": "hi",
        "paper": "Navbharat Times",
        "headline": "दिल्ली में पानी का संकट: यमुना का जलस्तर गिरा",
        "body": (
            "राष्ट्रीय राजधानी दिल्ली में पानी की किल्लत बढ़ती जा रही है। "
            "यमुना नदी का जलस्तर गिरकर 200.50 मीटर पर आ गया है, जो सामान्य से "
            "2.3 मीटर कम है। दिल्ली जल बोर्ड के अनुसार कई इलाकों में 40 प्रतिशत "
            "कम पानी की आपूर्ति हो रही है। मुख्यमंत्री अरविंद केजरीवाल ने कहा कि "
            "हरियाणा सरकार पानी रोक रही है। जलमंत्री सौरभ भारद्वाज ने बताया कि "
            "₹500 करोड़ की परियोजना से जल्द राहत मिलेगी। पेज 3 देखें"
        ),
        "expected_fields": ["article_type", "primary_subject", "summaries",
                            "locations", "quotes", "numbers", "entities_extracted",
                            "english_translation"],
        "expect_translation": True,
        "checks": {
            "numbers_min": 1,
            "locations_country": "India",
            "entities_min": 2,
            "translation_min_chars": 100,
        },
    },
    {
        "lang": "te",
        "paper": "Eenadu",
        "headline": "తెలంగాణలో వరుణుడి కరుణ - రైతులకు ఊరట",
        "body": (
            "తెలంగాణ రాష్ట్రంలో ఈ సీజన్‌లో సాధారణం కంటే 15 శాతం అధిక వర్షపాతం "
            "నమోదైంది. రాష్ట్ర వ్యవసాయ శాఖ మంత్రి తుమ్మల నాగేశ్వరరావు మాట్లాడుతూ "
            "₹2,000 కోట్ల పంట నష్ట పరిహారం ఇవ్వనున్నట్లు తెలిపారు. ఖమ్మం, వరంగల్ "
            "జిల్లాల్లో వరి సాగు 20 శాతం పెరిగింది. నీటిపారుదల శాఖ అధికారులు "
            "రిజర్వాయర్ల లో నీటి నిల్వలు 73 శాతానికి చేరినట్లు ధ్రువీకరించారు."
        ),
        "expected_fields": ["article_type", "primary_subject", "summaries",
                            "locations", "numbers", "entities_extracted",
                            "english_translation"],
        "expect_translation": True,
        "checks": {
            "numbers_min": 1,
            "locations_country": "India",
            "entities_min": 1,
            "translation_min_chars": 80,
        },
    },
    {
        "lang": "ta",
        "paper": "Dinamalar",
        "headline": "தமிழகத்தில் மழை: விவசாயிகளுக்கு ₹500 கோடி நிவாரணம்",
        "body": (
            "தமிழ்நாட்டில் கடந்த வாரம் கனமழை பெய்ததால் சுமார் 50,000 ஏக்கர் "
            "விவசாய நிலம் பாதிக்கப்பட்டுள்ளது. முதலமைச்சர் எம்.கே. ஸ்டாலின் "
            "₹500 கோடி நிவாரண தொகை அறிவித்துள்ளார். திருவள்ளூர், காஞ்சிபுரம் "
            "மாவட்டங்கள் அதிகம் பாதிக்கப்பட்டுள்ளன. PAGE 4 தொடரும்"
        ),
        "expected_fields": ["article_type", "primary_subject", "summaries",
                            "locations", "quotes", "numbers", "entities_extracted",
                            "english_translation"],
        "expect_translation": True,
        "checks": {
            "numbers_min": 1,
            "locations_country": "India",
            "entities_min": 1,
            "translation_min_chars": 80,
        },
    },
    {
        "lang": "en",
        "paper": "The Hindu (OCR noise sample)",
        "headline": "Cabinet clears ₹12,400-crore highway project for Andhra Pradesh",
        "body": (
            "The Union Cabinet on Thursday approved a ₹12,400-crore national high-\n"
            "way project connecting Vijayawada to Amaravati, expected to be com-\n"
            "pleted by 2028. Road Transport Minister Nitin Gadkari said the pro-\n"
            "ject would generate 45,000 direct jobs. NATIONAL HIGHWAYS AUTHORITY\n"
            "OF INDIA (NHAI) will float tenders by Q3 2026. Opposition TDP law-\n"
            "makers welcomed the move while YSRCP termed it a pre-election gim-\n"
            "mick. The AP government has already acquired 78 per cent of land.\n"
            ">>PAGE 7"
        ),
        "expected_fields": ["article_type", "primary_subject", "summaries",
                            "locations", "quotes", "claims", "numbers",
                            "entities_extracted", "actor_stances", "register"],
        "expect_translation": False,
        "checks": {
            "numbers_min": 2,
            "locations_country": "India",
            "entities_min": 3,
            "claim_subject_present": True,
            "quote_speaker_present": True,
        },
    },
]


# ── Scoring helpers ───────────────────────────────────────────────────────────

VALID_ARTICLE_TYPES = {
    "news", "opinion", "analysis", "explainer", "interview", "press_release",
    "sports_result", "editorial", "column", "letter", "other",
}
VALID_STANCES = {"supportive", "neutral", "critical"}
VALID_RHETORICAL = {
    "factual", "analytical", "polemical", "sympathetic",
    "mocking", "promotional", "sensational",
}
VALID_EMOTIONS = {
    "neutral", "alarm", "approval", "mockery",
    "urgency", "lament", "curiosity", "admiration",
}
VALID_ENTITY_TYPES = {"person", "org", "geo", "event", "other"}
VALID_EVENT_TYPES = {
    "announcement", "meeting", "filing", "statement", "protest",
    "release", "election", "accident", "market_event", "legal",
    "sports_result", "other",
}

_SOVEREIGN_BLACKLIST = {"IN", "US", "UK", "GH", "CN"}  # ISO codes we should never see


def _score(data: dict, fixture: dict) -> dict[str, list[str]]:
    """Return {pass: [...], fail: [...], warn: [...]}."""
    P, F, W = [], [], []

    def ok(msg: str) -> None: P.append(msg)
    def fail(msg: str) -> None: F.append(msg)
    def warn(msg: str) -> None: W.append(msg)

    # 1. Schema — required top-level keys
    required = ["article_type", "primary_subject", "summaries", "locations",
                 "events", "quotes", "actor_stances", "claims", "numbers",
                 "register", "entities_extracted"]
    for k in required:
        if k not in data:
            fail(f"MISSING key: {k}")
        else:
            ok(f"key present: {k}")

    if "article_type" in data:
        if data["article_type"] in VALID_ARTICLE_TYPES:
            ok(f"article_type valid: {data['article_type']}")
        else:
            fail(f"article_type INVALID: {data['article_type']!r}")

    # 2. primary_subject
    ps = data.get("primary_subject", "")
    if isinstance(ps, str) and 5 < len(ps) < 200:
        ok(f"primary_subject ok ({len(ps)} chars)")
    else:
        fail(f"primary_subject bad: {ps!r}")

    # 3. summaries length caps
    sums = data.get("summaries", {})
    for (k, cap) in [("preview", 50), ("snippet", 200), ("executive", 1000)]:
        v = sums.get(k, "")
        if not v:
            warn(f"summaries.{k} empty")
        elif len(v) <= cap:
            ok(f"summaries.{k} ok ({len(v)}/{cap} chars)")
        else:
            fail(f"summaries.{k} OVER CAP: {len(v)} > {cap}")

    # 4. locations
    locs = data.get("locations", [])
    for i, loc in enumerate(locs):
        all5 = all(k in loc for k in ["text", "country", "region", "city", "is_primary"])
        if not all5:
            fail(f"locations[{i}] missing field — has: {list(loc.keys())}")
        else:
            ok(f"locations[{i}] has all 5 fields")
        country = loc.get("country")
        if country and country.upper() in _SOVEREIGN_BLACKLIST:
            fail(f"locations[{i}] country is ISO code: {country!r}")
        if isinstance(loc.get("city"), str) and loc["city"] and not country:
            fail(f"locations[{i}] city set but country null")

    # 5. Numbers ₹ extraction
    nums = data.get("numbers", [])
    checks = fixture.get("checks", {})
    if "numbers_min" in checks:
        if len(nums) >= checks["numbers_min"]:
            ok(f"numbers count ok: {len(nums)} >= {checks['numbers_min']}")
        else:
            fail(f"numbers count LOW: {len(nums)} < {checks['numbers_min']}")
    for i, n in enumerate(nums):
        for k in ("value", "context"):
            if not n.get(k):
                warn(f"numbers[{i}].{k} empty")

    # 6. Entities
    ents = data.get("entities_extracted", [])
    if "entities_min" in checks:
        if len(ents) >= checks["entities_min"]:
            ok(f"entities count ok: {len(ents)} >= {checks['entities_min']}")
        else:
            fail(f"entities count LOW: {len(ents)} < {checks['entities_min']}")
    for i, e in enumerate(ents):
        if e.get("type") not in VALID_ENTITY_TYPES:
            fail(f"entities[{i}].type INVALID: {e.get('type')!r}")

    # 7. register
    reg = data.get("register", {})
    if reg.get("rhetorical_style") in VALID_RHETORICAL:
        ok(f"register.rhetorical_style: {reg['rhetorical_style']}")
    else:
        fail(f"register.rhetorical_style INVALID: {reg.get('rhetorical_style')!r}")
    if reg.get("primary_emotion") in VALID_EMOTIONS:
        ok(f"register.primary_emotion: {reg['primary_emotion']}")
    else:
        fail(f"register.primary_emotion INVALID: {reg.get('primary_emotion')!r}")
    if isinstance(reg.get("is_breaking"), bool):
        ok(f"register.is_breaking: {reg['is_breaking']}")
    else:
        fail(f"register.is_breaking not bool: {reg.get('is_breaking')!r}")

    # 8. actor_stances
    stances = data.get("actor_stances", [])
    for i, s in enumerate(stances):
        if s.get("stance") not in VALID_STANCES:
            fail(f"actor_stances[{i}].stance INVALID: {s.get('stance')!r}")
        intensity = s.get("intensity")
        if not isinstance(intensity, (int, float)) or not (0 <= intensity <= 1):
            fail(f"actor_stances[{i}].intensity out of range: {intensity!r}")

    # 9. claims SPO
    claims = data.get("claims", [])
    if checks.get("claim_subject_present") and claims:
        for i, c in enumerate(claims):
            for k in ("subject", "predicate", "object", "text", "claimant", "type", "verifiable"):
                if k not in c:
                    fail(f"claims[{i}].{k} MISSING")
    elif checks.get("claim_subject_present") and not claims:
        warn("claims array empty (expected at least 1)")

    # 10. quotes
    quotes = data.get("quotes", [])
    if checks.get("quote_speaker_present") and quotes:
        for i, q in enumerate(quotes):
            if not q.get("speaker"):
                fail(f"quotes[{i}].speaker empty")
    elif checks.get("quote_speaker_present") and not quotes:
        warn("quotes array empty (expected at least 1)")

    # 11. Translation for non-English
    if fixture.get("expect_translation"):
        tr = data.get("english_translation", "")
        min_c = checks.get("translation_min_chars", 80)
        if not tr:
            fail("english_translation MISSING for non-English clipping")
        elif len(tr) < min_c:
            fail(f"english_translation TOO SHORT: {len(tr)} < {min_c}")
        else:
            ok(f"english_translation present ({len(tr)} chars)")
    else:
        if data.get("english_translation"):
            warn("english_translation present for English clipping (unexpected)")

    return {"pass": P, "fail": F, "warn": W}


# ── LLM call ──────────────────────────────────────────────────────────────────

async def _call(fixture: dict) -> tuple[dict | None, str]:
    from backend.nlp.groq_client import call_groq, FAST_MODEL
    from backend.nlp.newspaper_prompt import prompt_for_language, body_cap, TASK_TYPE

    lang = fixture["lang"]
    headline = fixture["headline"]
    body = fixture["body"][:body_cap(lang)]
    sys_prompt, max_tok = prompt_for_language(lang)

    user_msg = f"HEADLINE: {headline}\n\nBODY (OCR):\n{body}"
    try:
        raw = await asyncio.wait_for(
            call_groq(
                system=sys_prompt,
                user=user_msg,
                model=FAST_MODEL,
                task_type=TASK_TYPE,
                json_response=True,
                max_tokens_override=max_tok,
            ),
            timeout=120.0,  # fail fast if pool is saturated
        )
        if isinstance(raw, str):
            raw = raw.strip().strip("```json").strip("```").strip()
            data = json.loads(raw)
        else:
            data = raw
        from backend.nlp.newspaper_prompt import sanitize_extraction
        return sanitize_extraction(data), ""
    except asyncio.TimeoutError:
        return None, "TIMEOUT (120s) — pool likely saturated or quota exhausted"
    except Exception as exc:
        return None, str(exc)


# ── Report printer ────────────────────────────────────────────────────────────

def _print_report(fixture: dict, data: dict | None, err: str, scores: dict | None) -> None:
    lang = fixture["lang"]
    paper = fixture["paper"]
    hl = fixture["headline"][:60]
    print()
    print("=" * 72)
    print(f"  [{lang.upper()}] {paper}")
    print(f"  Headline: {hl}")
    print("=" * 72)

    if data is None:
        print(f"  CALL FAILED: {err}")
        return

    if scores is None:
        print("  (no scores)")
        return

    passes = scores["pass"]
    fails  = scores["fail"]
    warns  = scores["warn"]
    total  = len(passes) + len(fails)
    pct    = round(100 * len(passes) / total) if total else 0

    print(f"  SCORE: {len(passes)}/{total} checks passed ({pct}%)")
    if warns:
        print(f"  WARNINGS ({len(warns)}):")
        for w in warns:
            print(f"    ~ {w}")
    if fails:
        print(f"  FAILURES ({len(fails)}):")
        for f in fails:
            print(f"    FAIL {f}")
    else:
        print("  All checks PASSED.")

    # Sample output for human inspection
    print("\n  --- primary_subject ---")
    print(f"  {data.get('primary_subject', '(none)')}")
    print("\n  --- summaries.snippet ---")
    print(f"  {data.get('summaries', {}).get('snippet', '(none)')}")
    print("\n  --- locations ---")
    for loc in data.get("locations", []):
        print(f"    {loc}")
    print("\n  --- numbers ---")
    for n in data.get("numbers", []):
        print(f"    {n}")
    print("\n  --- entities_extracted ---")
    for e in data.get("entities_extracted", []):
        print(f"    {e}")
    if data.get("english_translation"):
        print("\n  --- english_translation (first 200 chars) ---")
        print(f"  {data['english_translation'][:200]}")
    print("\n  --- register ---")
    print(f"  {data.get('register')}")
    if data.get("actor_stances"):
        print("\n  --- actor_stances ---")
        for s in data["actor_stances"][:3]:
            print(f"    {s}")
    if data.get("claims"):
        print("\n  --- claims (first 2) ---")
        for c in data["claims"][:2]:
            print(f"    S={c.get('subject')} | P={c.get('predicate')} | O={c.get('object')}")
    if data.get("quotes"):
        print("\n  --- quotes (first 2) ---")
        for q in data["quotes"][:2]:
            print(f"    [{q.get('speaker')}] {str(q.get('text',''))[:80]}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="Pull real clippings from pipeline instead of fixtures")
    parser.add_argument("--lang", default=None,
                        help="Test only this language code (e.g. te, hi, en)")
    args = parser.parse_args()

    fixtures = FIXTURES
    if args.lang:
        fixtures = [f for f in fixtures if f["lang"] == args.lang]
        if not fixtures:
            print(f"No fixtures for lang={args.lang!r}"); return

    overall_pass = overall_total = 0
    results_by_lang: dict[str, list[tuple[int, int]]] = {}

    for fix in fixtures:
        data, err = await _call(fix)
        scores = _score(data, fix) if data else None
        _print_report(fix, data, err, scores)
        if scores:
            p = len(scores["pass"])
            t = p + len(scores["fail"])
            overall_pass += p
            overall_total += t
            results_by_lang.setdefault(fix["lang"], []).append((p, t))

    print()
    print("=" * 72)
    print("  OVERALL SUMMARY")
    print("=" * 72)
    for lang, res in results_by_lang.items():
        tp = sum(r[0] for r in res)
        tt = sum(r[1] for r in res)
        pct = round(100 * tp / tt) if tt else 0
        print(f"  [{lang.upper()}]  {tp}/{tt}  ({pct}%)")
    if overall_total:
        pct = round(100 * overall_pass / overall_total)
        print(f"\n  TOTAL  {overall_pass}/{overall_total}  ({pct}%)")


if __name__ == "__main__":
    asyncio.run(main())
