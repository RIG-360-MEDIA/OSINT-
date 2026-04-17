"""
5-article synthetic NLP quality gate.

Tests all 4 pipeline steps against known-good inputs WITHOUT hitting the database.
All 5 must pass before P07 relevance scoring is written.

Run: python scripts/test_nlp_quality.py
"""
from __future__ import annotations

import asyncio
import sys
import os

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Synthetic articles ─────────────────────────────────────────────────────────

ARTICLES = [
    {
        "id": 1,
        "title": "CM Revanth Reddy inaugurates Kaleshwaram reservoir in Nizamabad district",
        "text": (
            "Chief Minister A. Revanth Reddy today inaugurated the Kaleshwaram Lift "
            "Irrigation Scheme reservoir in Nizamabad district. The project benefits "
            "farmers across Telangana. GHMC officials attended the ceremony."
        ),
        "lang_expected": "en",
        "entities_must_include_one_of": ["A. Revanth Reddy", "Kaleshwaram Lift Irrigation Scheme"],
        "topic_expected_in": {"POLITICS", "GOVERNANCE", "INFRASTRUCTURE"},
        "geo_expected_in": {"Nizamabad", "Telangana"},
        "label": "TEST 1",
    },
    {
        "id": 2,
        "title": "కాళేశ్వరం ప్రాజెక్టు",
        "text": "ముఖ్యమంత్రి రేవంత్ రెడ్డి కాళేశ్వరం ప్రాజెక్టు ప్రారంభించారు",
        "lang_expected": "te",
        "translation_keywords": ["kaleshwaram", "chief minister", "revanth"],
        "label": "TEST 2",
    },
    {
        "id": 3,
        "title": "India vs Australia cricket Test match preview",
        "text": (
            "The Indian cricket team faces Australia in the second Test match in Melbourne. "
            "Several players from Telangana are in the squad."
        ),
        "topic_expected": "SPORTS",
        "label": "TEST 3",
    },
    {
        "id": 4,
        "title": "Hungarian elections: Viktor Orban wins fourth term",
        "text": (
            "Viktor Orban has won a fourth consecutive term as Hungarian Prime Minister. "
            "The election took place in Budapest."
        ),
        "topic_expected_in": {"INTERNATIONAL", "POLITICS"},
        "geo_must_not_be": {"India", "Telangana"},
        "entities_must_not_include_types": ["Telangana"],
        "label": "TEST 4",
    },
    {
        "id": 5,
        "title": "BJP wins municipal seats in Hyderabad",
        "text": (
            "BJP won three seats in the Hyderabad municipal corporation polls today. "
            "The party has been strengthening its presence. "
            "KCR commented on the results. Revanth Reddy also responded."
        ),
        "geo_expected_in": {"Hyderabad", "Telangana"},
        "min_prominence": 0.5,
        "label": "TEST 5",
    },
]


async def run_tests() -> None:
    import spacy
    from backend.database import get_db
    from backend.nlp.nlp_embedding import generate_embedding
    from backend.nlp.nlp_entities import _ENTITY_DICT, extract_entities, load_entity_dictionary
    from backend.nlp.nlp_geo import tag_geography
    from backend.nlp.nlp_language import detect_and_translate
    from backend.nlp.nlp_topic import classify_topic

    # Load entity dictionary from DB — required for entity extraction and prominence scoring
    async with get_db() as db:
        n_keys = await load_entity_dictionary(db)
    print(f"Entity dictionary: {n_keys} lookup keys loaded\n")

    nlp_model = spacy.load("en_core_web_sm")

    passed = 0
    failed = 0

    # ── TEST 1 ────────────────────────────────────────────────────────────────
    a = ARTICLES[0]
    lang, translated = await detect_and_translate(a["text"], a["title"])
    entities = extract_entities(a["title"], translated, nlp_model)
    topic = await classify_topic(a["title"], translated)
    geo, _ = await tag_geography(a["title"], translated, entities)
    entity_names = [e["name"] for e in entities]

    ok_lang = lang == a["lang_expected"]
    ok_entity = any(e in entity_names for e in a["entities_must_include_one_of"])
    ok_topic = topic in a["topic_expected_in"]
    ok_geo = geo in a["geo_expected_in"] if geo else False
    t1_pass = ok_lang and ok_entity and ok_topic and ok_geo

    entity_hit = next((e for e in a["entities_must_include_one_of"] if e in entity_names), "NONE")
    status = "PASS" if t1_pass else "FAIL"
    print(
        f"[{a['label']}] Lang:{lang} | Entity:{entity_hit} | "
        f"Topic:{topic} | Geo:{geo} | {status}"
    )
    if not t1_pass:
        if not ok_lang:
            print(f"  FAIL reason: lang={lang!r} expected {a['lang_expected']!r}")
        if not ok_entity:
            print(f"  FAIL reason: no target entity in {entity_names[:5]}")
        if not ok_topic:
            print(f"  FAIL reason: topic={topic!r} not in {a['topic_expected_in']}")
        if not ok_geo:
            print(f"  FAIL reason: geo={geo!r} not in {a['geo_expected_in']}")
    passed += t1_pass
    failed += not t1_pass

    # ── TEST 2 ────────────────────────────────────────────────────────────────
    a = ARTICLES[1]
    lang, translated = await detect_and_translate(a["text"], a["title"])
    ok_lang = lang == a["lang_expected"]
    ok_translation = (
        translated
        and any(kw in translated.lower() for kw in a["translation_keywords"])
    )
    t2_pass = ok_lang and ok_translation

    status = "PASS" if t2_pass else "FAIL"
    trans_preview = (translated or "")[:60]
    print(f"[{a['label']}] Lang:{lang} | Translation:{trans_preview!r} | {status}")
    if not t2_pass:
        if not ok_lang:
            print(f"  FAIL reason: lang={lang!r} expected {a['lang_expected']!r}")
        if not ok_translation:
            print(f"  FAIL reason: no keyword {a['translation_keywords']} in translation")
    passed += t2_pass
    failed += not t2_pass

    # ── TEST 3 ────────────────────────────────────────────────────────────────
    a = ARTICLES[2]
    lang, translated = await detect_and_translate(a["text"], a["title"])
    topic = await classify_topic(a["title"], translated)
    t3_pass = topic == a["topic_expected"]

    status = "PASS" if t3_pass else "FAIL"
    print(f"[{a['label']}] Topic:{topic} | {status}")
    if not t3_pass:
        print(f"  FAIL reason: topic={topic!r} expected {a['topic_expected']!r}")
    passed += t3_pass
    failed += not t3_pass

    # ── TEST 4 ────────────────────────────────────────────────────────────────
    a = ARTICLES[3]
    lang, translated = await detect_and_translate(a["text"], a["title"])
    entities = extract_entities(a["title"], translated, nlp_model)
    topic = await classify_topic(a["title"], translated)
    geo, _ = await tag_geography(a["title"], translated, entities)

    ok_topic = topic in a["topic_expected_in"]
    ok_geo = geo not in a["geo_must_not_be"] if geo else True
    entity_states = [e.get("state") for e in entities]
    ok_entities = "Telangana" not in entity_states
    t4_pass = ok_topic and ok_geo and ok_entities

    status = "PASS" if t4_pass else "FAIL"
    print(
        f"[{a['label']}] Topic:{topic} | Geo:{geo!r} | "
        f"No Indian entities:{'✓' if ok_entities else '✗'} | {status}"
    )
    if not t4_pass:
        if not ok_topic:
            print(f"  FAIL reason: topic={topic!r} not in {a['topic_expected_in']}")
        if not ok_geo:
            print(f"  FAIL reason: geo={geo!r} is in forbidden set {a['geo_must_not_be']}")
        if not ok_entities:
            print(f"  FAIL reason: Indian entity found in {[e['name'] for e in entities]}")
    passed += t4_pass
    failed += not t4_pass

    # ── TEST 5 ────────────────────────────────────────────────────────────────
    a = ARTICLES[4]
    lang, translated = await detect_and_translate(a["text"], a["title"])
    entities = extract_entities(a["title"], translated, nlp_model)
    geo, _ = await tag_geography(a["title"], translated, entities)

    ok_geo = geo in a["geo_expected_in"] if geo else False
    top_prominence = max((e["prominence"] for e in entities), default=0.0)
    ok_prominence = top_prominence >= a["min_prominence"]
    t5_pass = ok_geo and ok_prominence

    status = "PASS" if t5_pass else "FAIL"
    print(
        f"[{a['label']}] Geo:{geo!r} | "
        f"Top prominence:{top_prominence:.2f} | {status}"
    )
    if not t5_pass:
        if not ok_geo:
            print(f"  FAIL reason: geo={geo!r} not in {a['geo_expected_in']}")
        if not ok_prominence:
            print(f"  FAIL reason: max prominence {top_prominence:.2f} < {a['min_prominence']}")
    passed += t5_pass
    failed += not t5_pass

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    if passed == 5:
        print("NLP quality test: 5/5 passed. Ready for P07 relevance scoring.")
    else:
        print(f"NLP quality test: {passed}/5 passed. {failed} test(s) failed — fix before P07.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_tests())
