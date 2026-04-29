# Brief — Output Quality Scorecard

**Method:** Generate three briefs for the same test user across three days. Score each across nine dimensions on a 1–5 scale. Cross-reference claims in the brief against the source articles in `articles` (pulled by `articles_used` count and the SOURCE COVERAGE section).

Test user: `db4b9207-51aa-4d39-a7bf-e6fab34c3465` (the only user with briefs in DB).

---

## Generation 1 — 2026-04-23 (30 articles)

| Dimension | 1–5 | Notes |
|---|---:|---|
| Factual accuracy (claims match source articles) | TBD | Compare each numbered KEY DEVELOPMENTS item against the corresponding article in `articles_used` set. |
| Recency (anything >24h old presented as "today") | TBD | Cross-check `published_at` of the 30 articles. With D-BRIEF-5 unfixed, expect leakage. |
| De-duplication (same story across sections?) | TBD | Manually scan SITUATION + DEVELOPMENTS + ENTITIES for repeats. |
| Role/geo personalization actually visible | TBD | Look for explicit role mentions ("for the {role_context}"). |
| Entity coverage matches `user_entities` | TBD | Diff entities mentioned in ENTITIES TODAY vs. `user_entities` table for this user. |
| Source diversity (count distinct domains in SOURCE COVERAGE) | TBD | |
| **Govt-doc presence** | **0 / 5** | **Architectural — D-BRIEF-1. No govt docs ever reach the brief.** |
| Hallucination check (entities/numbers not in input?) | TBD | Sample 3 numeric claims, verify each appears in source article text. |
| Markdown rendering correctness (every section appears in UI) | TBD | Check D-BRIEF-13 — section parser drops malformed headers. |

## Generation 2 — 2026-04-20 (30 articles)

(Same table.)

## Generation 3 — 2026-04-18 (17 articles — sub-30 case)

(Same table. Specifically watch for thin-content fallback behavior.)

---

## Aggregated findings (fill after running)

- Mean score across dimensions: ___
- Lowest-scoring dimension across all 3: ___
- Top 3 quality issues observed (with brief excerpts): ___

## Reproduction commands

```bash
# Pull the three briefs from DB
docker exec rig-postgres psql -U rig -d rig -c \
  "SELECT brief_date, articles_used, content FROM briefs \
   WHERE user_id = 'db4b9207-51aa-4d39-a7bf-e6fab34c3465' \
   ORDER BY brief_date DESC;" > /tmp/briefs.txt

# Pull the article set used (approximate — relevance scores may have shifted)
docker exec rig-postgres psql -U rig -d rig -c \
  "SELECT a.title, a.published_at, s.domain, uar.score_final \
   FROM user_article_relevance uar \
   JOIN articles a ON a.id = uar.article_id \
   JOIN sources s ON s.id = a.source_id \
   WHERE uar.user_id = 'db4b9207-51aa-4d39-a7bf-e6fab34c3465' \
     AND uar.relevance_tier IN (1,2) \
   ORDER BY uar.relevance_tier ASC, uar.score_final DESC LIMIT 30;"
```

---

## Note on objectivity

These scores are subjective. Two reviewers should score independently and reconcile. The scorecard is a structured way to make qualitative impressions auditable, not a calibrated metric.
