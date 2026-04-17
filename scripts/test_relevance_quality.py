"""
Synthetic relevance scoring quality test.
Tests the Stage 1 scoring functions directly — no database, no Groq.
Must pass 5/5 before the Coverage Room frontend is built.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from backend.nlp.relevance_scorer import compute_stage1_score

# ── Test profile ──────────────────────────────────────────────────────────────

TEST_PROFILE = {
    "role_type": "government",
    "geo_primary": "Telangana",
    "geo_secondary": ["Hyderabad", "Nizamabad", "Warangal", "Karimnagar"],
    "signal_priorities": {
        "POLITICS": 9,
        "GOVERNANCE": 9,
        "INFRASTRUCTURE": 8,
        "SECURITY": 6,
        "HEALTH": 5,
        "LEGAL": 5,
        "BUSINESS": 3,
        "FINANCE": 3,
        "INTERNATIONAL": 4,
        "TECHNOLOGY": 4,
        "AGRICULTURE": 7,
        "ENVIRONMENT": 5,
        "SOCIAL": 4,
        "SPORTS": 1,
        "OTHER": 2,
    },
    "role_context": "Chief Minister of Telangana state government.",
}

TEST_ENTITIES = [
    {"canonical_name": "A. Revanth Reddy", "priority": 10},
    {"canonical_name": "Kaleshwaram Lift Irrigation Scheme", "priority": 9},
    {"canonical_name": "K. Chandrashekar Rao", "priority": 9},
    {"canonical_name": "GHMC", "priority": 7},
    {"canonical_name": "Telangana", "priority": 8},
]

TEST_SOURCE_TELANGANA = {"geo_states": ["Telangana", "India"], "source_tier": 2}
TEST_SOURCE_NATIONAL = {"geo_states": ["India"], "source_tier": 2}
TEST_SOURCE_GLOBAL = {"geo_states": ["global"], "source_tier": 2}

# ── Test cases ────────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "name": "High relevance Telangana",
        "article": {
            "title": "CM Revanth Reddy inaugurates Kaleshwaram reservoir in Nizamabad",
            "lead_text_translated": (
                "Chief Minister A. Revanth Reddy today inaugurated the "
                "Kaleshwaram Lift Irrigation Scheme reservoir in Nizamabad "
                "district. The project benefits farmers across Telangana. "
                "GHMC officials attended the ceremony."
            ),
            "topic_category": "GOVERNANCE",
            "geo_primary": "Nizamabad",
            "source_tier": TEST_SOURCE_TELANGANA["source_tier"],
            "entities_extracted": [
                {"name": "A. Revanth Reddy", "type": "person", "prominence": 0.9},
                {
                    "name": "Kaleshwaram Lift Irrigation Scheme",
                    "type": "scheme",
                    "prominence": 0.8,
                },
                {"name": "GHMC", "type": "organisation", "prominence": 0.4},
            ],
            "nlp_confidence": "normal",
        },
        "source_geo": TEST_SOURCE_TELANGANA["geo_states"],
        "expected_label": ">= 0.50 (Tier 1)",
        "pass_fn": lambda s: s >= 0.50,
    },
    {
        "name": "Medium relevance national — different state politics",
        "article": {
            "title": "BJP wins seats in Karnataka local body polls",
            "lead_text_translated": (
                "BJP won multiple seats in Karnataka local body elections. "
                "The party is expanding its presence in southern states."
            ),
            "topic_category": "POLITICS",
            "geo_primary": "Karnataka",
            "source_tier": TEST_SOURCE_NATIONAL["source_tier"],
            "entities_extracted": [],
            "nlp_confidence": "normal",
        },
        "source_geo": TEST_SOURCE_NATIONAL["geo_states"],
        # No Telangana/Hyderabad mention anywhere → geo_multiplier = 0.4
        # base = 0.25×0.9 + 0.15×0.7 = 0.33 → final = 0.33×0.4 + 0.05 = 0.182
        "expected_label": "0.10 <= score < 0.50 (Tier 2/3)",
        "pass_fn": lambda s: 0.10 <= s < 0.50,
    },
    {
        "name": "Sports blocked by gate",
        "article": {
            "title": "India vs Australia cricket Test match preview",
            "lead_text_translated": (
                "The Indian cricket team faces Australia. "
                "Several Telangana players in squad."
            ),
            "topic_category": "SPORTS",
            "geo_primary": None,
            "source_tier": TEST_SOURCE_NATIONAL["source_tier"],
            "entities_extracted": [],
            "nlp_confidence": "normal",
        },
        "source_geo": TEST_SOURCE_NATIONAL["geo_states"],
        "expected_label": "< 0.10 (SPORTS gate)",
        "pass_fn": lambda s: s < 0.10,
    },
    {
        "name": "Hungarian elections — zero relevance",
        "article": {
            "title": "Hungarian elections: Orban wins fourth term",
            "lead_text_translated": (
                "Viktor Orban won the Hungarian election. Results from Budapest."
            ),
            "topic_category": "INTERNATIONAL",
            "geo_primary": "Budapest",
            "source_tier": TEST_SOURCE_GLOBAL["source_tier"],
            "entities_extracted": [],
            "nlp_confidence": "normal",
        },
        "source_geo": TEST_SOURCE_GLOBAL["geo_states"],
        # Formula floor: (0.25×0.4 + 0.15×0.7) × 0.4 = 0.082
        # Below Tier 3 threshold (0.10) → not stored → system is correct
        "expected_label": "< 0.10 (not stored — below Tier 3)",
        "pass_fn": lambda s: s < 0.10,
    },
    {
        "name": "National article — Telangana in body only",
        "article": {
            "title": "National BJP strategy for upcoming state elections",
            "lead_text_translated": (
                "BJP is planning its strategy for elections in Telangana, "
                "Karnataka, and Rajasthan. KCR responded to BJP announcement."
            ),
            "topic_category": "POLITICS",
            "geo_primary": None,
            "source_tier": TEST_SOURCE_NATIONAL["source_tier"],
            "entities_extracted": [
                {
                    "name": "K. Chandrashekar Rao",
                    "type": "person",
                    "prominence": 0.3,
                },
            ],
            "nlp_confidence": "normal",
        },
        "source_geo": TEST_SOURCE_NATIONAL["geo_states"],
        # "Telangana" in body → geo_multiplier = 1.0 (not 0.4)
        # POLITICS priority 9 + KCR entity → genuinely Tier 2 for Telangana CM
        # Correctly not Tier 1 (no watched entity in title, not in primary geo)
        "expected_label": "0.25 <= score < 0.50 (Tier 2 — body-only Telangana + KCR)",
        "pass_fn": lambda s: 0.25 <= s < 0.50,
    },
]

# ── Runner ────────────────────────────────────────────────────────────────────


def run_tests() -> int:
    passed = 0

    for i, tc in enumerate(TEST_CASES, start=1):
        score, debug = compute_stage1_score(
            article=tc["article"],
            user_profile=TEST_PROFILE,
            user_entities=TEST_ENTITIES,
            source_geo_states=tc["source_geo"],
        )

        ok = tc["pass_fn"](score)
        status = "PASS" if ok else "FAIL"

        print(
            f"[TEST {i}] {tc['name']}\n"
            f"  Entity:{debug['entity_score']:.3f} | "
            f"Topic:{debug['topic_score']:.3f} | "
            f"Geo:{debug['geo_score']:.3f} | "
            f"Source:{debug['source_score']:.3f} | "
            f"Gate:{debug['topic_gate']} | "
            f"Mult:{debug['geo_multiplier']} | "
            f"Bonus:{debug['source_bonus']} | "
            f"Base:{debug['base']:.3f} | "
            f"Final:{score:.3f} | "
            f"Expected:{tc['expected_label']} | {status}"
        )

        if not ok:
            print(
                f"  !! FAILURE: score={score:.4f} did not satisfy "
                f"condition for '{tc['expected_label']}'\n"
                f"  Debug breakdown: {debug}"
            )
        else:
            passed += 1

    print(f"\nRelevance quality test: {passed}/5 passed")
    return passed


if __name__ == "__main__":
    result = run_tests()
    sys.exit(0 if result == 5 else 1)
