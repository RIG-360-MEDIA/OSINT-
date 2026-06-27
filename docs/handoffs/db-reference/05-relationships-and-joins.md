# Relationships & join recipes

The 73 foreign keys in the live DB, grouped by hub, plus the join patterns the products actually use.
`child.column → parent` notation. Self-references and cross-schema FKs are flagged.

## Hub: `articles` (the corpus spine)
Everything article-related FKs to `articles(id)`:
- `article_claims.article_id`, `article_stances.article_id`, `article_quotes.article_id`,
  `article_numbers.article_id`, `article_events.article_id`, `article_locations.article_id`,
  `article_links.article_id`, `article_media.article_id`, `article_tweets.article_id`
- `article_districts.article_id`, `user_article_relevance.article_id`
- `articles.duplicate_of → articles` (self-FK: dedup chain), `articles.source_id → sources`
- `article_events.event_cluster_id → event_clusters_archive` (older product event layer)

## Hub: `entity_dictionary` (canonical entities)
The substrate's entity columns across ALL pillars resolve here:
- `article_claims.subject_entity_id`, `article_quotes.speaker_entity_id`, `article_stances.actor_entity_id`
  (⚠ `actor_entity_id` = the **target** of sentiment, see corpus doc), `article_contradictions.entity_id`
- `clipping_claims.subject_entity_id`, `clipping_quotes.speaker_entity_id`, `clipping_stances.actor_entity_id`
- `newsroom_entity_mentions.entity_id`, `newsroom_segments.speaker_entity_id`
- `entity_lookup.entity_id → entity_dictionary` (the resolution table)
- `user_watched_entities.entity_id`, `coverage_gaps_daily.entity_id`

## Hub: `clippings` (cuttings pillar)
- `clipping_claims/_events/_locations/_numbers/_quotes/_stances.clipping_id → clippings`
- `clippings.newspaper_source_id → newspaper_sources`
- (legacy) `newspaper_clippings.newspaper_id`, `newspaper_editions.newspaper_id → newspaper_sources`

## Hub: `youtube_clips_v2` (clips pillar — note: v2, NOT legacy `youtube_clips`)
- `youtube_clip_claims/_locations/_quotes/_stances.clip_id → youtube_clips_v2`

## Hub: `districts` (CM-v2 atlas, 59-row gazetteer)
- `article_districts.district_id`, `acled_events.district_id`, `air_quality_readings.district_id`,
  `mandi_prices.district_id`, `power_grid_status.district_id`, `weather_warnings.district_id`,
  `welfare_coverage.district_id` (most of these collector sinks are EMPTY/PLANNED)

## Hub: `newsroom_*` (the /clips redesign, currently stalled)
- `newsroom_segments.broadcast_id → newsroom_broadcasts`, `newsroom_broadcasts.channel_id → newsroom_channels`
- `newsroom_entity_mentions.segment_id → newsroom_segments`, `newsroom_breaking_segments.segment_id → newsroom_segments`

## Hub: `public.users` (the older/product user system)
- `analyst_sessions.user_id`, `analyst_turns.session_id → analyst_sessions`
- `briefs.user_id`, `brief_quality_scores.user_id`, `user_article_relevance.user_id`,
  `user_entities.user_id`, `user_govt_doc_relevance.user_id`, `user_profiles.user_id`,
  `user_page_access.user_id` + `user_page_access.granted_by`, `user_cards.parent_card_id → user_cards` (self)
- `impersonation_sessions.admin_id` + `.target_user_id → users`, `impersonation_actions.session_id → impersonation_sessions`

## Hub: `analytics.users` + Chronicle (the night-desk system — separate from public.users)
- `analytics.users.invited_by → analytics.users` (self), `analytics.users.org_id → analytics.orgs`
- `analytics.user_brief_prefs.user_id → analytics.users`
- `analytics.user_story_assignments.story_id → analytics.story_clusters_archive` ⚠
- `analytics.chronicle_cache.story_id → analytics.story_clusters_archive` ⚠
- `analytics.story_clusters_archive.redirected_to → analytics.story_clusters_archive` (self)
  ⚠ **These three FKs point at the OLD `story_clusters_archive`, not the live `_v8` keeper — this is the
  Chronicle naming mismatch (see 30-clustering-stories.md / 90-known-issues).**

## Infra
- `kombu_message.queue_id → kombu_queue` (Celery broker)

---

## Common join recipes

**All substrate extracted from one article:**
```sql
SELECT * FROM articles a
LEFT JOIN article_claims  c ON c.article_id = a.id
LEFT JOIN article_quotes  q ON q.article_id = a.id
LEFT JOIN article_stances s ON s.article_id = a.id
LEFT JOIN article_events  e ON e.article_id = a.id
WHERE a.id = :article_id;
```

**Every mention of an entity across all pillars** (the alias-resolved way):
```sql
-- articles
SELECT 'article' src, article_id item_id FROM article_entity_mentions WHERE entity_id = :eid
UNION ALL
SELECT 'clipping', clipping_id FROM clipping_entity_mentions WHERE entity_id = :eid
UNION ALL
SELECT 'clip', clip_id FROM youtube_clip_entity_mentions WHERE entity_id = :eid;
-- (matviews; refreshed every 30 min. Resolve a name → entity_id via entity_lookup/entity_dictionary first.)
```

**A story cluster → its member articles → their substrate:**
```sql
SELECT a.*, f.*
FROM story_cluster_members_v8 m
JOIN articles a       ON a.id = m.article_id
LEFT JOIN story_facts_v8 f ON f.story_id = m.story_id   -- cluster-level enrichment is keyed by story_id
WHERE m.story_id = :story_id;
```

**Per-user ranked feed (articles):**
```sql
SELECT a.*, r.score_final
FROM user_article_relevance r
JOIN articles a ON a.id = r.article_id
WHERE r.user_id = :uid
ORDER BY r.score_final DESC;   -- NOT "score"; columns are score_stage1 / score_final
```

**Sentiment toward an actor** (directed-sentiment gotcha — `actor_entity_id` is the TARGET):
```sql
SELECT avg(sentiment) FROM article_stances WHERE actor_entity_id = :target_entity_id;
```

**Resolve a name to a canonical entity_id (start of any entity query):**
```sql
SELECT entity_id FROM entity_lookup WHERE name_norm = lower(trim(:surface_form));
```
