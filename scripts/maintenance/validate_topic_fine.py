#!/usr/bin/env python3
"""
Validate the topic_fine classifier (migration 084) on real OTHER-pile
titles BEFORE deploying it.

Reads TSV from stdin, one row per article:  <id>\x1f<text>
For each, runs the NEW 25-bucket / don't-hedge prompt and reports:
  * the distribution of resulting labels
  * a per-article sample (was OTHER -> now <label>)
  * the % still landing in OTHER (the "rescue rate" is 100 - that)

The prompt here MIRRORS backend/nlp/nlp_topic.classify_topic_fine so we
can test it inside the running container without redeploying code.

Run (cloud-only, so it never hangs on the offline local LLM slots):
  cat titles.tsv | docker exec -e LOCAL_LLM_ENABLED=0 -i rig-backend \
      python3 /tmp/validate_topic_fine.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter

sys.path.insert(0, "/app")
os.environ.setdefault("LOCAL_LLM_ENABLED", "0")

VALID_TOPICS_FINE = frozenset({
    "POLITICS", "GOVERNANCE", "BUSINESS", "FINANCE", "INFRASTRUCTURE",
    "SECURITY", "HEALTH", "LEGAL", "AGRICULTURE", "INTERNATIONAL",
    "TECHNOLOGY", "ENVIRONMENT", "SOCIAL", "SPORTS", "OTHER",
    "WELFARE", "DEFENCE", "CRIME", "EDUCATION", "DISASTER",
    "SCIENCE", "ENTERTAINMENT", "RELIGION", "LIFESTYLE", "OBITUARY",
})

_SYSTEM_PROMPT_FINE = (
    "/no_think\n"
    "You are a precise news topic classifier for Indian and international "
    "news. Classify the article into EXACTLY ONE category from the list "
    "below. Choose the single best-fitting category. Use OTHER ONLY when "
    "genuinely nothing else fits — never choose OTHER out of uncertainty. "
    "Reply with ONLY the category name in uppercase. No punctuation, no "
    "explanation.\n\n"
    "Categories:\n"
    "POLITICS - party politics, elections, legislators, govt formation\n"
    "GOVERNANCE - policy, administration, bureaucracy, govt programs\n"
    "WELFARE - ration, pensions, subsidies, scholarships, welfare schemes\n"
    "BUSINESS - companies, corporate deals, industry, trade\n"
    "FINANCE - stocks, banking, earnings, RBI, mutual funds, economy\n"
    "INFRASTRUCTURE - roads, rail, metro, power, water, construction\n"
    "SECURITY - military ops, terrorism, border, internal security\n"
    "DEFENCE - armed forces, weapons, defence deals, military exercises\n"
    "CRIME - murder, theft, fraud, arrests, police cases\n"
    "LEGAL - court judgments, litigation, judiciary, constitutional law\n"
    "HEALTH - disease, hospitals, medicine, public health\n"
    "EDUCATION - schools, universities, exams, results, admissions\n"
    "AGRICULTURE - farming, crops, farmers, MSP, irrigation\n"
    "ENVIRONMENT - climate, pollution, wildlife, forests, conservation\n"
    "DISASTER - floods, earthquakes, accidents, fires, cyclones, rescue\n"
    "TECHNOLOGY - IT, software, AI, gadgets, internet, startups\n"
    "SCIENCE - research, space, ISRO, discoveries, scientific studies\n"
    "INTERNATIONAL - foreign affairs, diplomacy, world events\n"
    "SPORTS - cricket, football, IPL, tournaments, athletes\n"
    "ENTERTAINMENT - films, music, celebrities, OTT, TV, cinema\n"
    "RELIGION - temples, festivals, religious events, faith\n"
    "SOCIAL - society, caste, gender, communities, human interest\n"
    "LIFESTYLE - food, travel, fashion, wellness, culture\n"
    "OBITUARY - deaths, tributes, passing of notable people\n"
    "OTHER - genuinely none of the above\n\n"
    "Examples:\n"
    "Title: IPL 2026: RCB beat CSK by 5 wickets => SPORTS\n"
    "Title: State govt launches new ration card scheme for poor families => WELFARE\n"
    "Title: Top actor's new film crosses 100 crore at box office => ENTERTAINMENT\n"
    "Title: Group-1 exam results declared, cutoffs released => EDUCATION\n"
    "Title: Three killed as car rams truck on highway => DISASTER\n"
    "Title: Man arrested for ATM card fraud => CRIME\n"
    "Title: Temple festival draws lakhs of devotees => RELIGION\n"
)


def _coerce(reply: str) -> str:
    topic = (reply or "").strip().upper()
    if topic in VALID_TOPICS_FINE:
        return topic
    matches = sorted(
        (v for v in VALID_TOPICS_FINE if v in topic), key=len, reverse=True
    )
    return matches[0] if matches else "OTHER"


async def _classify_one(text: str) -> str:
    from backend.nlp.groq_client import classify
    try:
        reply = await classify(
            system=_SYSTEM_PROMPT_FINE, user=f"Title: {text[:500]}"
        )
        return _coerce(reply)
    except Exception as exc:  # noqa: BLE001
        return f"ERR:{str(exc)[:30]}"


async def _main() -> None:
    # Force cloud-only before the pool is built (offline Trijya = hang).
    import backend.nlp.groq_client as gc
    gc._LOCAL_LLM_ENABLED = False
    gc._unified_pool_singleton = None

    rows: list[str] = [ln.rstrip("\n") for ln in sys.stdin if ln.strip()]
    texts: list[str] = []
    for ln in rows:
        parts = ln.split("\x1f", 1)
        texts.append(parts[1] if len(parts) > 1 else parts[0])

    sem = asyncio.Semaphore(6)

    async def worker(t: str) -> tuple[str, str]:
        async with sem:
            label = await _classify_one(t)
        return label, t[:72]

    results = await asyncio.gather(*(worker(t) for t in texts))

    dist = Counter(lbl for lbl, _ in results)
    n = len(results)
    still_other = dist.get("OTHER", 0)
    print(f"=== topic_fine validation on {n} real OTHER-pile articles ===")
    print(f"rescued out of OTHER: {n - still_other}/{n} "
          f"({100 * (n - still_other) // max(n, 1)}%)\n")
    print("--- new-label distribution ---")
    for lbl, c in dist.most_common():
        print(f"{c:4d}  {lbl}")
    print("\n--- samples (OTHER -> new) ---")
    for lbl, txt in sorted(results):
        print(f"{lbl:<14} {txt}")


if __name__ == "__main__":
    asyncio.run(_main())
