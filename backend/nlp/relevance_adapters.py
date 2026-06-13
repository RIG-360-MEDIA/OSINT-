"""Cross-pillar adapters — map a clip (youtube_clips_v2) or cutting (clippings) row to the
article-dict shape the v3 relevance scorer expects, so the SAME scorer ranks all pillars (#9).

Honest gaps (until the #9 entity backfill lands):
  - clips carry NO geo and entities are `{name}` only (no type/prominence) → geo component
    dead, entity weighting flatter.
  - cuttings carry `{name,type}` (no prominence) + geo + edition_date → entity+topic+geo+recency
    all work, only prominence defaults.
Both default missing fields safely; the scorer never crashes on a thin object.
"""
from __future__ import annotations


def clip_to_article_dict(c: dict) -> dict:
    """youtube_clips_v2 row → article-dict. published_at ← video_published_at; no geo."""
    return {
        "id": c.get("id"),
        "title": c.get("video_title") or c.get("primary_subject") or "",
        "lead_text_translated": c.get("summary") or c.get("transcript_segment") or "",
        "lead_text_original": "",
        "topic_category": c.get("topic_category") or "",
        "geo_primary": None,                       # clips have no geo yet
        "source_tier": 2,
        "entities_extracted": c.get("entities_extracted") or [],
        "nlp_confidence": None,                     # clip 'confidence' is a float, not low/high
        "published_at": c.get("video_published_at"),
        "source_name": c.get("channel_name"),
    }


def cutting_to_article_dict(c: dict) -> dict:
    """clippings row → article-dict. published_at ← edition_date; has topic + geo + {name,type}."""
    return {
        "id": c.get("id"),
        "title": c.get("headline_translated") or c.get("headline") or "",
        "lead_text_translated": c.get("body_text_translated") or c.get("summary_preview") or "",
        "lead_text_original": c.get("body_text") or "",
        "topic_category": c.get("topic_category") or "",
        "geo_primary": c.get("geo_primary"),
        "source_tier": 2,
        "entities_extracted": c.get("entities_extracted") or [],
        "nlp_confidence": None,
        "published_at": c.get("edition_date"),
        "source_name": None,
    }


# columns each adapter reads (for the relevance pass SELECTs)
CLIP_COLS = ["id", "video_title", "primary_subject", "summary", "transcript_segment",
             "topic_category", "entities_extracted", "video_published_at", "channel_name"]
CUTTING_COLS = ["id", "headline", "headline_translated", "body_text", "body_text_translated",
                "summary_preview", "topic_category", "geo_primary", "entities_extracted",
                "edition_date"]
