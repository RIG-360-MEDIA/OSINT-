"""Narrative pipeline — Stages 0 through 6.

The pipeline transforms scraped articles into human-quality coverage by
multi-source triangulation (Mode A) or single-source interrogation (Mode B).

Stages:
  0 — cluster assembler  (cluster 24h articles by LaBSE similarity)
  1 — frame router       (route each cluster/article to a narrative frame)
  2A — triangulation     (Mode A: cross-source agreement on SPO claims)
  2B — interrogation     (Mode B: deep single-source claim interrogation)
  3 — lede constructor   (open the piece with a strong hook)
  4 — body composer      (build the article body from triangulated claims)
  5 — critic panel       (5 parallel critics: specificity, rhythm, stance,
                          narrative gravity, anti-recap)
  6 — revision pass      (apply critic feedback to produce final draft)

Each stage is a pure function or a celery task. State flows through
`narrative_clusters` (Stage 0 output) and `narrative_drafts` (Stage 3+
output). Frame routing requires `articles.narrative_frame` to be
populated (D5 dependency).
"""
