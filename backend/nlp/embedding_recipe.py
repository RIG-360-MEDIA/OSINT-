"""
embedding_recipe.py — single source of truth for the LaBSE embedding INPUT recipe.

WHY THIS EXISTS: 0a (embed-at-ingest) and 0c (full re-embed) MUST produce
byte-identical vectors, or the pgvector/HNSW index mixes incompatible spaces and
similarity search silently degrades. Both import the recipe from HERE so there is
exactly one definition.

Until the Embedding-Recipe A/B returns a winner
(rig-news/docs/plans/embedding-recipe-ab-2026-05-30.md), RECIPE is the CURRENT
PRODUCTION recipe — i.e. A/B variant V0:
    translated lead · no title · 512 chars · max_seq_length 256.

>>> LOCK STEP (after the A/B): set RECIPE to the winning variant, bump
    recipe_version, then (1) run 0c full re-embed and (2) deploy 0a — both read
    this module, so the flip is one edit here. <<<
"""
from __future__ import annotations

from dataclasses import dataclass

# Pinned model snapshot — changing this REQUIRES a coordinated full re-embed (0c).
LABSE_MODEL_ID = "sentence-transformers/LaBSE"
LABSE_REVISION = "836121a0533e5664b21c7aacc5d22951f2b8b25b"


@dataclass(frozen=True)
class EmbeddingRecipe:
    """Immutable description of how raw article fields become embedding input."""

    language: str          # 'original' | 'translated'
    title_prepend: bool    # prepend the (full) title before the body
    char_window: int       # chars of BODY embedded (title, if used, is added in full)
    max_seq_length: int    # LaBSE token cap actually applied at encode time
    recipe_version: str    # bump on every lock so provenance (embedding_revision) is traceable
    model_id: str = LABSE_MODEL_ID
    model_rev: str = LABSE_REVISION


# LOCKED 2026-05-31 to A/B winner V4 (analytics confirm: rig-news db-chat-confirm-v4-2026-05-31).
# translated lead + title prepended, 1024-char window, max_seq_length 512.
# Chosen over original (V1): A2 showed original-language *coin-flips* catastrophically on
# low-resource cross-lingual (the Telugu Harmanpreet twin cratered to rank ~700 under
# original, held top-few under translated). V4 is reliable cross-lingual AND barely a
# change from prod-V0 (already translated/512) — it just adds title + 1024.
# 0a (embed-at-ingest) and 0c (full re-embed) BOTH read this. Changing it again ==
# a coordinated full re-embed. translated => reads existing lead_text_translated (no NEW MT call).
RECIPE = EmbeddingRecipe(
    language="translated",
    title_prepend=True,
    char_window=1024,
    max_seq_length=512,
    recipe_version="v4-tr-title-1024",
)


def build_embedding_text(
    recipe: EmbeddingRecipe,
    *,
    title: str | None,
    lead_original: str | None,
    lead_translated: str | None,
) -> str:
    """Assemble the exact text to embed for the given recipe.

    Identical logic to scripts/maintenance/embed_recipe_ab.py::build_text so the
    A/B winner maps onto production with no behavioural drift.
    """
    body_src = lead_original if recipe.language == "original" else lead_translated
    body = (body_src or "")[: recipe.char_window]
    if recipe.title_prepend and (title or "").strip():
        return title.strip() + "\n" + body
    return body
