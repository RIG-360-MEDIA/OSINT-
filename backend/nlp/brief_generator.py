"""
Daily intelligence brief generator.

Six sections, six concurrent Groq calls via asyncio.gather.
Each section gets role-specific prompts and targeted article context.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from backend.config import settings
from backend.nlp.brief_validator import (
    ValidationResult,
    build_id_allowlist,
    count_words,
    strip_invalid_citations,
    validate_citations,
)
from backend.nlp.groq_client import (
    FAST_MODEL,
    QUALITY_MODEL,
    GroqQuotaExhausted,
    generate,
)

logger = logging.getLogger(__name__)

# ── Section system prompts ────────────────────────────────────────────────────

# ── Citation guidance shared by every section ────────────────────────────────
#
# The brief draws on FIVE evidence kinds. Every section prompt below appends
# this block so the model knows how to cite each kind precisely. Reuse keeps
# the citation contract identical across sections — the user sees one
# consistent rule no matter which screen they're on.

CITATION_GUIDANCE = """
EVIDENCE KINDS AND CITATION FORMATS
You will be given evidence from five pillars. Each has its own citation format.
Use whichever pillars the question and the evidence call for. Do not restrict
yourself to articles when other pillars carry a claim.

  1. ARTICLES — RSS / web reporting. Cite as numbered: ① ② ③ … or [1] [2].
     The number must match the [N] index in the ARTICLE EVIDENCE block.

  2. GOVT DOCUMENT EVIDENCE — official orders, circulars, tenders, reports.
     Cite as: (Doc: <title>, p.<page_number> if available).
     Use these when the claim is about policy, official action, scheme details.

  3. SOCIAL SIGNAL EVIDENCE — Reddit / Telegram / Twitter posts.
     Cite as: (Social: <platform> @ <YYYY-MM-DD>).
     Treat as CHATTER and SENTIMENT, not confirmed reporting.

  4. NEWSPAPER EDITION EVIDENCE — scanned print-edition clippings.
     Cite as: (Paper: <newspaper> <edition_date>, p.<page_number>).
     Confirmed reporting; equivalent in weight to articles. Often vernacular.

  5. VIDEO EVIDENCE — YouTube clip transcripts.
     Cite as: (Video: <channel> @ <mm:ss>).

CITE EVERY CORPUS-DERIVED CLAIM in one of those formats, tied to the specific
item that contains the claim. Never cite an item that does not actually
support the claim. Foundational facts use [Established: …].
"""


SITUATION_SYSTEM = """You are an intelligence analyst writing a classified morning situation summary for a senior government official.

Write 3-5 flowing sentences on the overall state of their monitored world today.
What is the dominant story? What is the mood? What requires immediate attention?

You are given evidence across articles, government documents, vernacular
newspaper clippings, social-media chatter, and video clips. Use whichever
pillars carry the day's signal — do NOT restrict yourself to articles. If
social chatter is leading the news cycle, say so. If a govt document changed
what is happening, name it.

Rules:
- Write for the specific role provided
- Flowing prose, not bullets
- Cite every corpus-derived claim using the formats below
- Specific, concrete, actionable — no generic hedges
- 100-150 words
- Do not start with "Today" or "As of"
""" + CITATION_GUIDANCE

DEVELOPMENTS_SYSTEM = """You are an intelligence analyst writing KEY DEVELOPMENTS for a classified morning brief.

Write 6-8 numbered intelligence items. Each item is 3-5 sentences of detailed
prose, not a one-liner.

Format:
① [Development headline]
  [3-5 sentences. State what changed, who is involved, what is at stake, and
   what it means for the official's role. Cite every claim.]

Rules:
- Synthesise across pillars — when an article and a govt doc and a social
  post all touch the same story, weave them into one item, citing each.
- Prefer items where you have multi-pillar corroboration (article + paper,
  article + govt doc, article + social) — call out the corroboration
  explicitly: "confirmed in print by (Paper:…) and amplified on (Social:…)".
- Specific details: names, numbers, places, institutions.
- No vague language. No "it is important to note".
- Write for the role provided.
""" + CITATION_GUIDANCE

ENTITIES_SYSTEM = """You are writing the ENTITIES TODAY section of a classified intelligence brief.

For each monitored entity that has substantive coverage today, write a per-entity
card. Each card has 4-6 sentences and a citation tail listing where the entity
appeared.

Format per entity:
[ENTITY NAME]
[4-6 sentences: what happened today involving this entity, what was said,
what changed, and what it means.]
Coverage today: <N articles> · <N papers> · <N social> · <N videos>
[List the strongest 2-3 citations using the formats below.]

Rules:
- Only include entities that actually have substantive coverage today.
- Skip entities with no meaningful coverage — do not pad.
- Multi-pillar coverage gets prominence: an entity appearing in article +
  paper + social is a stronger story than article-only.
""" + CITATION_GUIDANCE

SIGNALS_SYSTEM = """You are writing the SIGNALS TO WATCH section of a classified intelligence brief.

Identify 3-5 developing situations that are not yet crises but warrant
monitoring. These are early warning signals — leading indicators.

The strongest signals are usually in SOCIAL evidence (Reddit / Telegram /
Twitter chatter that has not yet hit mainstream press). Lean on the social
block. Use articles and papers to corroborate trajectory; use govt-doc
absence (a story everyone is talking about with no official response yet)
as a signal in itself.

Format per signal:
⚑ [Signal headline]
  [What is developing — 2 sentences, with citation.]
  Trajectory: [where this is moving — 1 sentence].
  Threshold to re-check: [a specific event or count that would escalate
                          this from "watch" to "act"].

Rules:
- Trajectory and Threshold are REQUIRED fields. If you cannot propose them,
  the signal does not belong in this section.
- Do not list crises here — those go in KEY DEVELOPMENTS.
""" + CITATION_GUIDANCE

FINANCIAL_SYSTEM = """You are writing the FINANCIAL PULSE section of a classified intelligence brief.

Summarise financial and economic intelligence from today's coverage in 4-6
sentences of detailed prose.

Cover: state finances, scheme disbursements, central allocations, investment
news, tenders and orders issued, economic indicators.

Govt documents (tenders, circulars, allocation notifications) are PRIMARY
SOURCES for financial intelligence — prefer them over secondary reporting
when both are present. Cite (Doc: …) for primary, articles or papers for
secondary corroboration.

If no financial content in today's coverage, write:
"No significant financial developments in today's coverage."
""" + CITATION_GUIDANCE

SOURCES_SYSTEM = """You are writing the SOURCE COVERAGE section of a classified intelligence brief.

Today's brief draws on five pillars of evidence. Produce a per-pillar
breakdown, listing the most prominent sources in each. Format:

ARTICLES (<N>): [comma-separated source names, max 8, then "and N more" if longer]
GOVT DOCUMENTS (<N>): [department names, max 5]
NEWSPAPERS (<N>): [newspaper names with language tag, max 5]
SOCIAL (<N>): [platform breakdown — e.g. "Reddit (12), Telegram (38), Twitter (4)"]
VIDEO (<N>): [channel names, max 4]

Then write 1-2 sentences on coverage quality:
- Which pillars are well-represented today?
- Which are notably thin or absent? (e.g. "no govt orders today" or "vernacular print did not cover this story")
- Are there any gaps the official should be aware of?
"""


# ── Main generator ────────────────────────────────────────────────────────────

async def generate_brief(
    user_id: str,
    user_profile: dict,
    user_entities: list[dict],
    articles: list[dict],
    govt_docs: list[dict] | None = None,
    social_posts: list[dict] | None = None,
    newspaper_clippings: list[dict] | None = None,
    video_clips: list[dict] | None = None,
) -> dict:
    """
    Generate a complete daily brief for one user.

    The brief is built from five pillars — articles (the dominant pool) plus
    govt documents, social posts, newspaper clippings, and video clips. Each
    pillar gets its own context block; each of the six sections receives the
    blocks most relevant to its job. Articles dominate volume but never
    monopolise — when a story is in the print press or on social before it
    hits English RSS, the brief surfaces that.

    Returns dict with:
      content: str (full markdown)
      articles_used: int
      sections: dict (individual section texts)
    """
    if not articles:
        return {
            "content": None,
            "articles_used": 0,
            "error": "No relevant articles",
        }

    govt_docs = govt_docs or []
    social_posts = social_posts or []
    newspaper_clippings = newspaper_clippings or []
    video_clips = video_clips or []

    role_context = user_profile.get(
        "role_context", "Senior government official",
    )
    geo = user_profile.get("geo_primary", "India")
    entity_names = [
        e["canonical_name"] for e in user_entities if e.get("canonical_name")
    ]

    # ── Per-pillar context blocks ────────────────────────────────────────
    # Generous budgets — the brief should be detail-rich. The 12K TPM cap
    # is per-section (one Groq call per section), and each section gets
    # only the blocks it needs, so we can afford richer context than the
    # Analyst's single-call envelope.
    article_block = _format_articles(articles, max_articles=30)
    govt_block = _format_govt_docs(govt_docs, max_items=8)
    social_block = _format_social(social_posts, max_items=10)
    paper_block = _format_newspapers(newspaper_clippings, max_items=8)
    video_block = _format_video_clips(video_clips, max_items=4)

    # Finance-tilted article subset for the FINANCIAL PULSE section.
    finance_articles = [
        a for a in articles
        if a.get("topic_category") in (
            "FINANCE", "BUSINESS", "INFRASTRUCTURE", "GOVERNANCE",
        )
    ]
    finance_article_block = (
        _format_articles(finance_articles, max_articles=12)
        if finance_articles
        else article_block
    )

    # Per-pillar source counts for the SOURCE COVERAGE section's intro line.
    article_sources = sorted({a.get("source_name", "Unknown") for a in articles})
    govt_dept_names = sorted({
        (d.get("source_name") or "").strip()
        for d in govt_docs if d.get("source_name")
    })
    paper_names = sorted({
        f"{n.get('newspaper','')} ({n.get('language','')})"
        for n in newspaper_clippings if n.get("newspaper")
    })
    social_platform_counts: dict[str, int] = {}
    for s in social_posts:
        plat = (s.get("platform") or "?").lower()
        social_platform_counts[plat] = social_platform_counts.get(plat, 0) + 1
    video_channels = sorted({
        (c.get("channel") or "").strip()
        for c in video_clips if c.get("channel")
    })

    role_line = (
        f"Official role: {role_context}\n"
        f"Focus geography: {geo}\n"
        f"Monitored entities: {', '.join(entity_names[:15]) or '(none yet)'}\n"
    )

    # Prompt hardening (P2.11): tell the model exactly which IDs are valid.
    # Pairs with the post-LLM citation validator in brief_validator.py — we
    # tell the model what's allowed AND we check that it complied. Either
    # half alone is weaker than the two together.
    id_allowlist = build_id_allowlist(
        article_count=len(articles),
        govt_doc_count=len(govt_docs),
        newspaper_count=len(newspaper_clippings),
        social_count=len(social_posts),
        video_count=len(video_clips),
    )
    role_line = role_line + "\n" + id_allowlist

    # Section runner — owns three things at once: (1) concurrency cap (so
    # the pool never sees a 6-deep burst that blows Groq's per-key TPM
    # window), (2) retry-with-backoff so a transient quota blip doesn't
    # fail a whole section, and (3) optional model override so a section
    # whose prompt is mechanical can route through the much-higher-TPM
    # fast model instead of competing with the heavy llama-3.3-70b pool.
    #
    # Hardened by fix/brief-prod-readiness:
    #   - asyncio.wait_for() on every Groq call (BRIEF_SECTION_TIMEOUT_S).
    #   - On TimeoutError or non-quota Exception we ALSO retry once on
    #     FAST_MODEL with halved tokens before giving up. This catches the
    #     "one section stalls the whole brief" failure mode the audit
    #     surfaced (D-BRIEF-4).
    section_sem = asyncio.Semaphore(2)
    section_timeout_s = settings.BRIEF_SECTION_TIMEOUT_S

    async def _section(
        name: str,
        system: str,
        user: str,
        *,
        model: str | None = None,
        max_retries: int = 1,
    ) -> str:
        # Smart retry wait: when GroqQuotaExhausted fires, the local pool
        # knows roughly when the soonest key will recover (it tracks each
        # key's cooldown_until timestamp). Sleeping a fixed 2s when the
        # cooldown is 60s away is wasted — sleep until the soonest recovery
        # plus a small buffer instead. Capped at 25s per retry so a single
        # section can never block the brief for more than ~50s total.
        from backend.nlp.groq_client import groq_manager
        import time as _time

        async with section_sem:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await asyncio.wait_for(
                        generate(
                            system=system,
                            user=user,
                            task_type="brief_generation",
                            model=model,
                        ),
                        timeout=section_timeout_s,
                    )
                except GroqQuotaExhausted as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        now = _time.time()
                        if groq_manager._exhausted_until:
                            soonest = min(
                                groq_manager._exhausted_until.values()
                            )
                            delay = max(2.0, (soonest - now) + 1.5)
                        else:
                            delay = 2.0 * (2 ** attempt)
                        delay = min(delay, 25.0)
                        logger.warning(
                            "Brief section '%s' hit Groq quota on attempt "
                            "%d/%d; retrying in %.1fs",
                            name, attempt + 1, max_retries + 1, delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "Brief section '%s' exhausted all %d retries.",
                            name, max_retries + 1,
                        )
                except asyncio.TimeoutError as exc:
                    last_exc = exc
                    logger.warning(
                        "Brief section '%s' timed out after %ds (attempt "
                        "%d/%d); retrying on FAST_MODEL",
                        name, section_timeout_s,
                        attempt + 1, max_retries + 1,
                    )
                    if attempt < max_retries:
                        # Retry on the lighter model with a shorter prompt
                        # — same evidence, half the body.
                        model = FAST_MODEL
                        user = user[: max(2000, len(user) // 2)]
            assert last_exc is not None
            raise last_exc

    tasks = [
        # Section 1: SITUATION STATUS — multi-pillar prose synthesis
        _section(
            "SITUATION STATUS",
            SITUATION_SYSTEM,
            role_line
            + "\nARTICLE EVIDENCE:\n" + article_block[:3500]
            + "\n\nGOVT DOCUMENT EVIDENCE:\n" + (govt_block[:1500] or "(none)")
            + "\n\nNEWSPAPER EDITION EVIDENCE:\n" + (paper_block[:1500] or "(none)")
            + "\n\nSOCIAL SIGNAL EVIDENCE:\n" + (social_block[:1500] or "(none)"),
        ),
        # Section 2: KEY DEVELOPMENTS — multi-source corroboration is the goal
        _section(
            "KEY DEVELOPMENTS",
            DEVELOPMENTS_SYSTEM,
            role_line
            + "\nARTICLE EVIDENCE:\n" + article_block[:5500]
            + "\n\nGOVT DOCUMENT EVIDENCE:\n" + (govt_block[:1800] or "(none)")
            + "\n\nNEWSPAPER EDITION EVIDENCE:\n" + (paper_block[:1500] or "(none)")
            + "\n\nSOCIAL SIGNAL EVIDENCE:\n" + (social_block[:1500] or "(none)")
            + "\n\nVIDEO EVIDENCE:\n" + (video_block[:1000] or "(none)"),
        ),
        # Section 3: ENTITIES TODAY — cross-pillar dossier per monitored entity
        _section(
            "ENTITIES TODAY",
            ENTITIES_SYSTEM,
            role_line
            + "\nARTICLE EVIDENCE:\n" + article_block[:3500]
            + "\n\nNEWSPAPER EDITION EVIDENCE:\n" + (paper_block[:1500] or "(none)")
            + "\n\nSOCIAL SIGNAL EVIDENCE:\n" + (social_block[:1500] or "(none)")
            + "\n\nVIDEO EVIDENCE:\n" + (video_block[:1000] or "(none)"),
        ),
        # Section 4: SIGNALS TO WATCH — social-led, article corroboration
        _section(
            "SIGNALS TO WATCH",
            SIGNALS_SYSTEM,
            role_line
            + "\nSOCIAL SIGNAL EVIDENCE (primary for this section):\n"
            + (social_block[:3000] or "(no social signals retrieved)")
            + "\n\nNEWSPAPER EDITION EVIDENCE (corroboration):\n"
            + (paper_block[:1500] or "(none)")
            + "\n\nARTICLE EVIDENCE (corroboration):\n"
            + article_block[:2500],
        ),
        # Section 5: FINANCIAL PULSE — govt docs prioritised, articles back up
        _section(
            "FINANCIAL PULSE",
            FINANCIAL_SYSTEM,
            role_line
            + "\nGOVT DOCUMENT EVIDENCE (primary for this section):\n"
            + (govt_block[:2500] or "(no govt orders today)")
            + "\n\nFINANCE-TILTED ARTICLES:\n" + finance_article_block[:3000]
            + "\n\nNEWSPAPER EDITION EVIDENCE:\n" + (paper_block[:1000] or "(none)"),
        ),
        # Section 6: SOURCE COVERAGE — pillar pulse + gaps. Routed through
        # the fast model (llama-3.1-8b-instant) because the prompt is a
        # mechanical per-pillar list — doesn't need llama-3.3-70b reasoning,
        # and the fast model's much higher TPM ceiling means this section
        # never competes for the heavy-model pool.
        _section(
            "SOURCE COVERAGE",
            SOURCES_SYSTEM,
            f"PILLAR COUNTS\n"
            f"  Articles: {len(articles)} (sources: {', '.join(article_sources[:8])})\n"
            f"  Govt docs: {len(govt_docs)} (departments: {', '.join(govt_dept_names[:5]) or '(none)'})\n"
            f"  Newspaper clippings: {len(newspaper_clippings)} ({', '.join(paper_names[:5]) or '(none)'})\n"
            f"  Social posts: {len(social_posts)} "
            f"({', '.join(f'{k} {v}' for k,v in social_platform_counts.items()) or '(none)'})\n"
            f"  Video clips: {len(video_clips)} ({', '.join(video_channels[:4]) or '(none)'})\n"
            f"\nSAMPLE OF TOP COVERAGE:\n{article_block[:1500]}\n",
            model=FAST_MODEL,
        ),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    section_names = [
        "SITUATION STATUS",
        "KEY DEVELOPMENTS",
        "ENTITIES TODAY",
        "SIGNALS TO WATCH",
        "FINANCIAL PULSE",
        "SOURCE COVERAGE",
    ]

    # Structured fallback (D-BRIEF-14 fix) — when a section fails entirely
    # we DO NOT ship raw `[Generation failed: ...]` to the user. Instead
    # we synthesise a short prose summary from the evidence that was
    # supposed to feed that section. The user sees something coherent
    # (even if shallow); the LLM placeholder never reaches the UI.
    fallback_blurbs = _build_fallback_blurbs(
        articles=articles,
        govt_docs=govt_docs,
        social_posts=social_posts,
        newspaper_clippings=newspaper_clippings,
        video_clips=video_clips,
    )

    sections: dict[str, str] = {}
    section_failures: list[str] = []
    for name, result in zip(section_names, results):
        if isinstance(result, Exception):
            logger.error("Section %s failed: %s", name, result)
            sections[name] = fallback_blurbs.get(
                name,
                "_This section could not be generated. The remaining "
                "sections of today's brief are unaffected._",
            )
            section_failures.append(name)
        else:
            sections[name] = result or fallback_blurbs.get(
                name, "_No content generated._"
            )

    # Section-length minimums (P2.9) — anything below
    # BRIEF_SECTION_MIN_WORDS gets regenerated once with a stricter
    # prompt asking for more depth. Skip SOURCE COVERAGE (mechanical
    # list, often shorter) and skip already-fallback content.
    min_words = settings.BRIEF_SECTION_MIN_WORDS
    skip_regen = {"SOURCE COVERAGE", *section_failures}
    short_names = [
        n for n, body in sections.items()
        if n not in skip_regen and count_words(body) < min_words
    ]
    if short_names:
        logger.info(
            "Brief sections below %d words, regenerating: %s",
            min_words, short_names,
        )
        # Map name -> (system, user) from the original task list. Recover
        # them by index — same order as section_names.
        regen_systems = {
            "SITUATION STATUS": SITUATION_SYSTEM,
            "KEY DEVELOPMENTS": DEVELOPMENTS_SYSTEM,
            "ENTITIES TODAY": ENTITIES_SYSTEM,
            "SIGNALS TO WATCH": SIGNALS_SYSTEM,
            "FINANCIAL PULSE": FINANCIAL_SYSTEM,
        }
        for n in short_names:
            try:
                stricter_system = (
                    regen_systems[n]
                    + "\n\nIMPORTANT: previous attempt was too short. "
                    f"Produce at least {min_words + 40} words of "
                    "substantive prose. Add concrete details, names, "
                    "and citations — do not pad with hedges."
                )
                # Reuse the same evidence body as the first attempt by
                # re-running the same _section call. Cheap because
                # section_sem caps concurrency.
                regen = await _section(
                    n, stricter_system,
                    role_line + "\n" + _evidence_for_section(
                        n, article_block, govt_block, social_block,
                        paper_block, video_block, finance_article_block,
                    ),
                )
                if count_words(regen) >= min_words:
                    sections[n] = regen
            except Exception as exc:  # noqa: BLE001 — best-effort regen
                logger.warning("Section '%s' regen failed: %s", n, exc)

    # Citation validator (P2.7) — strip sentences with hallucinated
    # ``[N]`` indexes. Prose-style cites (Doc:/Paper:/Social:/Video:)
    # are checked for plausibility (the pillar must be non-empty) but
    # not stripped — they are free-form labels and false positives are
    # too costly to ship the user a half-empty brief over.
    validation_summary: list[ValidationResult] = []
    for n, body in sections.items():
        result = validate_citations(
            n, body,
            article_count=len(articles),
            govt_doc_count=len(govt_docs),
            newspaper_count=len(newspaper_clippings),
            social_count=len(social_posts),
            video_count=len(video_clips),
        )
        validation_summary.append(result)
        if result.invalid_article_indexes:
            cleaned = strip_invalid_citations(
                body, article_count=len(articles)
            )
            if count_words(cleaned) >= min_words // 2:
                sections[n] = cleaned
                logger.warning(
                    "Brief section '%s' had hallucinated cites %s; "
                    "stripped offending sentences.",
                    n, list(result.invalid_article_indexes),
                )

    today_str = date.today().strftime("%A, %d %B %Y")

    content = f"""# DAILY INTELLIGENCE BRIEF
## {today_str}
*Generated for: {role_context[:80]}*

---

## SITUATION STATUS

{sections["SITUATION STATUS"]}

---

## KEY DEVELOPMENTS

{sections["KEY DEVELOPMENTS"]}

---

## ENTITIES TODAY

{sections["ENTITIES TODAY"]}

---

## SIGNALS TO WATCH

{sections["SIGNALS TO WATCH"]}

---

## FINANCIAL PULSE

{sections["FINANCIAL PULSE"]}

---

## SOURCE COVERAGE

{sections["SOURCE COVERAGE"]}

---
*{len(articles)} articles · {len(govt_docs)} govt orders · {len(newspaper_clippings)} newspaper clippings · {len(social_posts)} social signals · {len(video_clips)} video clips · {QUALITY_MODEL} · RIG SURVEILLANCE*"""

    return {
        "content": content,
        "articles_used": len(articles),
        "sections": sections,
        "section_failures": section_failures,
        "validation_summary": [
            {
                "section": v.section_name,
                "is_valid": v.is_valid,
                "total_cites": v.total_cites,
                "invalid_article_indexes": list(v.invalid_article_indexes),
                "issues": list(v.issues),
            }
            for v in validation_summary
        ],
    }


# ── Internal helpers used by structured fallback + length-min regen ──────────


def _build_fallback_blurbs(
    *,
    articles: list[dict],
    govt_docs: list[dict],
    social_posts: list[dict],
    newspaper_clippings: list[dict],
    video_clips: list[dict],
) -> dict[str, str]:
    """Build a per-section human-readable fallback when LLM fails.

    No "[Generation failed: ...]" leaks to the user (D-BRIEF-14). Each
    blurb is a short prose summary built from the evidence that was
    supposed to feed that section. The fallback is intentionally bland
    — its job is to ensure the brief still renders cleanly when one
    section's LLM call dies, not to replace the LLM.
    """
    top_articles = articles[:5]
    article_titles = [a.get("title", "") for a in top_articles if a.get("title")]
    top_govt = [d.get("title", "") for d in govt_docs[:3] if d.get("title")]
    paper_lines = [
        f"{n.get('newspaper','?')} ({n.get('language','')}) — "
        f"{n.get('headline','(untitled)')}"
        for n in newspaper_clippings[:3]
    ]
    social_topics = sorted({
        (s.get("topic") or s.get("topic_category") or "").strip()
        for s in social_posts if s.get("topic") or s.get("topic_category")
    })
    return {
        "SITUATION STATUS": (
            "_(Live LLM section unavailable; auto-summary follows.)_ "
            f"Today's coverage spans {len(articles)} relevant articles, "
            f"{len(govt_docs)} government documents, "
            f"{len(newspaper_clippings)} newspaper clippings, "
            f"{len(social_posts)} social posts and {len(video_clips)} "
            "video clips. Top stories: "
            + ("; ".join(article_titles[:3]) or "no headline articles.")
            + " Click Refresh in a few minutes for the full brief."
        ),
        "KEY DEVELOPMENTS": (
            "_(Live LLM section unavailable; auto-summary follows.)_\n\n"
            + "\n".join(
                f"① {t}" for t in article_titles[:5]
            )
            + ("\n\n(Refresh to retry full multi-pillar synthesis.)"
               if article_titles else "")
        ),
        "ENTITIES TODAY": (
            "_(Live LLM section unavailable; auto-summary follows.)_ "
            "Per-entity dossiers will return on the next regeneration."
        ),
        "SIGNALS TO WATCH": (
            "_(Live LLM section unavailable; auto-summary follows.)_ "
            + (
                "Active social topics today: "
                + ", ".join(t for t in social_topics if t)[:300]
                if social_topics
                else "No social signals retrieved for today."
            )
        ),
        "FINANCIAL PULSE": (
            "_(Live LLM section unavailable; auto-summary follows.)_ "
            + (
                "Top govt orders today: " + "; ".join(top_govt)
                if top_govt
                else "No significant financial developments captured."
            )
        ),
        "SOURCE COVERAGE": (
            f"ARTICLES ({len(articles)}): top {min(8, len(top_articles))} "
            f"shown\nNEWSPAPERS ({len(newspaper_clippings)})"
            + (": " + "; ".join(paper_lines) if paper_lines else "")
            + f"\nGOVT DOCS ({len(govt_docs)}) · "
            f"SOCIAL ({len(social_posts)}) · VIDEO ({len(video_clips)})"
        ),
    }


def _evidence_for_section(
    section_name: str,
    article_block: str,
    govt_block: str,
    social_block: str,
    paper_block: str,
    video_block: str,
    finance_article_block: str,
) -> str:
    """Return the evidence body matching ``section_name`` for length regen.

    Mirrors the per-section evidence assembly in the main ``tasks`` list
    so the regen pass uses the same context the first attempt saw.
    """
    if section_name == "SITUATION STATUS":
        return (
            "ARTICLE EVIDENCE:\n" + article_block[:3500]
            + "\n\nGOVT DOCUMENT EVIDENCE:\n" + (govt_block[:1500] or "(none)")
            + "\n\nNEWSPAPER EDITION EVIDENCE:\n" + (paper_block[:1500] or "(none)")
            + "\n\nSOCIAL SIGNAL EVIDENCE:\n" + (social_block[:1500] or "(none)")
        )
    if section_name == "KEY DEVELOPMENTS":
        return (
            "ARTICLE EVIDENCE:\n" + article_block[:5500]
            + "\n\nGOVT DOCUMENT EVIDENCE:\n" + (govt_block[:1800] or "(none)")
            + "\n\nNEWSPAPER EDITION EVIDENCE:\n" + (paper_block[:1500] or "(none)")
            + "\n\nSOCIAL SIGNAL EVIDENCE:\n" + (social_block[:1500] or "(none)")
            + "\n\nVIDEO EVIDENCE:\n" + (video_block[:1000] or "(none)")
        )
    if section_name == "ENTITIES TODAY":
        return (
            "ARTICLE EVIDENCE:\n" + article_block[:3500]
            + "\n\nNEWSPAPER EDITION EVIDENCE:\n" + (paper_block[:1500] or "(none)")
            + "\n\nSOCIAL SIGNAL EVIDENCE:\n" + (social_block[:1500] or "(none)")
            + "\n\nVIDEO EVIDENCE:\n" + (video_block[:1000] or "(none)")
        )
    if section_name == "SIGNALS TO WATCH":
        return (
            "SOCIAL SIGNAL EVIDENCE (primary for this section):\n"
            + (social_block[:3000] or "(no social signals retrieved)")
            + "\n\nNEWSPAPER EDITION EVIDENCE (corroboration):\n"
            + (paper_block[:1500] or "(none)")
            + "\n\nARTICLE EVIDENCE (corroboration):\n"
            + article_block[:2500]
        )
    if section_name == "FINANCIAL PULSE":
        return (
            "GOVT DOCUMENT EVIDENCE (primary for this section):\n"
            + (govt_block[:2500] or "(no govt orders today)")
            + "\n\nFINANCE-TILTED ARTICLES:\n" + finance_article_block[:3000]
            + "\n\nNEWSPAPER EDITION EVIDENCE:\n" + (paper_block[:1000] or "(none)")
        )
    return article_block[:3000]


# ── Per-pillar formatters ─────────────────────────────────────────────────────

def _format_articles(articles: list[dict], max_articles: int = 30) -> str:
    lines: list[str] = []
    for i, a in enumerate(articles[:max_articles]):
        title = a.get("title", "")
        source = a.get("source_name", "")
        topic = a.get("topic_category", "")
        geo = a.get("geo_primary", "")
        text = (
            a.get("lead_text_translated")
            or a.get("lead_text_original")
            or ""
        )[:400]
        score = a.get("score_final") or 0

        lines.append(
            f"[{i + 1}] {title}\n"
            f"Source: {source} | Topic: {topic} | Geo: {geo} | Score: {score:.2f}\n"
            f"{text}\n"
        )

    return "\n".join(lines)


def _format_govt_docs(govt_docs: list[dict], max_items: int = 8) -> str:
    """Format govt documents as numbered evidence with cite hint."""
    if not govt_docs:
        return ""
    lines: list[str] = []
    for i, d in enumerate(govt_docs[:max_items], 1):
        title = d.get("title", "(untitled)")
        source = d.get("source_name", "")
        geo = d.get("source_geography", "")
        doc_type = d.get("document_type", "")
        published = (d.get("published_at") or d.get("collected_at") or "")[:10]
        page = d.get("page_number")
        section_h = d.get("section_heading") or ""
        snippet = (d.get("snippet") or d.get("summary") or "")[:500]

        intel = d.get("intel_json") or {}
        what = (intel.get("what_it_does") or "").strip()

        page_str = f" | Page: {page}" if page else ""
        section_str = f" | Section: {section_h}" if section_h else ""
        what_str = f"\nWhat it does: {what}" if what else ""

        lines.append(
            f"[Doc {i}] {title}\n"
            f"Source: {source} | Type: {doc_type} | Geo: {geo}"
            f" | Date: {published}{page_str}{section_str}\n"
            f"Citation: (Doc: {title[:60]}{', p.'+str(page) if page else ''})"
            f"{what_str}\n"
            f"{snippet}\n"
        )
    return "\n---\n".join(lines)


def _format_social(social_posts: list[dict], max_items: int = 10) -> str:
    """Format social posts (Reddit / Telegram / Twitter) with citation hint."""
    if not social_posts:
        return ""
    lines: list[str] = []
    for i, s in enumerate(social_posts[:max_items], 1):
        platform = (s.get("platform") or "").upper()
        author = s.get("author") or s.get("author_username") or ""
        posted = (s.get("posted_at") or "")[:10]
        sentiment = s.get("sentiment")
        topic = s.get("topic") or s.get("topic_category") or ""
        url = s.get("url") or s.get("post_url") or ""

        snippet = (
            s.get("text_snippet")
            or s.get("post_text_translated")
            or s.get("post_text")
            or ""
        )[:400].replace("\n", " ").strip()

        sentiment_str = (
            f" | Sentiment: {sentiment:+.2f}"
            if isinstance(sentiment, (int, float)) else ""
        )
        url_str = f" | URL: {url}" if url else ""

        lines.append(
            f"[Social {i}] {platform} @ {posted}\n"
            f"Author: {author}{sentiment_str} | Topic: {topic}{url_str}\n"
            f"Citation: (Social: {platform.lower()} @ {posted})\n"
            f"{snippet}\n"
        )
    return "\n---\n".join(lines)


def _format_newspapers(clippings: list[dict], max_items: int = 8) -> str:
    """Format vernacular newspaper clippings with citation hint."""
    if not clippings:
        return ""
    lines: list[str] = []
    for i, n in enumerate(clippings[:max_items], 1):
        newspaper = n.get("newspaper", "")
        language = n.get("language", "")
        edition = (n.get("edition_date") or "")[:10]
        page = n.get("page_number")
        headline = (n.get("headline") or "(untitled)")
        topic = n.get("topic_category") or ""
        geo = n.get("geo_primary") or ""
        snippet = (n.get("text_snippet") or "")[:400].replace("\n", " ").strip()

        page_str = f", p.{page}" if page else ""

        lines.append(
            f"[Paper {i}] {headline}\n"
            f"Newspaper: {newspaper} ({language}) | Edition: {edition}"
            f"{page_str} | Topic: {topic} | Geo: {geo}\n"
            f"Citation: (Paper: {newspaper} {edition}{page_str})\n"
            f"{snippet}\n"
        )
    return "\n---\n".join(lines)


def _format_video_clips(clips: list[dict], max_items: int = 4) -> str:
    """Format YouTube clip transcripts with citation hint."""
    if not clips:
        return ""
    lines: list[str] = []
    for i, c in enumerate(clips[:max_items], 1):
        title = c.get("title", "")
        channel = c.get("channel", "")
        start_seconds = c.get("start_seconds") or 0
        try:
            mins = int(start_seconds) // 60
            secs = int(start_seconds) % 60
            timestamp = f"{mins}:{secs:02d}"
        except Exception:
            timestamp = "0:00"
        entity = c.get("matched_entity", "")
        snippet = (c.get("text_snippet") or "")[:400].replace("\n", " ").strip()

        lines.append(
            f"[Video {i}] {title}\n"
            f"Channel: {channel} | At: {timestamp} | Entity: {entity}\n"
            f"Citation: (Video: {channel} @ {timestamp})\n"
            f"Spoken: {snippet}\n"
        )
    return "\n---\n".join(lines)
