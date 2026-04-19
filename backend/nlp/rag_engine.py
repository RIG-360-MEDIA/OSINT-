"""
RAG engine — semantic retrieval, context building, mode detection,
confidence scoring, and follow-up generation for the Analyst workspace.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime

from sqlalchemy import text

logger = logging.getLogger(__name__)

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
— Every factual claim tied to a specific article in context
— Never say 'based on the documents' — you are the analyst
— Give a clear read then qualify
— If coverage is thin, say so directly and name what is missing
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


async def retrieve_relevant_articles(
    query: str,
    user_id: str,
    db,
    top_k: int = 10,
    distance_threshold: float = 0.7,
    geo_filter: list[str] | None = None,
) -> tuple[list[dict], str, int]:
    """
    Retrieve articles relevant to the query via LaBSE semantic search.

    Strategy:
    1. Embed query with LaBSE
    2. HNSW cosine search on labse_embedding, distance < threshold
    3. Filter to user's scored articles (user_article_relevance)
    4. Fallback to full-text search if < 3 semantic results
    5. Return (articles, retrieval_method, elapsed_ms)
    """
    start = time.time()

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
        "top_k": top_k,
    }
    # geo_clause is inlined — no extra param binding needed

    # Dynamic threshold — expand until ≥5 results
    rows = []
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
        rows = sem_result.fetchall()
        if len(rows) >= 5:
            break
        logger.info(f"Threshold {threshold}: {len(rows)} results, expanding")

    if len(rows) < 3:
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
            "top_k": top_k,
        })
        rows = ft_result.fetchall()

    # Third fallback: top scored T1/T2 articles — never return empty
    if len(rows) < 3:
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
        rows = recency_result.fetchall()

    elapsed_ms = int((time.time() - start) * 1000)

    articles = []
    for r in rows:
        raw_text = (
            r.lead_text_translated
            or r.lead_text_original
            or r.title
            or ""
        )
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
            "text_snippet": raw_text[:600],
            "distance": float(r.distance),
        })

    return articles, retrieval_method, elapsed_ms


# ── Context builder ───────────────────────────────────────────────────────────

def build_context(
    articles: list[dict],
    user_profile: dict,
    session_history: list[dict],
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

        article_items.append(
            f"[{i}] {a['title']}\n"
            f"Source: {a['source_name']} | Date: {date_str}"
            f" | Topic: {a.get('topic_category', '')}"
            f" | Geo: {a.get('geo_primary', '')}"
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

    return (
        f"OFFICIAL PROFILE:\n"
        f"Role: {role}\n"
        f"Focus Geography: {geo}\n"
        f"{session_context}\n\n"
        f"CRITICAL RULE: You may ONLY reference events, actors, and facts that appear "
        f"in the INTELLIGENCE CORPUS below. Do NOT introduce external knowledge, "
        f"global events, or speculation about topics not present in these articles. "
        f"If the corpus is thin on a topic, say so explicitly rather than filling gaps "
        f"with outside knowledge.\n\n"
        f"INTELLIGENCE CORPUS ({len(articles)} articles):\n\n"
        + "\n---\n".join(article_items)
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

def compute_confidence(articles: list[dict], retrieval_method: str) -> tuple[str, int]:
    """
    Compute confidence label and percentage from actual article quality.

    Weighted: tier(0.35) + recency(0.25) + volume(0.25) + method(0.15).
    Returns (label, percentage) e.g. ("HIGH", 87).
    """
    from datetime import datetime, timezone

    if not articles:
        return "LOW", 15

    total = len(articles)

    tier_weights = {1: 1.0, 2: 0.7, 3: 0.3}
    tier_avg = sum(tier_weights.get(a.get("relevance_tier", 3), 0.3) for a in articles) / total

    now = datetime.now(timezone.utc)
    recency_scores: list[float] = []
    for a in articles:
        collected = a.get("collected_at")
        score = 0.5
        if collected:
            try:
                dt = datetime.fromisoformat(str(collected).replace("Z", "+00:00")) if isinstance(collected, str) else collected
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_days = (now - dt).total_seconds() / 86400
                score = 1.0 if age_days < 1 else (0.8 if age_days < 7 else (0.5 if age_days < 30 else 0.2))
            except Exception:
                pass
        recency_scores.append(score)
    recency_avg = sum(recency_scores) / len(recency_scores)

    volume_score = 1.0 if total >= 8 else (0.75 if total >= 5 else (0.5 if total >= 3 else 0.25))

    method_score = {"semantic": 1.0, "fulltext": 0.7, "recency": 0.4}.get(retrieval_method, 0.7)

    raw = tier_avg * 0.35 + recency_avg * 0.25 + volume_score * 0.25 + method_score * 0.15
    pct = max(15, min(95, int(raw * 100)))
    label = "HIGH" if pct >= 75 else ("MEDIUM" if pct >= 50 else "LOW")

    return label, pct


# ── Follow-up generator ───────────────────────────────────────────────────────

_FALLBACK_FOLLOWUPS: dict[str, list[str]] = {
    "SITUATION": [
        "What are the warning signs to watch in the next 14 days?",
        "How is the opposition responding to this situation?",
        "What should the administration prepare for?",
    ],
    "OPPOSITION": [
        "What is their likely next move?",
        "What are their key vulnerabilities right now?",
        "How has their strategy shifted over the last month?",
    ],
    "RISK": [
        "What would trigger escalation to a crisis?",
        "What precedents exist for this pattern?",
        "What would resolution look like and how likely is it?",
    ],
    "POLICY": [
        "Which departments face the most implementation pressure?",
        "What is the likely legal challenge to this decision?",
        "What does this mean for the next budget cycle?",
    ],
    "PATTERN": [
        "What is the buried signal most worth pursuing?",
        "Which silent actor's position matters most here?",
        "What single data point would most change this analysis?",
    ],
    "BRIEF": [
        "What are the risk indicators I should monitor daily?",
        "What intelligence gaps are most urgent to fill?",
        "When should I request the next update?",
    ],
}


async def generate_followups(
    question: str,
    mode: str,
    articles: list[dict],
) -> list[str]:
    """Generate 3 contextual follow-up questions using FAST_MODEL."""
    from backend.nlp.groq_client import call_groq, FAST_MODEL

    article_titles = "\n".join(f"- {a['title']}" for a in articles[:5])

    try:
        result = await call_groq(
            system=(
                "Generate exactly 3 follow-up investigation questions based on "
                "this analysis. Each question should go deeper or explore a "
                "different angle. Output as a JSON array of 3 strings only. "
                "No other text."
            ),
            user=(
                f"Mode: {mode}\nQuestion: {question}\n"
                f"Key articles:\n{article_titles}"
            ),
            task_type="profile_extraction",
            model=FAST_MODEL,
            json_response=True,
        )
        parsed = json.loads(result) if isinstance(result, str) else result
        if isinstance(parsed, list) and parsed:
            return [str(q) for q in parsed[:3]]
    except Exception:
        pass

    return _FALLBACK_FOLLOWUPS.get(mode, _FALLBACK_FOLLOWUPS["SITUATION"])
