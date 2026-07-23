"""draftsmith.stages.rank — Stage 3: evidence -> ranked, budget-fit selection.

    rank(items, plan) -> list[models.EvidenceItem]

Pure and immutable — and now EMBEDDING-FREE. The DB vector search (gather
stage) already paid the one expensive LaBSE embedding; rank reuses the cosine
signal it left behind (extra['cosine_distance']) and falls back to a cheap
lexical token-overlap for items that carry none. No I/O, no model calls: the
remote LaBSE server is ~30-40s/call, which made the old per-item embedding
fatal at this stage. Every EvidenceItem below is either passed through
unchanged or replaced via dataclasses.replace(...), never mutated. The input
`items` list/sequence itself is never modified.

Pipeline, in order:
  1. dedup by normalised URL (keep higher-tier/longer text on a collision)
  2. dedup by lexical near-duplicate (difflib ratio over the normalised leading
     text prefix; same tie-break)
  3. social bot/junk filter (short/emoji-only/duplicate-text social posts)
  4. relevance scoring: config.RELEVANCE_WEIGHTS over a vector-relevance term
     (1 - DB cosine_distance where present, else lexical overlap with the
     plan), recency decay (config.RECENCY_HALFLIFE_DAYS half-life), tier weight
  5. per-source-type selection caps (config.SELECT_CAPS)
  6. per-source-type char caps on the frozen text snapshot (config.CHAR_CAPS)
  7. trim to config.BUNDLE_TOKEN_CEILING, dropping lowest-relevance items
     first, never below config.SELECT_FLOOR for a source type

EvidenceItem carries no `selected` flag (see models.py — that flag lives on
rigwire.draft_evidence, not in the frozen contract). The items THIS function
returns ARE the selection: callers persist that via
    db.select_evidence(job_id, source_ids=[i.source_id for i in kept],
                        mark_selected=True)
exactly as db._evidence's docstring describes ("the rank stage is the only
writer of selected=true").
"""

from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional, Sequence
from urllib.parse import urlsplit

from backend.draftsmith import config
from backend.draftsmith.models import EvidenceItem, QueryPlan

logger = logging.getLogger(__name__)

__all__ = ["rank", "estimate_tokens"]

_SOCIAL_SOURCE_TYPES = frozenset(
    {"twitter", "reddit", "tiktok", "telegram", "instagram", "wechat"}
)
_MIN_SOCIAL_CHARS = 30

# Any Unicode "word" character (letter) that isn't a digit/underscore. If a
# social post's text has none of these once emoji/punctuation/whitespace are
# accounted for, it's emoji-only junk, not a citable claim.
_WORDLIKE_RE = re.compile(r"[^\W\d_]", re.UNICODE)

# Lexical-relevance / dedup tokenizer: unicode letters+digits, no underscore.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
# Minimum token length + a small stopword set so "the"/"and"/… don't inflate
# the token-overlap (Jaccard) similarity between an item and the plan.
_MIN_TOKEN_LEN = 3
_STOPWORDS = frozenset({
    "the", "and", "for", "that", "with", "from", "this", "are", "was", "were",
    "has", "have", "had", "but", "not", "you", "all", "its", "their", "them",
    "they", "then", "than", "into", "over", "after", "before", "about", "who",
    "what", "when", "where", "which", "will", "would", "can", "could", "been",
    "being", "also", "more", "most", "such", "some", "any", "per", "via", "out",
})

# Rough chars-per-token heuristic for English-ish prose (~4 chars/token is
# the commonly-cited average for GPT-family tokenizers). This is an ESTIMATE
# for budget trimming, not a real tokenizer call — precision to the token
# doesn't matter here, only "roughly under the ceiling."
_CHARS_PER_TOKEN = 4.0

# published_at is frequently absent on story_fact rows (fact-ledger entries
# aren't always dated) even though they're the highest-trust source. Scoring
# missing recency as 0 would systematically punish exactly the sources we
# want up-weighted; scoring it as "brand new" (1.0) would be worse. Neutral
# (half weight) is the least-biased default given no evidence either way.
_NEUTRAL_RECENCY = 0.5


def estimate_tokens(text: Optional[str]) -> int:
    """Rough token-count estimate for budget trimming (see _CHARS_PER_TOKEN).
    Never returns 0 for non-empty text so a 1-char string still counts."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / _CHARS_PER_TOKEN))


# --- lexical helpers (embedding-free relevance + dedup) ---------------------


def _tokenize(text: Optional[str]) -> frozenset[str]:
    """Lowercased content-token set: unicode words >= _MIN_TOKEN_LEN chars,
    stopwords dropped. Order/frequency are irrelevant for token-overlap."""
    if not text:
        return frozenset()
    return frozenset(
        tok
        for tok in (m.lower() for m in _TOKEN_RE.findall(text))
        if len(tok) >= _MIN_TOKEN_LEN and tok not in _STOPWORDS
    )


def _plan_keywords(plan: QueryPlan) -> frozenset[str]:
    """Token set describing the job's intent, for lexical relevance of items
    that carry no DB cosine signal (fts-only / story_fact / social / web /
    wiki). Union of the topic summary and every search-query keyword in the
    plan — cheap, embedding-free, computed once per rank call."""
    q = plan.queries
    parts: list[str] = [plan.topic_summary or "", q.warehouse_vector_seed or "",
                        q.facts_cluster_hint or ""]
    for seq in (q.warehouse_fts, q.web, q.youtube, q.twitter, q.reddit,
                q.tiktok, q.telegram, q.instagram, q.wechat, q.wikipedia_titles):
        parts.extend(s for s in seq if s)
    tokens: set[str] = set()
    for part in parts:
        tokens |= _tokenize(part)
    return frozenset(tokens)


def _lexical_similarity(text: Optional[str], plan_keywords: frozenset[str]) -> float:
    """Jaccard token-overlap of an item's text against the plan keywords, in
    [0, 1]. 0.0 when either side has no content tokens."""
    if not plan_keywords:
        return 0.0
    item_tokens = _tokenize(text)
    if not item_tokens:
        return 0.0
    union = item_tokens | plan_keywords
    if not union:
        return 0.0
    return len(item_tokens & plan_keywords) / len(union)


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _relevance_signal(item: EvidenceItem, plan_keywords: frozenset[str]) -> float:
    """Vector-relevance term, embedding-free. Prefer the cosine signal the DB
    vector search already computed (extra['cosine_distance'] on corpus_article
    / youtube_clip rows) as `1 - distance`; fall back to a cheap lexical
    token-overlap with the plan for every item that carries none."""
    distance = item.extra.get("cosine_distance")
    if distance is not None:
        try:
            return _clamp01(1.0 - float(distance))
        except (TypeError, ValueError):
            pass
    return _lexical_similarity(item.text, plan_keywords)


# --- dedup ---------------------------------------------------------------


def _normalize_url(url: Optional[str]) -> Optional[str]:
    """host+path, lowercased, no scheme/query/fragment/trailing slash/`www.`.
    None (never deduped on) for anything empty or hostless."""
    if not url:
        return None
    try:
        parsed = urlsplit(url.strip().lower())
    except ValueError:
        return None
    netloc = parsed.netloc
    if not netloc:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/")
    return f"{netloc}{path}"


def _better_of(a: EvidenceItem, b: EvidenceItem) -> EvidenceItem:
    """Tie-break rule shared by both dedup passes: lower trust_tier number
    (1 = best) wins; on a tie, the longer text snapshot wins."""
    key_a = (a.trust_tier, -len(a.text or ""))
    key_b = (b.trust_tier, -len(b.text or ""))
    return a if key_a <= key_b else b


def _dedup_by_url(items: Sequence[EvidenceItem]) -> list[EvidenceItem]:
    best_by_key: dict[str, EvidenceItem] = {}
    unkeyed: list[EvidenceItem] = []
    for item in items:
        key = _normalize_url(item.url)
        if key is None:
            unkeyed.append(item)
            continue
        existing = best_by_key.get(key)
        best_by_key[key] = item if existing is None else _better_of(existing, item)
    return unkeyed + list(best_by_key.values())


def _dedup_key(text: Optional[str]) -> str:
    """Normalised leading prefix used for near-duplicate comparison:
    whitespace-collapsed, lowercased, capped at config.DEDUP_TEXT_PREFIX_CHARS."""
    if not text:
        return ""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return normalized[: config.DEDUP_TEXT_PREFIX_CHARS]


def _dedup_by_text(items: Sequence[EvidenceItem]) -> list[EvidenceItem]:
    """Collapse near-duplicate text (syndicated wire copy, cross-posts) without
    embeddings, via difflib ratio over the normalised leading prefix. Best-first
    ordering (highest tier, then longest text) so the survivor of a near-dup
    cluster is always the item _better_of would have picked."""
    ordered = sorted(items, key=lambda i: (i.trust_tier, -len(i.text or "")))
    kept: list[EvidenceItem] = []
    kept_keys: list[str] = []
    for item in ordered:
        key = _dedup_key(item.text)
        if key and any(
            SequenceMatcher(None, key, other).ratio() > config.DEDUP_TEXT_RATIO
            for other in kept_keys
        ):
            continue
        kept.append(item)
        if key:
            kept_keys.append(key)
    return kept


# --- social junk filter ----------------------------------------------------


def _is_emoji_only(text: str) -> bool:
    return _WORDLIKE_RE.search(text) is None


def _filter_social_junk(items: Sequence[EvidenceItem]) -> list[EvidenceItem]:
    seen_text: set[str] = set()
    kept: list[EvidenceItem] = []
    for item in items:
        if item.source_type not in _SOCIAL_SOURCE_TYPES:
            kept.append(item)
            continue
        text = (item.text or "").strip()
        if len(text) < _MIN_SOCIAL_CHARS:
            continue
        if _is_emoji_only(text):
            continue
        normalized = re.sub(r"\s+", " ", text.lower())
        if normalized in seen_text:
            continue
        seen_text.add(normalized)
        kept.append(item)
    return kept


# --- relevance scoring -----------------------------------------------------


def _recency_decay(published_at: Optional[datetime], now: datetime) -> float:
    if published_at is None:
        return _NEUTRAL_RECENCY
    pub = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - pub).total_seconds() / 86400.0)
    return 0.5 ** (age_days / config.RECENCY_HALFLIFE_DAYS)


def _score_relevance(
    items: Sequence[EvidenceItem], plan_keywords: frozenset[str],
) -> list[EvidenceItem]:
    now = datetime.now(timezone.utc)
    weights = config.RELEVANCE_WEIGHTS
    scored: list[EvidenceItem] = []
    for item in items:
        similarity = _relevance_signal(item, plan_keywords)
        recency = _recency_decay(item.published_at, now)
        tier_weight = config.TIER_WEIGHT.get(item.trust_tier, 0.0)
        relevance = (
            weights["cosine"] * similarity
            + weights["recency"] * recency
            + weights["tier"] * tier_weight
        )
        scored.append(replace(item, relevance=round(relevance, 6)))
    return scored


# --- selection caps + char caps ---------------------------------------------


def _apply_selection_caps(items: Sequence[EvidenceItem]) -> list[EvidenceItem]:
    by_type: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in items:
        by_type[item.source_type].append(item)
    kept: list[EvidenceItem] = []
    for source_type, group in by_type.items():
        cap = config.SELECT_CAPS.get(source_type, len(group))
        ranked = sorted(group, key=lambda i: i.relevance, reverse=True)
        kept.extend(ranked[:cap])
    return kept


def _apply_char_caps(items: Sequence[EvidenceItem]) -> list[EvidenceItem]:
    capped: list[EvidenceItem] = []
    for item in items:
        cap = config.CHAR_CAPS.get(item.source_type, 0)
        text = item.text or ""
        if cap and len(text) > cap:
            text = text[:cap].rstrip() + "…"  # ellipsis marks a real truncation
            capped.append(replace(item, text=text))
        else:
            capped.append(item)
    return capped


# --- token-budget trim -------------------------------------------------------


def _trim_to_budget(items: Sequence[EvidenceItem]) -> list[EvidenceItem]:
    items = list(items)
    if not items:
        return items
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[item.source_type] += 1
    total = sum(estimate_tokens(item.text) for item in items)
    if total <= config.BUNDLE_TOKEN_CEILING:
        return items

    keep = [True] * len(items)
    # lowest-relevance-first: sort indices ascending by relevance
    order = sorted(range(len(items)), key=lambda idx: items[idx].relevance)
    for idx in order:
        if total <= config.BUNDLE_TOKEN_CEILING:
            break
        item = items[idx]
        floor = config.SELECT_FLOOR.get(item.source_type, 0)
        if counts[item.source_type] <= floor:
            continue  # protected: dropping this would breach the hard floor
        keep[idx] = False
        counts[item.source_type] -= 1
        total -= estimate_tokens(item.text)
    return [item for item, k in zip(items, keep) if k]


# --- entry point -------------------------------------------------------------


async def rank(items: Sequence[EvidenceItem], plan: QueryPlan) -> list[EvidenceItem]:
    """Stage 3 — evidence -> the final, budget-fit, relevance-scored
    selection that stage 4 (brief.build_brief) assembles into the BRIEF.

    Embedding-free: relevance reuses the DB vector search's cosine signal where
    present and a cheap lexical overlap otherwise, and dedup is URL + lexical
    near-duplicate. No model calls are made here.

    Returns [] for an empty `items` input (nothing to rank is not an error).
    Raises ValueError if `plan` is missing — every other failure mode (an
    unrecognised source_type, missing recency, a non-numeric cosine signal) is
    handled by falling back to a safe default and logging, never by raising, so
    one bad evidence item can never take down the whole ranking pass.
    """
    if plan is None:
        raise ValueError("rank: plan is required")
    if not items:
        return []

    working = _dedup_by_url(items)
    working = _dedup_by_text(working)
    working = _filter_social_junk(working)
    working = _score_relevance(working, _plan_keywords(plan))
    working = _apply_selection_caps(working)
    working = _apply_char_caps(working)
    working = _trim_to_budget(working)
    return working
