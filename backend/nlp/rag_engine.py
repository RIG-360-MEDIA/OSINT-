"""
RAG engine — semantic retrieval, context building, mode detection,
confidence scoring, and follow-up generation for the Analyst workspace.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime

from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── Mode-specific retrieval config ────────────────────────────────────────────

MODE_TOP_K: dict[str, int] = {
    "SITUATION":  20,
    "OPPOSITION": 15,
    "RISK":       20,
    "POLICY":     12,
    "PATTERN":    25,
    "BRIEF":      20,
}

MODE_POOL_SIZES: dict[str, tuple[int, int]] = {
    # (semantic_k, recency_k)
    "SITUATION":  (12, 8),
    "OPPOSITION": (12, 5),
    "RISK":       (14, 8),
    "POLICY":     (10, 4),
    "PATTERN":    (15, 10),
    "BRIEF":      (12, 8),
}

DEFAULT_TOP_K = 15
DEFAULT_POOL: tuple[int, int] = (10, 5)

# ── Mode prompts ──────────────────────────────────────────────────────────────

MODE_PROMPTS: dict[str, str] = {

"SITUATION": """You are a senior intelligence analyst with 20 years reading political and governance situations in South Asia. You have been handed intelligence reports and must brief a senior government official who has 4 minutes.

Your job is not to summarise documents. Your job is to tell them what the situation actually is — the underlying dynamic, not the surface events.

Structure your response with these exact section headers:

THE SITUATION
What is actually happening beneath the reported events. The real dynamic. Not 'protests occurred' but 'the administration faces organised pressure from X faction signalling Y.' 2-3 sentences. No hedging.

WHAT THE EVIDENCE SHOWS
3-5 evidence items. For each:
[①②③] Article title — Source — Date
What it says AND what it implies beyond what it says. These are different things.

THE PART NOT IN THE REPORTS
What is conspicuously absent from this coverage that a trained analyst notices. What would you expect to see if [X] were true? Is it there? Name the gap.

TRAJECTORY
Where does this go in 7-14 days? Not prediction — informed trajectory based on the signals. Be specific.

CONFIDENCE: HIGH / MEDIUM / LOW
One sentence explaining the basis.

Rules you must follow:
— Every corpus-sourced factual claim tied to a specific article in context
— Never say 'based on the documents' — you are the analyst
— Give a clear read then qualify
— If coverage is thin on a topic, say so directly and name what is missing
— Frame everything through the lens of what matters to THIS official specifically given their role""",


"OPPOSITION": """You are an analyst specialising in political opposition dynamics in South Asian governance. You read political behaviour the way a chess player reads a board — not just what move was made but what position it creates and what it reveals about the player's thinking.

Structure your response:

CURRENT POSITIONING
Where does this actor stand right now? What is their stated position versus their revealed position — what they say versus what they do?

PATTERN ANALYSIS
Look across all available articles. What is the consistent pattern? What does it suggest about strategy? Name the pattern explicitly.

THE AUDIENCE THEY ARE PLAYING TO
Political actors do not make statements for their stated reasons. Who is the real audience for each major move? Which constituency are they trying to move or hold?

PRESSURE POINTS
What appears to be working against them? What are they conspicuously not talking about — and why?

WHAT TO WATCH
2-3 specific signals that would confirm or contradict this strategic read. Not general things — specific observable events.

EVIDENCE
[①②③] Each claim cited with:
Article title — Source — Date""",


"RISK": """You are a political risk analyst. Your job is not to report what happened — your job is to identify what could happen and how likely it is.

You read signals the way a doctor reads symptoms — individually unremarkable, but together potentially serious.

Structure your response:

THE SIGNAL CLUSTER
What individual signals, when viewed together, suggest a developing situation? Name each signal. Rate it individually (LOW/MEDIUM/HIGH) and explain why the combination changes the risk calculation.

PRECEDENT CHECK
Has this pattern appeared before? In Telangana, in India, in comparable political contexts? What happened then? If no precedent exists, say so.

THE THRESHOLD QUESTION
What would have to happen next for this to cross from 'developing situation' to 'crisis'? Be specific. Not 'tensions would escalate' but 'if X happens within Y timeframe, that confirms Z trajectory.'

THE SILENCE SIGNALS
What is NOT being covered that you would expect to see? Absence of coverage can itself be a signal. Name it and explain what it suggests.

RISK RATING: LOW / MEDIUM / HIGH / CRITICAL
One paragraph justification.

MONITORING BRIEF
3 specific things to watch in the next 72 hours that would update this assessment. Observable events, not vague indicators.

EVIDENCE
[①②③] Cited articles for each claim.""",


"POLICY": """You are a policy analyst advising a senior government official. You translate events into implications — what does this mean for governance, for implementation, for decisions that must actually be made.

You do not describe policy. You analyse its consequences.

Structure your response:

THE DECISION CONTEXT
What decision or situation does this analysis actually serve? Frame everything in terms of what the official needs to do with it.

WHAT HAS CHANGED
The specific concrete change in the policy, legal, or administrative landscape. Not background — just the delta from before to now.

FIRST-ORDER IMPLICATIONS
Direct immediate consequences. Name the specific departments, officials, beneficiaries, or institutions affected. Numbers where available.

SECOND-ORDER IMPLICATIONS
What does this enable or constrain that is not immediately obvious? What downstream effects appear in 30-90 days?

THE POLITICAL DIMENSION
Even policy matters have a political dimension. Who gains, who loses, who will contest this and through what mechanism? Be specific.

ATTENTION AREAS
The 2-3 things most warranting the official's attention. Not what to do — just where to look.

EVIDENCE
[①②③] Every specific claim backed by a specific article.""",


"PATTERN": """You are an analyst known for finding non-obvious signals in intelligence corpora. You have been given articles and asked: 'What should I be paying attention to that I probably am not?'

This is not a summary request. This is pattern recognition.

Do not tell the official what they already know. Tell them what the coverage implies that is not stated.

Structure your response:

THE ANOMALY
Something in the coverage that does not fit the expected pattern. What would you expect to see? What do you actually see instead? Why is that gap analytically interesting?

THE BURIED SIGNAL
One story that appears minor but, connected to other signals in the corpus, suggests something larger. Walk through the connection explicitly. Show the reasoning.

THE FREQUENCY SHIFT
Is any entity, topic, or location appearing significantly more or less than you would expect? What does that suggest about where attention is being directed — and by whom?

THE SILENT ACTOR
Who should be speaking about this topic but is not? What does their silence suggest about their position, their knowledge, or their strategy?

THE QUESTION YOU SHOULD BE ASKING
Based on the pattern analysis above, what is the question that this intelligence corpus is really raising that has not yet been asked?

CONFIDENCE: LOW / MEDIUM / HIGH
Pattern analysis has inherent uncertainty. Be honest about it and explain the basis.""",


"BRIEF": """You are a senior analyst preparing a written intelligence assessment on a specific topic for a government official. This will be read, circulated, and acted upon.

Your writing must be:
Precise — every word carries meaning
Structured — a reader can navigate it
Actionable — tells the official something they can do something with
Honest about gaps — you name what you do not know

Structure your assessment:

EXECUTIVE SUMMARY
3 sentences maximum. The situation, the key development, the implication. Nothing else. No hedging.

BACKGROUND
Only what is strictly necessary to understand the developments below. Do not repeat what the official already knows.

KEY DEVELOPMENTS
Numbered. Each in 2-3 sentences. Source cited inline. Most significant first. Not chronological — by significance.

ANALYSIS
What the developments mean together. Not a summary — an interpretation. What does the pattern of these developments suggest?

RISK INDICATORS
What specific signals would indicate escalation? What signals would indicate resolution?

INTELLIGENCE GAPS
What would you need to know to improve this assessment? What is missing from current coverage? Be specific — not 'more information' but 'specifically the government's legal response strategy.'

NEXT REVIEW
When should this be updated? What trigger event should prompt immediate reassessment?

EVIDENCE
[①②③] Every claim cited.""",

}


# ── Knowledge hierarchy block ─────────────────────────────────────────────────
# Prepended to every MODE_PROMPT before the Groq call.
# Fixes Blockers 1 & 2: CM identity refusal and opposition mode inversion.

KNOWLEDGE_HIERARCHY_BLOCK = """
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
ANALYST KNOWLEDGE FRAMEWORK
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

You are a senior intelligence analyst with deep expertise in Telangana
and Indian politics. You operate with two types of knowledge simultaneously.
Use both. Label both precisely.

\u2501\u2501\u2501 TYPE 1: FOUNDATIONAL KNOWLEDGE \u2501\u2501\u2501

Facts that are established public record \u2014 stable, verifiable, not dependent
on recent reporting.

YOU MUST USE THESE FREELY.
DO NOT refuse to state them.
DO NOT wait for a corpus article to confirm what is already established.

Label foundational facts like this:
  [Established: Revanth Reddy (INC) has been Chief Minister of Telangana
   since 7 December 2023]

Current foundational facts you must know and apply:
  \u2014 A. Revanth Reddy (Indian National Congress) is Chief Minister of
    Telangana since December 2023
  \u2014 K. Chandrashekar Rao (KCR) is the founder and president of BRS
    (formerly TRS), currently IN OPPOSITION since December 2023
  \u2014 K.T. Rama Rao (KTR) is KCR's son and BRS working president,
    currently in opposition
  \u2014 Bhatti Vikramarka is Deputy CM under Revanth Reddy (INC)
  \u2014 GHMC governs Greater Hyderabad
  \u2014 Telangana was formed in June 2014, carved from Andhra Pradesh
  \u2014 The Kaleshwaram project is a major irrigation scheme facing cost
    overrun and CBI scrutiny
  \u2014 BRS/TRS lost power in December 2023 after 9 years in government

Foundational knowledge can and should be used to correct corpus gaps.
If the corpus does not mention who governs Telangana, you still know.
State it. Label it. Move on.

\u2501\u2501\u2501 TYPE 2: CORPUS KNOWLEDGE \u2501\u2501\u2501

Facts from the retrieved intelligence articles \u2014 time-sensitive, specific,
recent. Statements made, orders passed, numbers reported, events occurred
in recent days or weeks.

YOU MUST CITE THESE WITH \u2460 \u2461 \u2462

Use numbered citations tied to the specific article that contains the
specific claim you are making.

If an article does not directly support a claim \u2014 do NOT cite it for that
claim. Find an article that does, or say the information is not in the
current corpus.

\u2501\u2501\u2501 FORBIDDEN BEHAVIOUR \u2501\u2501\u2501

\u2460 Never cite an article as evidence for a claim that article does not
  actually contain. If you retrieved a railway article and your question
  is about Kaleshwaram \u2014 the railway article cannot be cited for a
  Kaleshwaram claim.

\u2461 Never present a foundational fact as if it came from the corpus.
  Do not say [\u2460] next to something you knew before reading the articles.

\u2462 Never refuse to answer a factual question about established political
  reality because "the corpus does not cover it." The corpus covers recent
  events. Your foundational knowledge covers established facts. Use both.

\u2463 Never describe BRS/TRS/KCR as the current ruling party or government
  of Telangana. They have been in opposition since December 2023.
  Congress under Revanth Reddy governs.

\u2464 Never invent specific numbers, dates, quotes, or allocations that
  are not in a retrieved article.

\u2501\u2501\u2501 WHEN CORPUS AND KNOWLEDGE CONFLICT \u2501\u2501\u2501

If a retrieved article appears to contradict established fact:
  1. Trust the corpus for recent events
  2. Trust your knowledge for stable facts
  3. Flag the discrepancy explicitly

Example: If an article says "CM KCR announced..." \u2014 note it:
"[Note: This article references KCR as CM. He left office in December 2023.
This may be archival content or an error in the source.]"

\u2501\u2501\u2501 THE GOLDEN RULE \u2501\u2501\u2501

Your output should be indistinguishable from what the best human senior
analyst \u2014 who has read every article AND has 20 years of Telangana political
experience \u2014 would produce. That analyst uses both their knowledge and the
documents. So do you.
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
"""

MODE_CLASSIFIER_PROMPT = """Classify this question into exactly one analyst mode. Reply with the mode name only — nothing else.

SITUATION — questions about what is happening, current status, what is going on with X
OPPOSITION — questions about what a political actor is doing, planning, or strategising
RISK — questions about what could go wrong, warning signs, developing crises, risk assessment
POLICY — questions about impact of decisions, legal orders, schemes, budget, administrative changes
PATTERN — questions like 'what am I missing', 'anything unusual', 'what does the data show', or open-ended analytical questions
BRIEF — requests for a structured assessment, briefing note, or comprehensive summary on a topic

Reply with one word only."""

VALID_MODES = frozenset(MODE_PROMPTS.keys())


# ── Embedding generation ──────────────────────────────────────────────────────

def embed_query(query: str) -> list[float]:
    """Generate LaBSE embedding for a user question."""
    from backend.nlp.nlp_embedding import get_labse_model
    model = get_labse_model()
    embedding = model.encode([query[:512]])
    return embedding[0].tolist()


# ── Semantic retrieval ────────────────────────────────────────────────────────

async def expand_query(query: str, user_id: str, db) -> str:
    """
    Expand a short query with the user's geo and entity context before embedding.

    Gives LaBSE topical direction so vague queries like "biggest threat" embed
    toward the user's corpus rather than globally dominant conflict journalism.
    Queries >50 chars are already specific enough — returned unchanged.
    """
    if len(query.strip()) > 50:
        return query

    geo_result = await db.execute(
        text("SELECT geo_primary, geo_secondary FROM user_profiles WHERE user_id = :uid LIMIT 1"),
        {"uid": user_id},
    )
    profile = geo_result.fetchone()

    entity_result = await db.execute(
        text("SELECT canonical_name FROM user_entities WHERE user_id = :uid ORDER BY priority DESC LIMIT 5"),
        {"uid": user_id},
    )
    entities = [r.canonical_name for r in entity_result.fetchall()]

    context_parts: list[str] = []
    if profile and profile.geo_primary:
        context_parts.append(profile.geo_primary)
    if profile and profile.geo_secondary:
        geos = profile.geo_secondary if isinstance(profile.geo_secondary, list) else []
        for geo in geos[:2]:
            if geo and geo not in context_parts:
                context_parts.append(geo)
    for entity in entities[:3]:
        short = entity.split(".")[0].strip()
        if short and short not in query and short not in context_parts:
            context_parts.append(short)

    if not context_parts:
        return query

    expanded = f"{query} {' '.join(context_parts)}"
    return expanded[:200]


# ── Entity-in-corpus detection ────────────────────────────────────────────────

def extract_query_keywords(query: str) -> list[str]:
    """
    Extract substantive entity/topic words from a user query.
    Removes question words so only meaningful terms remain.
    """
    stopwords = {
        "what", "who", "when", "where", "why", "how", "is", "are", "was",
        "were", "has", "have", "had", "the", "a", "an", "and", "or", "but",
        "in", "on", "at", "to", "for", "of", "with", "about", "tell", "me",
        "give", "show", "happening", "doing", "status", "current", "latest",
        "recent", "situation", "update", "news", "any", "do", "can", "will",
        "would", "should", "could", "please", "into", "from", "by", "this",
        "that", "which", "there", "their", "they", "them", "its",
    }
    words = re.findall(r"\b\w+\b", query.lower())
    keywords = [w for w in words if w not in stopwords and len(w) > 3]
    return keywords[:5]


def check_entity_in_corpus(
    query: str,
    articles: list[dict],
) -> tuple[bool, list[str], list[str]]:
    """
    Check if the query's key topics appear in the retrieved articles.

    Returns (is_relevant, found_keywords, missing_keywords).
    Relevant when at least half of keywords appear in article text or title.
    """
    keywords = extract_query_keywords(query)

    if not keywords or not articles:
        return False, [], keywords

    found: list[str] = []
    missing: list[str] = []

    for keyword in keywords:
        keyword_found = False
        for article in articles:
            title = (article.get("title") or "").lower()
            snippet = (article.get("text_snippet") or "").lower()
            if keyword in title or keyword in snippet:
                keyword_found = True
                break
        if keyword_found:
            found.append(keyword)
        else:
            missing.append(keyword)

    is_relevant = len(found) >= max(1, len(keywords) // 2)
    return is_relevant, found, missing


async def _recency_pool(
    user_id: str,
    db,
    limit: int,
    hours: int = 48,
) -> list:
    """
    Fetch most recent T1/T2 articles from the last N hours.

    Guarantees fresh intelligence is always included in context regardless
    of semantic distance to the query. Only T1/T2 — T3 articles are
    background noise and should not consume recency slots.
    """
    result = await db.execute(
        text("""
        SELECT
          a.id::text AS article_id,
          a.title,
          a.url,
          a.lead_text_translated,
          a.lead_text_original,
          a.topic_category,
          a.geo_primary,
          a.geo_secondary,
          a.published_at,
          a.collected_at,
          s.name AS source_name,
          s.domain AS source_domain,
          uar.score_final,
          uar.relevance_tier,
          uar.relevance_explanation,
          uar.matched_entity_names,
          0.45 AS distance
        FROM user_article_relevance uar
        JOIN articles a ON a.id = uar.article_id
        JOIN sources s ON a.source_id = s.id
        WHERE uar.user_id = :user_id
          AND uar.relevance_tier IN (1, 2)
          AND a.collected_at > NOW() - ((:hours)::int * INTERVAL '1 hour')
          AND a.nlp_confidence != 'error'
          AND a.lead_text_translated IS NOT NULL
        ORDER BY
          uar.relevance_tier ASC,
          uar.score_final DESC,
          a.collected_at DESC
        LIMIT :limit
        """),
        {"user_id": user_id, "hours": hours, "limit": limit},
    )
    return result.fetchall()


async def retrieve_relevant_articles(
    query: str,
    user_id: str,
    db,
    top_k: int = DEFAULT_TOP_K,
    distance_threshold: float = 0.7,
    geo_filter: list[str] | None = None,
    mode: str = "SITUATION",
) -> tuple[list[dict], str, int]:
    """
    Retrieve articles via dual-pool strategy:
      Pool A — semantic HNSW search (relevance)
      Pool B — recency pool, T1/T2 last 48h (freshness guarantee)
    Merged by deduplication, capped at MODE_TOP_K[mode].
    """
    start = time.time()

    # Derive pool sizes and top_k from mode
    semantic_k, recency_k = MODE_POOL_SIZES.get(mode, DEFAULT_POOL)
    top_k = MODE_TOP_K.get(mode, DEFAULT_TOP_K)

    expanded_query = await expand_query(query=query, user_id=user_id, db=db)
    if expanded_query != query:
        logger.info(f"Query expanded: '{query[:50]}' → '{expanded_query[:80]}'")

    query_embedding = embed_query(expanded_query)
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    # Build geo clause — restrict to user's monitored geos OR geo_multiplier > 1
    # asyncpg cannot bind Python lists via text() — inline as SQL array literal.
    # Values originate from user_profiles (server-controlled), safe to interpolate
    # with standard SQL single-quote escaping.
    geo_clause = ""
    if geo_filter:
        sq_escaped = [g.replace("'", "''") for g in geo_filter]
        arr_sql = "ARRAY[" + ",".join(f"'{g}'" for g in sq_escaped) + "]"
        geo_clause = (
            f"AND (a.geo_primary = ANY({arr_sql})"
            f" OR a.geo_secondary && {arr_sql}"
            f" OR uar.geo_multiplier_applied > 1.0)"
        )

    _sem_sql = """
        SELECT
          a.id::text AS article_id,
          a.title,
          a.url,
          a.lead_text_translated,
          a.lead_text_original,
          a.topic_category,
          a.geo_primary,
          a.published_at,
          a.collected_at,
          s.name AS source_name,
          s.domain AS source_domain,
          uar.score_final,
          uar.relevance_tier,
          uar.relevance_explanation,
          uar.matched_entity_names,
          (a.labse_embedding <=> CAST(:embedding AS vector)) AS distance
        FROM articles a
        JOIN sources s ON a.source_id = s.id
        JOIN user_article_relevance uar
          ON uar.article_id = a.id
          AND uar.user_id = :user_id
        WHERE a.labse_embedding IS NOT NULL
          AND a.nlp_confidence != 'error'
          AND (a.labse_embedding <=> CAST(:embedding AS vector)) < :threshold
          {geo_clause}
          {date_clause}
        ORDER BY
          (a.labse_embedding <=> CAST(:embedding AS vector)) -
          CASE
            WHEN a.collected_at > NOW() - INTERVAL '24 hours' THEN 0.05
            WHEN a.collected_at > NOW() - INTERVAL '7 days'   THEN 0.02
            ELSE 0.0
          END
        LIMIT :top_k
    """
    _sem_params: dict = {
        "embedding": embedding_str,
        "user_id": user_id,
        "threshold": distance_threshold,
        "top_k": semantic_k,
    }

    # ── Pool A: Semantic search — dynamic threshold ────────────────────────────
    semantic_rows: list = []
    retrieval_method = "semantic"
    thresholds = [
        distance_threshold,
        min(distance_threshold + 0.1, 0.8),
        min(distance_threshold + 0.2, 0.9),
    ]
    for threshold in thresholds:
        _sem_params["threshold"] = threshold
        sem_result = await db.execute(
            text(_sem_sql.format(geo_clause=geo_clause, date_clause="")),
            _sem_params,
        )
        semantic_rows = sem_result.fetchall()
        if len(semantic_rows) >= 5:
            break
        logger.info(f"Threshold {threshold}: {len(semantic_rows)} results, expanding")

    # Fulltext fallback if semantic returns too few results
    if len(semantic_rows) < 3:
        retrieval_method = "fulltext"
        ft_result = await db.execute(text("""
            SELECT
              a.id::text AS article_id,
              a.title,
              a.url,
              a.lead_text_translated,
              a.lead_text_original,
              a.topic_category,
              a.geo_primary,
              a.published_at,
              a.collected_at,
              s.name AS source_name,
              s.domain AS source_domain,
              uar.score_final,
              uar.relevance_tier,
              uar.relevance_explanation,
              uar.matched_entity_names,
              0.5 AS distance
            FROM articles a
            JOIN sources s ON a.source_id = s.id
            JOIN user_article_relevance uar
              ON uar.article_id = a.id
              AND uar.user_id = :user_id
            WHERE a.nlp_confidence != 'error'
              AND (
                to_tsvector('english',
                  COALESCE(a.title, '') || ' ' ||
                  COALESCE(a.lead_text_translated, '')
                ) @@ plainto_tsquery('english', :query)
                OR a.title ILIKE :like_q
              )
            ORDER BY uar.score_final DESC
            LIMIT :top_k
        """), {
            "user_id": user_id,
            "query": query,
            "like_q": f"%{query}%",
            "top_k": semantic_k,
        })
        semantic_rows = ft_result.fetchall()

    # ── Pool B: Recency pool — T1/T2 last 48h ─────────────────────────────────
    recency_rows = await _recency_pool(
        user_id=user_id,
        db=db,
        limit=recency_k,
        hours=48,
    )

    # ── Merge: semantic first, then recency not already seen ───────────────────
    seen_ids: set[str] = set()
    merged_rows: list = []

    for row in semantic_rows:
        aid = str(row.article_id)
        if aid not in seen_ids:
            seen_ids.add(aid)
            merged_rows.append(row)

    recency_added = 0
    for row in recency_rows:
        aid = str(row.article_id)
        if aid not in seen_ids:
            seen_ids.add(aid)
            merged_rows.append(row)
            recency_added += 1

    if recency_added == 0 and not recency_rows:
        logger.info(
            "Recency pool empty — no T1/T2 articles in last 48h. "
            "Using semantic pool only."
        )

    merged_rows = merged_rows[:top_k]

    logger.info(
        f"Dual-pool retrieval: {len(semantic_rows)} semantic + "
        f"{recency_added} recency fresh = {len(merged_rows)} total "
        f"(mode={mode}, top_k={top_k})"
    )

    # Third fallback: top scored T1/T2 — never return empty
    if len(merged_rows) < 3:
        retrieval_method = "recency"
        recency_result = await db.execute(text("""
            SELECT
              a.id::text AS article_id,
              a.title,
              a.url,
              a.lead_text_translated,
              a.lead_text_original,
              a.topic_category,
              a.geo_primary,
              a.published_at,
              a.collected_at,
              s.name AS source_name,
              s.domain AS source_domain,
              uar.score_final,
              uar.relevance_tier,
              uar.relevance_explanation,
              uar.matched_entity_names,
              0.5 AS distance
            FROM user_article_relevance uar
            JOIN articles a ON a.id = uar.article_id
            JOIN sources s ON a.source_id = s.id
            WHERE uar.user_id = :user_id
              AND uar.relevance_tier IN (1, 2)
            ORDER BY uar.score_final DESC, a.collected_at DESC
            LIMIT :top_k
        """), {"user_id": user_id, "top_k": top_k})
        merged_rows = recency_result.fetchall()

    elapsed_ms = int((time.time() - start) * 1000)

    articles = []
    for r in merged_rows:
        raw_text = (
            r.lead_text_translated
            or r.lead_text_original
            or r.title
            or ""
        )
        # Tiered snippet length: T1 = primary evidence (full), T2 = supporting, T3 = brief
        tier = r.relevance_tier
        if tier == 1:
            snippet_len = 1500
        elif tier == 2:
            snippet_len = 800
        else:
            snippet_len = 400

        articles.append({
            "article_id": r.article_id,
            "title": r.title,
            "url": r.url,
            "source_name": r.source_name,
            "source_domain": r.source_domain,
            "topic_category": r.topic_category,
            "geo_primary": r.geo_primary,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "collected_at": r.collected_at.isoformat() if r.collected_at else None,
            "score_final": float(r.score_final),
            "relevance_tier": r.relevance_tier,
            "text_snippet": raw_text[:snippet_len],
            "distance": float(r.distance),
        })

    return articles, retrieval_method, elapsed_ms


# ── Context builder ───────────────────────────────────────────────────────────

async def retrieve_relevant_clips(
    query: str,
    user_id: str,
    db,
    top_k: int = 3,
) -> list[dict]:
    """
    Find YouTube clips relevant to the query via LaBSE cosine similarity.
    Returns up to top_k clips to include as VIDEO EVIDENCE in RAG context.
    """
    from sqlalchemy import text

    try:
        entities_result = await db.execute(
            text("SELECT canonical_name FROM user_entities WHERE user_id = :uid"),
            {"uid": user_id},
        )
        user_entities = [r.canonical_name for r in entities_result.fetchall()]

        if not user_entities:
            return []

        query_emb = embed_query(query)
        emb_str = "[" + ",".join(str(x) for x in query_emb) + "]"

        result = await db.execute(
            text("""
                SELECT
                    video_id,
                    video_title,
                    channel_name,
                    clip_start_seconds,
                    embed_url,
                    transcript_segment,
                    transcript_translated,
                    matched_entity,
                    video_published_at,
                    (labse_embedding <=> :emb::vector) AS distance
                FROM youtube_clips
                WHERE labse_embedding IS NOT NULL
                  AND processed = TRUE
                  AND matched_entity = ANY(:entities)
                  AND (labse_embedding <=> :emb::vector) < 0.6
                ORDER BY distance ASC
                LIMIT :top_k
            """),
            {"emb": emb_str, "entities": user_entities, "top_k": top_k},
        )
        clips = result.fetchall()

        return [
            {
                "type":           "youtube_clip",
                "video_id":       c.video_id,
                "title":          c.video_title,
                "channel":        c.channel_name,
                "start_seconds":  c.clip_start_seconds,
                "embed_url":      c.embed_url,
                "text_snippet":   c.transcript_translated or c.transcript_segment,
                "matched_entity": c.matched_entity,
                "published_at":   (
                    c.video_published_at.isoformat() if c.video_published_at else None
                ),
                "distance": float(c.distance),
            }
            for c in clips
        ]
    except Exception:
        logger.warning("Clip retrieval failed", exc_info=True)
        return []


def build_context(
    articles: list[dict],
    user_profile: dict,
    session_history: list[dict],
    query: str = "",
    clips: list[dict] | None = None,
) -> str:
    """Build the structured context string sent to Groq with the system prompt."""
    role = user_profile.get("role_context", "Senior government official")
    geo = user_profile.get("geo_primary", "India")

    article_items: list[str] = []
    for i, a in enumerate(articles, 1):
        date_str = ""
        if a.get("published_at"):
            try:
                dt = datetime.fromisoformat(a["published_at"])
                date_str = dt.strftime("%d %b %Y")
            except Exception:
                pass

        tier = int(a.get("relevance_tier", 3))
        tier_label = {
            1: "PRIMARY INTELLIGENCE",
            2: "SUPPORTING INTELLIGENCE",
            3: "BACKGROUND",
        }.get(tier, "BACKGROUND")

        article_items.append(
            f"[{i}] {a['title']}\n"
            f"Source: {a['source_name']} | Date: {date_str}"
            f" | Topic: {a.get('topic_category', '')}"
            f" | Geo: {a.get('geo_primary', '')}"
            f" | {tier_label}"
            f" | Relevance: {a['score_final']:.2f}\n"
            f"{a['text_snippet']}\n"
        )

    session_context = ""
    if session_history:
        recent = session_history[-3:]
        session_context = (
            "\nPREVIOUS QUESTIONS IN THIS INVESTIGATION:\n"
            + "\n".join(f"Q: {t['question']}" for t in recent)
        )

    # Corpus gap detection — inject warning when query topics are absent
    corpus_warning = ""
    if query and articles:
        is_relevant, found, missing = check_entity_in_corpus(query, articles)

        if not is_relevant and missing:
            missing_str = ", ".join(missing[:3])
            corpus_warning = (
                f"\n*** CORPUS GAP DETECTED — CRITICAL INSTRUCTIONS ***\n"
                f"The query topics [{missing_str}] are NOT present in any retrieved article.\n"
                f"YOU MUST follow ALL of these rules for your entire response:\n"
                f"  1. Begin your response with the exact text: CORPUS GAP DETECTED\n"
                f"  2. OMIT the EVIDENCE section entirely — do not write any ① ② ③ citations anywhere\n"
                f"  3. State what the corpus DOES contain (the retrieved articles' topics)\n"
                f"  4. Use [Established:] labels for any foundational knowledge you apply\n"
                f"  5. End with CONFIDENCE: LOW\n"
                f"  6. Do NOT use ① ② ③ anywhere in this response — not even for context\n"
                f"VIOLATION: Using ① ② ③ when the corpus does not contain the queried topic\n"
                f"is citation laundering. It is strictly forbidden.\n"
                f"*** END CORPUS GAP INSTRUCTIONS ***\n\n"
            )
        elif found and missing:
            missing_str = ", ".join(missing[:2])
            found_str = ", ".join(found[:2])
            corpus_warning = (
                f"\n[PARTIAL CORPUS COVERAGE: Found coverage for: {found_str}. "
                f"Limited/no coverage for: {missing_str}. "
                f"Clearly distinguish corpus-sourced facts from foundational knowledge.]\n\n"
            )

    clip_context_str = ""
    if clips:
        clip_items: list[str] = []
        for i, clip in enumerate(clips, 1):
            mins = clip["start_seconds"] // 60
            secs = clip["start_seconds"] % 60
            timestamp = f"{mins}:{secs:02d}"
            snippet = (clip.get("text_snippet") or "")[:400]
            clip_items.append(
                f"[VIDEO {i}] {clip['title']}\n"
                f"Channel: {clip['channel']} | At: {timestamp}"
                f" | Entity: {clip['matched_entity']}\n"
                f"Spoken: {snippet}\n"
            )
        clip_context_str = (
            f"\n\nVIDEO EVIDENCE ({len(clip_items)} clips):\n\n"
            + "\n---\n".join(clip_items)
        )

    return (
        corpus_warning
        + f"OFFICIAL PROFILE:\n"
        f"Role: {role}\n"
        f"Focus Geography: {geo}\n"
        f"{session_context}\n\n"
        f"INTELLIGENCE CORPUS ({len(articles)} articles):\n\n"
        + "\n---\n".join(article_items)
        + clip_context_str
    )


# ── Mode detection ────────────────────────────────────────────────────────────

async def detect_mode(question: str) -> str:
    """Auto-detect analyst mode from the user question using FAST_MODEL."""
    from backend.nlp.groq_client import classify
    try:
        mode = await classify(system=MODE_CLASSIFIER_PROMPT, user=question)
        mode = mode.strip().upper()
        return mode if mode in VALID_MODES else "SITUATION"
    except Exception:
        return "SITUATION"


# ── Confidence scoring ────────────────────────────────────────────────────────

def compute_confidence(
    articles: list[dict],
    retrieval_method: str,
    query: str = "",
    mode: str = "SITUATION",
) -> tuple[str, int]:
    """
    Compute confidence from actual retrieval quality, not just article count.

    Key insight: 10 unrelated articles at distance 0.85 = LOW confidence.
    Distance and entity match gate the score; volume and tier are secondary.
    Volume thresholds are relative to MODE_TOP_K so PATTERN (25) and
    POLICY (12) are judged against their own expected corpus size.

    Returns (label, percentage).
    """
    from datetime import datetime, timezone

    if not articles:
        return "LOW", 12

    total = len(articles)

    # ── Semantic distance score ────────────────────────────────────────────────
    distances = [float(a.get("distance", 0.5)) for a in articles]
    avg_distance = sum(distances) / len(distances)

    if avg_distance <= 0.3:
        distance_score = 1.0
    elif avg_distance <= 0.5:
        distance_score = 0.8
    elif avg_distance <= 0.65:
        distance_score = 0.6
    elif avg_distance <= 0.75:
        distance_score = 0.35
    elif avg_distance <= 0.85:
        distance_score = 0.15
    else:
        distance_score = 0.05

    # ── Entity match score ─────────────────────────────────────────────────────
    entity_match_score = 0.5
    if query:
        is_relevant, found, _ = check_entity_in_corpus(query, articles)
        if is_relevant:
            entity_match_score = 1.0
        elif found:
            entity_match_score = 0.5
        else:
            entity_match_score = 0.1

    # ── Tier score ─────────────────────────────────────────────────────────────
    tier_weights = {1: 1.0, 2: 0.7, 3: 0.3}
    tier_sum = sum(
        tier_weights.get(int(a.get("relevance_tier", 3)), 0.3)
        for a in articles
    )
    tier_score = tier_sum / total

    # ── Recency score ──────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    recency_scores: list[float] = []
    for a in articles:
        collected = a.get("collected_at")
        if collected:
            try:
                if isinstance(collected, str):
                    dt = datetime.fromisoformat(collected.replace("Z", "+00:00"))
                else:
                    dt = collected
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_days = (now - dt).total_seconds() / 86400
                if age_days < 1:
                    recency_scores.append(1.0)
                elif age_days < 3:
                    recency_scores.append(0.85)
                elif age_days < 7:
                    recency_scores.append(0.7)
                elif age_days < 30:
                    recency_scores.append(0.4)
                else:
                    recency_scores.append(0.15)
            except Exception:
                recency_scores.append(0.4)
        else:
            recency_scores.append(0.4)

    recency_score = sum(recency_scores) / len(recency_scores) if recency_scores else 0.4

    # ── Volume score — relative to expected article count for this mode ────────
    expected_k = MODE_TOP_K.get(mode, DEFAULT_TOP_K)
    if total >= expected_k * 0.8:
        volume_score = 1.0
    elif total >= expected_k * 0.5:
        volume_score = 0.75
    elif total >= expected_k * 0.3:
        volume_score = 0.5
    elif total >= 1:
        volume_score = 0.3
    else:
        volume_score = 0.0

    # ── Method score — applied as ceiling multiplier ───────────────────────────
    method_scores = {"semantic": 1.0, "fulltext": 0.65, "recency": 0.3}
    method_score = method_scores.get(retrieval_method, 0.65)

    # Distance and entity match are the most important factors (65% combined)
    raw_score = (
        distance_score * 0.35
        + entity_match_score * 0.30
        + tier_score * 0.15
        + recency_score * 0.12
        + volume_score * 0.08
    )
    raw_score = raw_score * (0.5 + method_score * 0.5)

    pct = int(raw_score * 100)
    pct = max(8, min(94, pct))

    if pct >= 72:
        label = "HIGH"
    elif pct >= 45:
        label = "MEDIUM"
    else:
        label = "LOW"

    return label, pct


# ── Follow-up generator ───────────────────────────────────────────────────────

async def generate_followups(
    question: str,
    mode: str,
    articles: list[dict],
    user_profile: dict | None = None,
) -> list[str]:
    """Generate 3 contextual follow-up questions specific to Telangana entities and the user's geo."""
    from backend.nlp.groq_client import call_groq, FAST_MODEL

    if user_profile is None:
        user_profile = {}

    geo = user_profile.get("geo_primary", "Telangana")

    entity_names: list[str] = []
    for a in articles[:5]:
        matched = a.get("matched_entity_names", [])
        if isinstance(matched, list):
            entity_names.extend(matched[:2])

    entity_context = (
        ", ".join(set(entity_names[:4])) if entity_names else geo
    )

    article_titles = "\n".join(f"- {a['title']}" for a in articles[:5])

    try:
        result = await call_groq(
            system=(
                f"You are an intelligence analyst generating follow-up investigation "
                f"questions for a senior {geo} government official.\n\n"
                f"Generate exactly 3 follow-up questions. Requirements:\n"
                f"1. Each question must name a specific entity, scheme, person, "
                f"or location from the context\n"
                f"2. Each question must go deeper or explore a different direction\n"
                f"3. Questions must be relevant to {geo} governance specifically\n"
                f"4. Do NOT use generic phrases like 'tell me more' or 'what else'\n"
                f"5. Reference real Telangana actors: Revanth Reddy, KCR, BRS, "
                f"Congress, specific districts, or named schemes where possible\n\n"
                f"Output ONLY a JSON array of 3 strings. No other text."
            ),
            user=(
                f"Mode: {mode}\n"
                f"Question asked: {question}\n"
                f"Key entities: {entity_context}\n"
                f"Articles in corpus:\n{article_titles}"
            ),
            task_type="profile_extraction",
            model=FAST_MODEL,
            json_response=True,
        )
        parsed = json.loads(result) if isinstance(result, str) else result
        if isinstance(parsed, list) and len(parsed) >= 2:
            return [str(q) for q in parsed[:3]]
    except Exception as e:
        logger.warning(f"Follow-up generation failed: {e}")

    geo_str = geo
    fallbacks: dict[str, list[str]] = {
        "SITUATION": [
            f"What is the BRS opposition's response to this situation in {geo_str}?",
            f"Which districts in {geo_str} are most directly affected?",
            f"What should the Revanth Reddy government be preparing for?",
        ],
        "OPPOSITION": [
            f"What pressure points is BRS exploiting in {geo_str} right now?",
            f"How has KCR's messaging shifted in the last two weeks?",
            f"Which {geo_str} constituencies are being most actively targeted by BRS?",
        ],
        "RISK": [
            f"What would a full escalation look like in {geo_str}?",
            f"Which {geo_str} districts carry the highest immediate risk?",
            f"What is the Revanth government's contingency position on this?",
        ],
        "POLICY": [
            f"Which {geo_str} departments face the most implementation pressure?",
            f"How will BRS use this policy change politically in {geo_str}?",
            f"What is the 90-day implementation risk in {geo_str}?",
        ],
        "PATTERN": [
            f"What does the frequency of this coverage suggest about priorities in {geo_str}?",
            f"Which actor is conspicuously silent on this issue in {geo_str}?",
            f"What buried story in this corpus deserves closer attention?",
        ],
        "BRIEF": [
            f"What are the top 3 risks in this brief for {geo_str} governance?",
            f"Which developments need the Chief Minister's direct attention?",
            f"What is missing from this assessment that would change the picture?",
        ],
    }
    return fallbacks.get(mode, fallbacks["SITUATION"])


# ── Govt-document retrieval (additive — mirrors retrieve_relevant_articles) ───
#
# Pool A: semantic vector search over govt_documents.labse_embedding UNION
#         govt_document_chunks.labse_embedding (best-of-doc-or-chunk per doc).
# Pool B: recency — docs in last 30 days where user_govt_doc_relevance.tier IN (1,2).
# Returns dicts tagged source_kind="govt_doc" so analyst_router can merge with articles.

GOVT_MODE_TOP_K: dict[str, int] = {
    "SITUATION":  6,
    "OPPOSITION": 4,
    "RISK":       6,
    "POLICY":     8,   # POLICY mode leans heavily on docs
    "PATTERN":    6,
    "BRIEF":      6,
}

GOVT_MODE_POOL_SIZES: dict[str, tuple[int, int]] = {
    # (semantic_k, recency_k)
    "SITUATION":  (8, 4),
    "OPPOSITION": (6, 3),
    "RISK":       (8, 4),
    "POLICY":     (10, 5),
    "PATTERN":    (8, 5),
    "BRIEF":      (8, 4),
}

GOVT_DEFAULT_TOP_K = 6
GOVT_DEFAULT_POOL: tuple[int, int] = (8, 4)
GOVT_RECENCY_DAYS = 30


async def _govt_recency_pool(
    user_id: str,
    db,
    limit: int,
    days: int = GOVT_RECENCY_DAYS,
) -> list:
    """Recent T1/T2 govt docs for this user (freshness pool)."""
    result = await db.execute(
        text("""
            SELECT
              d.id::text          AS doc_id,
              d.title,
              d.source_name,
              d.source_geography,
              d.document_type,
              d.summary,
              d.intel_json,
              d.published_at,
              d.collected_at,
              ugr.score_final,
              ugr.relevance_tier,
              ugr.urgency,
              NULL::text          AS section_heading,
              NULL::int           AS chunk_index,
              0.5::float          AS distance
            FROM user_govt_doc_relevance ugr
            JOIN govt_documents d ON d.id = ugr.doc_id
            WHERE ugr.user_id = :user_id
              AND ugr.relevance_tier IN (1, 2)
              AND d.collected_at > NOW() - make_interval(days => :days)
            ORDER BY ugr.score_final DESC, d.collected_at DESC
            LIMIT :limit
        """),
        {"user_id": user_id, "limit": limit, "days": int(days)},
    )
    return result.fetchall()


async def retrieve_relevant_govt_docs(
    query: str,
    user_id: str,
    db,
    geo_filter: list[str] | None = None,
    mode: str = "SITUATION",
    k: int | None = None,
    distance_threshold: float = 0.7,
) -> list[dict]:
    """Dual-pool retrieval over govt documents.

    Returns a list of dicts (NOT a tuple — analyst_router consumes the list
    directly and uses elapsed time only for articles). Each item:
      doc_id, title, source_name, source_geography, document_type, summary,
      intel_json, score_final, relevance_tier, urgency, section_heading,
      chunk_index, snippet, distance, source_kind="govt_doc".
    """
    start = time.time()

    semantic_k, recency_k = GOVT_MODE_POOL_SIZES.get(mode, GOVT_DEFAULT_POOL)
    top_k = k if k is not None else GOVT_MODE_TOP_K.get(mode, GOVT_DEFAULT_TOP_K)

    expanded_query = await expand_query(query=query, user_id=user_id, db=db)
    query_embedding = embed_query(expanded_query)
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    # Geo clause — restrict to docs whose source_geography matches user's monitored geos.
    geo_clause_doc = ""
    if geo_filter:
        sq_escaped = [g.replace("'", "''") for g in geo_filter]
        arr_sql = "ARRAY[" + ",".join(f"'{g}'" for g in sq_escaped) + "]"
        # Allow user-monitored geos OR national/INDIA-wide docs.
        geo_clause_doc = (
            f"AND (d.source_geography = ANY({arr_sql}) "
            f"OR d.source_geography IN ('INDIA','NATIONAL'))"
        )

    # ── Pool A: best chunk-level OR doc-level cosine per doc ──────────────────
    sem_sql = f"""
        WITH chunk_hits AS (
          SELECT
            d.id                    AS doc_id,
            c.section_heading       AS section_heading,
            c.chunk_index           AS chunk_index,
            c.page_number           AS page_number,
            c.chunk_text            AS snippet,
            (c.labse_embedding <=> CAST(:embedding AS vector)) AS distance
          FROM govt_document_chunks c
          JOIN govt_documents d ON d.id = c.document_id
          JOIN user_govt_doc_relevance ugr
            ON ugr.doc_id = d.id
            AND ugr.user_id = :user_id
          WHERE c.labse_embedding IS NOT NULL
            AND (c.labse_embedding <=> CAST(:embedding AS vector)) < :threshold
            {geo_clause_doc}
        ),
        doc_hits AS (
          SELECT
            d.id                    AS doc_id,
            NULL::text              AS section_heading,
            NULL::int               AS chunk_index,
            NULL::int               AS page_number,
            COALESCE(d.summary, LEFT(d.full_text_translated, 1000),
                     LEFT(d.full_text, 1000)) AS snippet,
            (d.labse_embedding <=> CAST(:embedding AS vector)) AS distance
          FROM govt_documents d
          JOIN user_govt_doc_relevance ugr
            ON ugr.doc_id = d.id
            AND ugr.user_id = :user_id
          WHERE d.labse_embedding IS NOT NULL
            AND (d.labse_embedding <=> CAST(:embedding AS vector)) < :threshold
            {geo_clause_doc}
        ),
        unioned AS (
          SELECT * FROM chunk_hits
          UNION ALL
          SELECT * FROM doc_hits
        ),
        ranked AS (
          SELECT
            doc_id, section_heading, chunk_index, page_number, snippet, distance,
            ROW_NUMBER() OVER (PARTITION BY doc_id ORDER BY distance ASC) AS rn
          FROM unioned
        )
        SELECT
          d.id::text                AS doc_id,
          d.title,
          d.source_name,
          d.source_geography,
          d.document_type,
          d.summary,
          d.intel_json,
          d.published_at,
          d.collected_at,
          ugr.score_final,
          ugr.relevance_tier,
          ugr.urgency,
          r.section_heading,
          r.chunk_index,
          r.page_number,
          r.snippet,
          r.distance
        FROM ranked r
        JOIN govt_documents d ON d.id = r.doc_id
        JOIN user_govt_doc_relevance ugr
          ON ugr.doc_id = d.id
          AND ugr.user_id = :user_id
        WHERE r.rn = 1
        ORDER BY r.distance ASC
        LIMIT :top_k
    """

    semantic_rows: list = []
    thresholds = [
        distance_threshold,
        min(distance_threshold + 0.1, 0.8),
        min(distance_threshold + 0.2, 0.9),
    ]
    for threshold in thresholds:
        try:
            sem_result = await db.execute(
                text(sem_sql),
                {
                    "embedding": embedding_str,
                    "user_id": user_id,
                    "threshold": threshold,
                    "top_k": semantic_k,
                },
            )
            semantic_rows = sem_result.fetchall()
        except Exception as exc:
            logger.warning(f"Govt semantic retrieval failed at threshold {threshold}: {exc}")
            semantic_rows = []
        if len(semantic_rows) >= 3:
            break

    # ── Pool B: recency T1/T2 last 30 days ────────────────────────────────────
    try:
        recency_rows = await _govt_recency_pool(
            user_id=user_id, db=db, limit=recency_k,
        )
    except Exception as exc:
        logger.warning(f"Govt recency pool failed: {exc}")
        recency_rows = []

    # ── Merge ─────────────────────────────────────────────────────────────────
    seen: set[str] = set()
    merged: list = []
    for row in semantic_rows:
        did = str(row.doc_id)
        if did not in seen:
            seen.add(did)
            merged.append(row)
    for row in recency_rows:
        did = str(row.doc_id)
        if did not in seen:
            seen.add(did)
            merged.append(row)
    merged = merged[:top_k]

    elapsed_ms = int((time.time() - start) * 1000)
    logger.info(
        f"Govt dual-pool retrieval: {len(semantic_rows)} semantic + "
        f"{len(recency_rows)} recency = {len(merged)} total "
        f"(mode={mode}, top_k={top_k}, elapsed={elapsed_ms}ms)"
    )

    docs: list[dict] = []
    for r in merged:
        # Parse intel_json defensively — it's JSONB but driver may return str or dict
        intel_raw = getattr(r, "intel_json", None)
        if isinstance(intel_raw, str):
            try:
                intel_obj = json.loads(intel_raw) if intel_raw else {}
            except json.JSONDecodeError:
                intel_obj = {}
        elif isinstance(intel_raw, dict):
            intel_obj = intel_raw
        else:
            intel_obj = {}

        snippet_raw = (r.snippet or r.summary or r.title or "")
        tier = int(r.relevance_tier) if r.relevance_tier is not None else 3
        snippet_len = 1500 if tier == 1 else 800 if tier == 2 else 500

        docs.append({
            "doc_id":           r.doc_id,
            "title":            r.title,
            "source_name":      r.source_name,
            "source_geography": r.source_geography,
            "document_type":    r.document_type,
            "summary":          r.summary,
            "intel_json":       intel_obj,
            "score_final": (
                float(r.score_final) if r.score_final is not None else 0.0
            ),
            "relevance_tier":   tier,
            "urgency":          getattr(r, "urgency", None),
            "section_heading":  getattr(r, "section_heading", None),
            "chunk_index":      getattr(r, "chunk_index", None),
            "page_number":      getattr(r, "page_number", None),
            "snippet":          snippet_raw[:snippet_len],
            "distance":         float(r.distance) if r.distance is not None else 0.5,
            "published_at": (
                r.published_at.isoformat()
                if getattr(r, "published_at", None) else None
            ),
            "collected_at": (
                r.collected_at.isoformat()
                if getattr(r, "collected_at", None) else None
            ),
            "source_kind":      "govt_doc",
        })

    return docs

