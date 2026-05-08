"""
Per-user relevance scorer for /coverage/articles surfaces.

Replaces the binary "is this exact article in your feed?" filter with a
multi-signal continuous score. Works for clusters (Breaking), articles
(Top stories), entities (Coverage gaps), and speakers (Quotes).

Core ideas:
  - Load a UserInterestProfile once per request, cached in-process
    for 5 minutes per user_id.
  - Score every candidate against the profile via 4-5 weighted signals.
  - Sort descending, apply threshold, return top N.

Why ranking beats filtering:
  - One signal failing (e.g. relevance scorer didn't tier-1 a cluster's
    articles) doesn't drop the whole cluster — entity overlap or
    geo can rescue it.
  - Continuous scores let us cap surfaces (top 5) and rank cleanly.
  - Naturally degrades: a user with a thin profile gets a thinner page
    rather than a noisy one.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text


# ── Profile shape ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserInterestProfile:
    """
    Snapshot of what a user actually cares about. Built from their
    user_article_relevance history (tier-1/2 last 14 days).

    `entity_weights` maps lowercased canonical entity name → 0-1 weight,
    where the most-frequent entity in the user's strong feed is 1.0
    and others scale linearly down.
    """
    user_id: str
    # canonical-name (lowercased) -> weight 0-1
    entity_weights: dict[str, float] = field(default_factory=dict)
    # subset of entity_weights keys that are PERSON-typed
    person_set: frozenset[str] = field(default_factory=frozenset)
    # most-frequent geo_primary in their tier-1/2 feed
    geo_primary: str | None = None
    # topic_category -> 0-1 affinity, derived from tier-1/2 engagement rate.
    # An admin who reads governance / security / politics avidly and almost
    # never touches sports gets sports ≈ 0.05 and governance ≈ 1.0, so a
    # cricket-toss cluster can no longer outrank a press-conference cluster
    # purely on entity match.
    topic_weights: dict[str, float] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.entity_weights


# ── Indian-states bucket for geo proximity ──────────────────────────────────
# Crude but effective for the current corpus (India-focused). Two geos
# in this set are "near each other" for scoring purposes.

_INDIAN_GEO = frozenset({
    "telangana", "andhra pradesh", "tamil nadu", "karnataka", "kerala",
    "maharashtra", "gujarat", "rajasthan", "uttar pradesh", "bihar",
    "west bengal", "odisha", "punjab", "haryana", "delhi", "goa",
    "assam", "mumbai", "hyderabad", "bengaluru", "chennai", "kolkata",
    "india", "jammu and kashmir", "puducherry", "chandigarh",
    "madhya pradesh", "chhattisgarh", "jharkhand", "uttarakhand",
    "himachal pradesh", "tripura", "manipur", "meghalaya", "nagaland",
    "mizoram", "arunachal pradesh", "sikkim",
})


def _is_geo_proximate(a: str | None, b: str | None) -> float:
    """0-1 score for how close two geo strings are."""
    if not a or not b:
        return 0.0
    al, bl = a.strip().lower(), b.strip().lower()
    if al == bl:
        return 1.0
    if al in _INDIAN_GEO and bl in _INDIAN_GEO:
        return 0.6
    return 0.05


# ── Profile cache (in-process, 5 min TTL per user) ──────────────────────────


_PROFILE_CACHE: dict[str, tuple[float, UserInterestProfile]] = {}
_PROFILE_TTL_SECONDS = 300.0
_PROFILE_LOCK = asyncio.Lock()


async def load_user_profile(user_id: str, db) -> UserInterestProfile:
    """
    Build a UserInterestProfile from user_article_relevance.

    Cached per user_id with a 5-minute TTL. Cache is in-process and
    best-effort — multiple workers will compute independently.
    """
    now = time.monotonic()
    cached = _PROFILE_CACHE.get(user_id)
    if cached and (now - cached[0] < _PROFILE_TTL_SECONDS):
        return cached[1]

    async with _PROFILE_LOCK:
        # Re-check inside lock in case another coroutine just populated it.
        cached = _PROFILE_CACHE.get(user_id)
        if cached and (now - cached[0] < _PROFILE_TTL_SECONDS):
            return cached[1]

        # ── Entity frequencies from tier-1/2 feed last 14d ─────────────
        result = await db.execute(
            text(
                """
                SELECT LOWER(unnest(uar.matched_entity_names)) AS name,
                       COUNT(*) AS n
                FROM user_article_relevance uar
                WHERE uar.user_id = :uid
                  AND uar.relevance_tier IN (1, 2)
                  AND uar.scored_at > NOW() - interval '14 days'
                  AND uar.matched_entity_names IS NOT NULL
                GROUP BY 1
                ORDER BY n DESC
                LIMIT 200
                """
            ),
            {"uid": user_id},
        )
        rows = result.fetchall()

        if not rows:
            profile = UserInterestProfile(user_id=user_id)
            _PROFILE_CACHE[user_id] = (now, profile)
            return profile

        max_n = max(r.n for r in rows) or 1
        entity_weights: dict[str, float] = {
            r.name: r.n / max_n for r in rows if r.name
        }

        # ── Persons subset ─────────────────────────────────────────────
        names = list(entity_weights.keys())
        person_result = await db.execute(
            text(
                """
                SELECT LOWER(canonical_name) AS name
                FROM entity_dictionary
                WHERE LOWER(canonical_name) = ANY(:names)
                  AND entity_type = 'PERSON'
                """
            ),
            {"names": names},
        )
        persons = frozenset(r.name for r in person_result.fetchall())

        # ── Most-frequent geo in their strong feed ─────────────────────
        geo_result = await db.execute(
            text(
                """
                SELECT a.geo_primary, COUNT(*) AS n
                FROM user_article_relevance uar
                JOIN articles a ON a.id = uar.article_id
                WHERE uar.user_id = :uid
                  AND uar.relevance_tier IN (1, 2)
                  AND uar.scored_at > NOW() - interval '14 days'
                  AND a.geo_primary IS NOT NULL
                GROUP BY a.geo_primary
                ORDER BY n DESC
                LIMIT 1
                """
            ),
            {"uid": user_id},
        )
        geo_row = geo_result.fetchone()
        geo_primary = geo_row.geo_primary if geo_row else None

        # ── Topic affinity ──────────────────────────────────────────────
        # Per-topic strong-engagement rate over the last 14 days. We use
        # rate (not raw count) so a user who reads ALL of a small topic
        # area scores it high even if absolute volume is small. Normalised
        # to 0-1 against the user's own peak rate so shapes vary by user.
        topic_result = await db.execute(
            text(
                """
                SELECT a.topic_category AS topic,
                       COUNT(*) FILTER (WHERE uar.relevance_tier IN (1, 2))::float
                         / NULLIF(COUNT(*), 0)::float AS rate
                FROM user_article_relevance uar
                JOIN articles a ON a.id = uar.article_id
                WHERE uar.user_id = :uid
                  AND uar.scored_at > NOW() - interval '14 days'
                  AND a.topic_category IS NOT NULL
                GROUP BY a.topic_category
                HAVING COUNT(*) >= 20  -- need a baseline to avoid noise
                """
            ),
            {"uid": user_id},
        )
        topic_rows = topic_result.fetchall()
        if topic_rows:
            peak = max(r.rate for r in topic_rows if r.rate is not None) or 1.0
            topic_weights = {
                r.topic: (r.rate / peak) if r.rate else 0.0
                for r in topic_rows if r.topic
            }
        else:
            topic_weights = {}

        profile = UserInterestProfile(
            user_id=user_id,
            entity_weights=entity_weights,
            person_set=persons,
            geo_primary=geo_primary,
            topic_weights=topic_weights,
        )
        _PROFILE_CACHE[user_id] = (now, profile)
        return profile


# ── Cluster scoring ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClusterScore:
    total: float
    entity: float
    geo: float
    person: float
    velocity: float
    topic: float
    matched_entities: tuple[str, ...]


# Weights — tunable. The four "match" signals are additive, summing to 1.0.
# Topic affinity is then applied as a MULTIPLIER on the resulting base score
# (range 0.4 - 1.0). This is deliberate: a 15% additive topic component was
# too weak to demote sport-with-matching-geo clusters below politics-with-
# fuzzy-geo clusters for a politics-focused admin. The multiplier model says
# "even a perfect entity+geo+velocity match is worth less if you don't care
# about the topic at all" — which mirrors human attention.
_W_ENTITY   = 0.50
_W_GEO      = 0.25
_W_PERSON   = 0.15
_W_VELOCITY = 0.10

# Topic multiplier floor: a cluster on a topic the user has never engaged
# with still gets 40% credit (gives new-topic discovery a fighting chance),
# scaling up to 100% as topic affinity → 1.0.
_TOPIC_MULTIPLIER_FLOOR = 0.40

# Surface threshold — clusters below this score are hidden entirely.
SURFACE_THRESHOLD = 0.25


def score_cluster(
    *,
    cluster_entities: set[str],     # lowercased entity names from member articles
    cluster_geos: list[str | None],  # geo_primary of each member article
    cluster_age_minutes: float,
    sources_count: int,
    profile: UserInterestProfile,
    cluster_topics: list[str | None] | None = None,  # topic_category of each member article
) -> ClusterScore:
    """
    Score a single breaking cluster against a user profile. 0-1 range.

    Components:
      entity   — weighted overlap of cluster entities with user's tracked set
      geo      — proximity of any cluster geo to user's primary geo
      person   — bonus when cluster mentions someone the user tracks
      velocity — how fast sources are joining (real bursts vs slow burns)
      topic    — affinity of cluster's topic_category with user's history.
                 SPORTS for a politics-focused admin → low. POLITICS for
                 the same admin → high. Prevents cricket-toss clusters
                 from outranking civic events on entity match alone.
    """
    if profile.is_empty():
        return ClusterScore(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ())

    # ── Entity overlap (count AND weight, take the stronger signal) ─────
    matched: list[tuple[str, float]] = []
    for name in cluster_entities:
        w = profile.entity_weights.get(name)
        if w:
            matched.append((name, w))

    overlap_count = len(matched)
    top_weight = max((w for _, w in matched), default=0.0)
    # Count signal: 1 match = 0.4, 2 = 0.7, 3+ = 1.0.
    # Weight signal: how dominant the strongest matched entity is for
    # the user. A single match on a top-3 tracked entity is enough.
    # Take the stronger of the two so we don't punish single-but-strong
    # matches (e.g. cluster squarely about "Telangana") nor multiple
    # mid-tier matches (cluster about West Bengal politics with several
    # tracked players).
    count_contribution = min(1.0, overlap_count / 3.0) if overlap_count else 0.0
    weight_contribution = top_weight
    entity_score = max(count_contribution, weight_contribution)

    # ── Geo proximity (best of any member article) ──────────────────────
    geo_score = 0.0
    if profile.geo_primary:
        for g in cluster_geos:
            geo_score = max(geo_score, _is_geo_proximate(g, profile.geo_primary))

    # ── Person mention bonus ────────────────────────────────────────────
    persons_in_cluster = cluster_entities & profile.person_set
    person_score = min(1.0, len(persons_in_cluster) / 2.0)

    # ── Velocity (sources/hr) ───────────────────────────────────────────
    if cluster_age_minutes > 0:
        rate_per_hour = sources_count / (cluster_age_minutes / 60.0)
        velocity_score = min(1.0, rate_per_hour / 4.0)  # 4 sources/hr saturates
    else:
        velocity_score = 0.5

    # ── Topic affinity ──────────────────────────────────────────────────
    # Take the strongest topic_weight across the cluster's member articles
    # (i.e. give the cluster credit for whichever member best matches the
    # user's reading habits). If no topic data, fall back to neutral 0.5
    # rather than 0 so untagged clusters aren't unfairly penalised.
    topic_score = 0.0
    if profile.topic_weights and cluster_topics:
        best = max(
            (profile.topic_weights.get(t or "", 0.0) for t in cluster_topics),
            default=0.0,
        )
        topic_score = best
    elif not profile.topic_weights:
        topic_score = 0.5  # user has no topic signal yet — be neutral

    base = (
        _W_ENTITY   * entity_score
        + _W_GEO      * geo_score
        + _W_PERSON   * person_score
        + _W_VELOCITY * velocity_score
    )
    # Multiplicative topic gate. Floor at 0.40 so unfamiliar topics aren't
    # silently zeroed out, ceiling at 1.0 when affinity is at user's peak.
    topic_multiplier = _TOPIC_MULTIPLIER_FLOOR + (
        (1.0 - _TOPIC_MULTIPLIER_FLOOR) * topic_score
    )
    total = base * topic_multiplier

    matched_names = tuple(name for name, _ in sorted(matched, key=lambda t: -t[1])[:5])

    return ClusterScore(
        total=total,
        entity=entity_score,
        geo=geo_score,
        person=person_score,
        velocity=velocity_score,
        topic=topic_score,
        matched_entities=matched_names,
    )


# ── Article scoring (Top-5, story-level) ─────────────────────────────────────


def score_article(
    *,
    article_entities: set[str],
    article_geo: str | None,
    profile: UserInterestProfile,
    base_relevance: float = 0.0,
) -> float:
    """
    Lighter scorer for individual articles (no velocity, no cluster-level
    aggregation). `base_relevance` is the relevance scorer's score_final
    if available — included as a stabilising prior.
    """
    if profile.is_empty():
        return base_relevance

    entity_raw = sum(
        profile.entity_weights.get(name, 0.0) for name in article_entities
    )
    entity_score = min(1.0, entity_raw / 2.0)

    geo_score = (
        _is_geo_proximate(article_geo, profile.geo_primary)
        if profile.geo_primary else 0.0
    )

    persons = article_entities & profile.person_set
    person_score = min(1.0, len(persons) / 1.5)

    return (
        0.40 * entity_score
        + 0.20 * geo_score
        + 0.15 * person_score
        + 0.25 * min(1.0, base_relevance)
    )


# ── Helpers exported for SQL filters ────────────────────────────────────────


def profile_entity_names(profile: UserInterestProfile) -> list[str]:
    """Plain list of tracked entity names (lowercased) for use in SQL ANY()."""
    return list(profile.entity_weights.keys())


def profile_top_entity_names(profile: UserInterestProfile, n: int = 50) -> list[str]:
    """Top-N tracked entities by weight."""
    return [
        name for name, _ in sorted(
            profile.entity_weights.items(), key=lambda t: -t[1]
        )[:n]
    ]
