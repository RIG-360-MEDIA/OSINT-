# New-Product Chat — Kickoff Prompt

> Copy this entire file into the new chat as your first message. Replace `OCSjtTucdWQ83UOKHiMX6wsifVWxFH` with the actual password before pasting.

---

## What you're building

You are working on **a separate product** that uses the rig-surveillance intelligence data (~119,000 articles, ~240,000 claims with SPO triples, ~260,000 locations, ~210,000 events, ~190,000 numerical facts, ~160,000 stances, ~16,000 canonical entities, ~800 sources across 13+ countries). The data is the foundation. The product is whatever you and the user build on top.

You have **READ-ONLY** access to the source-of-truth tables. You have **FULL READ-WRITE** access to your own sandbox schema (`analytics`) where you can build tables, views, functions, materialized views, indexes — whatever shape your product needs.

---

## What you CAN do

- `SELECT` from any table in the `public` schema (articles, article_claims, article_quotes, article_locations, article_events, article_numbers, article_stances, article_links, article_media, article_tweets, article_districts, entity_dictionary, sources)
- `EXECUTE` any function in `public` (e.g. `compute_location_scope`, `compute_effective_event_date`)
- `CREATE TABLE`, `CREATE VIEW`, `CREATE MATERIALIZED VIEW`, `CREATE FUNCTION`, `CREATE INDEX` inside the `analytics` schema (your own sandbox)
- `INSERT / UPDATE / DELETE` inside `analytics.*` — your tables, your rules
- `REFRESH MATERIALIZED VIEW analytics.my_view` etc.
- Run any read query you want, no matter how complex (window functions, recursive CTEs, full-text search, vector ops via pgvector)

## What you CANNOT do (the DB enforces this — not just trust)

- `INSERT / UPDATE / DELETE / TRUNCATE` on `public.*` — you will get `permission denied for table X`
- `ALTER / DROP` on `public.*` — you will get `must be owner of table X`
- `CREATE TABLE public.something` — you will get `permission denied for schema public`
- Run migrations against `public`
- Create new roles
- Touch `pg_*` system catalogs in dangerous ways

If you need a new column added to a `public` table, or a new index on a `public` table, or any structural change — **ask the user to coordinate with the rig-surveillance maintainer to run a migration**. Don't try to work around it.

---

## Connection details

### Recommended: SSH tunnel + psycopg / direct psql

```bash
# From your laptop, set up a tunnel
ssh -i ~/.ssh/rig_hetzner -L 5433:rig-postgres:5432 root@178.105.63.154 -N

# In another terminal, connect to localhost:5433
psql "postgresql://analytics_user:OCSjtTucdWQ83UOKHiMX6wsifVWxFH@localhost:5433/rig"
```

Or as a Python connection string:
```python
import os, psycopg
DSN = f"postgresql://analytics_user:{os.environ['ANALYTICS_DB_PASSWORD']}@localhost:5433/rig"
conn = psycopg.connect(DSN)
```

### Direct (if Hetzner port 5433 is firewalled-open from your IP)

```
postgresql://analytics_user:OCSjtTucdWQ83UOKHiMX6wsifVWxFH@178.105.63.154:5433/rig
```

If you get connection refused, fall back to the SSH-tunnel method above.

---

## The data model — what's in there

### Master tables

- **`articles`** (~119K rows) — every article we've ingested. Key fields:
  - `id` UUID, `url`, `title`, `full_text_scraped`, `language_iso`
  - `published_at`, `collected_at`
  - `source_id` → `sources.id`
  - **`source_country`** CHAR(2) ISO alpha-2 (auto-populated via trigger from migration 075)
  - `extraction_version` (0/null = legacy, 3 = current)
  - `substrate_status` (`pending` | `processing` | `ok` | `extract_failed` | `fetch_failed` | `junk`)
  - `summary_preview` (~50 chars), `summary_snippet` (~200 chars), `summary_executive` (~700 chars)
  - `primary_subject` — one-sentence what-the-article-is-about
  - `article_type` (news / opinion / analysis / live_blog / etc.)
  - `register_style`, `register_emotion` — tone classifiers
  - `byline`, `author_name`
  - `labse_embedding` vector(768) — full-body LaBSE embedding (93% populated)
  - `topic_category` (sport / politics / business / tech / etc.)
  - `geo_primary` — primary location string
  - `is_duplicate`, `duplicate_of`

- **`sources`** (~793 rows, 550 active) — RSS/HTML/API sources we scrape from. Key fields:
  - `id`, `name`, `domain`, `rss_url`
  - `source_type` (rss / scrape / api), `source_tier` (1=high-trust / 2=standard / 3=experimental)
  - `language`, `geo_states` text[], **`country` CHAR(2)** (migration 075)
  - `is_active`, `health_score`, `consecutive_failures`

### Per-article child tables (all FK to `articles.id`)

| Table | Rows | What's in it |
|---|---|---|
| `article_claims` | ~240K | SPO triples: `subject_text`, `predicate`, `object_text`, `claim_text`, `claim_type` (asserted / hypothetical / etc.), `claimant` (article or speaker name), `confidence`, `embedding` vector(768). Post-D1 fix (2026-05-27): 99% have all 3 SPO fields. |
| `article_quotes` | ~96K | Quoted speech: `text` (raw), `quote_text_en` (translated), `speaker` (or speaker_name), `speaker_role`, `context`, `is_direct`, `extracted_at` |
| `article_locations` | ~260K | Geographic mentions: `location_text`, `country`, `region`, `city`, **`location_scope`** (city/state/country/continent — migration 074), `is_primary`, `mention_count` |
| `article_events` | ~210K | Discrete events: `event_date` (LLM raw), **`effective_event_date`** (smart-fixed — migration 072), `event_description`, `event_type`, `actors` text[], `is_future` |
| `article_numbers` | ~190K | Numeric facts: `value`, `unit` (normalized — migration 073), `context` |
| `article_stances` | ~160K | Position-taking: `actor`, `target`, `stance` (supportive/critical/neutral/sympathetic/etc.), `intensity` |
| `article_links` | ~5M | Outbound links from article bodies |
| `article_media` | ~1.5M | Embedded images/videos with captions |
| `article_tweets` | ~2K | Embedded tweet refs |
| `article_districts` | ~28K | Indian district mapping |
| `article_contradictions` | 0 | Reserved — narrative-pipeline output, currently unwritten |

### Entity vocabulary

- **`entity_dictionary`** (~15,755 rows) — canonical entities. Fields:
  - `id`, `canonical_name`, `entity_type` (person / organization / constituency / location / role)
  - `aliases` text[] (98% populated)
  - `state`, `party`, `metadata` JSONB
  - Child tables reference this via `*_entity_id` FK columns

### Narrative tables (scaffolded but not yet populated)

- `narrative_clusters`, `narrative_cluster_members`, `narrative_drafts` — for grouping related articles into narratives. Created by migration 070 but nothing writes to them yet (Stage 0-6 narrative pipeline is P2 todo for the rig team).

---

## Data quality stats (last 6h sample, 2026-05-28)

For articles `substrate_status='ok' AND extraction_version=3`:

| Field | Fill rate |
|---|---|
| summary_preview / snippet / executive | 100% |
| primary_subject | 100% |
| article_type | 100% |
| register_style / register_emotion | 99.99% |
| author_name | 100% |
| Claims with all 3 SPO fields | **99%** (was 14% pre-D1) |
| Locations populated | 99% (avg 2.57/article) |
| Events populated | 96% |
| Numbers populated | 74% |
| Quotes populated | 59% (lower because briefs/listicles have none) |
| labse_embedding | 93% |

**Failure modes to filter out:**
- `substrate_status IN ('fetch_failed', 'junk', 'extract_failed')` — exclude these for any user-facing product
- `is_duplicate = true` — deduped against earlier articles
- `language_iso` for content language; ~30% non-English (hi, te, kn, or, ta, ml, etc.)
- `extraction_version IS NULL OR extraction_version < 3` — legacy articles without v3 schema

---

## Useful starter queries

```sql
-- Latest 20 news articles with full substrate, in English
SELECT id, title, summary_snippet, source_country, published_at
  FROM articles
 WHERE substrate_status = 'ok'
   AND extraction_version = 3
   AND article_type = 'news'
   AND language_iso = 'en'
   AND NOT is_duplicate
 ORDER BY collected_at DESC
 LIMIT 20;

-- Claims about a specific entity (e.g. find Modi-related claims)
SELECT a.title, c.subject_text, c.predicate, c.object_text, c.claimant
  FROM article_claims c
  JOIN articles a ON a.id = c.article_id
 WHERE c.subject_text ILIKE '%Modi%'
   AND a.substrate_status = 'ok'
 ORDER BY a.collected_at DESC
 LIMIT 50;

-- Country-grouped article volume per day
SELECT source_country,
       date_trunc('day', collected_at) AS day,
       COUNT(*) AS n_articles
  FROM articles
 WHERE collected_at > NOW() - INTERVAL '7 days'
 GROUP BY source_country, day
 ORDER BY day DESC, n_articles DESC;

-- All cities mentioned in last 24h
SELECT city, country, COUNT(*) AS mentions
  FROM article_locations al
  JOIN articles a ON a.id = al.article_id
 WHERE al.location_scope = 'city'
   AND a.collected_at > NOW() - INTERVAL '24 hours'
   AND al.city IS NOT NULL
 GROUP BY city, country
 ORDER BY mentions DESC
 LIMIT 30;

-- Most-quoted speakers
SELECT speaker_name, COUNT(*) AS quote_count
  FROM article_quotes
 WHERE speaker_name IS NOT NULL
 GROUP BY 1
 ORDER BY 2 DESC
 LIMIT 30;

-- Vector similarity (find articles similar to a given one)
SELECT a2.title, 1 - (a1.labse_embedding <=> a2.labse_embedding) AS similarity
  FROM articles a1, articles a2
 WHERE a1.id = '<some-article-uuid>'
   AND a2.id != a1.id
   AND a2.labse_embedding IS NOT NULL
 ORDER BY a1.labse_embedding <=> a2.labse_embedding
 LIMIT 10;
```

---

## How the data gets in (context, not actionable)

You DON'T need to know the scraper pipeline to build your product, but here's enough to understand the data you're querying:

- **Ingestion:** ~793 sources (550 active). RSS via FreshRSS, fallback to direct HTTP, fallback to HTML scraping. Tier 4 (Playwright) currently disabled.
- **Extraction:** Each article runs through `Prompt G + D1 SPO addendum` via a unified LLM pool (Ollama on a local 4090 + 21 Groq keys + 27 Cerebras keys). Output is structured JSON populating the 6 child tables.
- **Quality:** Post-D1 fix (2026-05-27), the substrate produces 99% complete SPO triples and 100% summary coverage on processed articles. 0.28% failure rate.
- **Sources are country-coded** via migration 075. ISO 3166 alpha-2 in `articles.source_country`.

If your product needs MORE granular extraction (e.g. a new field), coordinate with the rig team to update the substrate prompt + add a migration — you can't extend `public.*` yourself.

---

## Recommended workflow

### Building your product

1. Start by `\dt+ public.*` (see all tables) and reading column comments via `\d+ public.<table>`
2. Prototype queries in `psql` interactive mode
3. When a query is useful, persist it as a VIEW in YOUR schema:
   ```sql
   CREATE VIEW analytics.recent_news_en AS
   SELECT id, title, summary_snippet, source_country, published_at
     FROM articles
    WHERE substrate_status = 'ok' AND extraction_version = 3
      AND article_type = 'news' AND language_iso = 'en'
      AND NOT is_duplicate;
   ```
4. For expensive aggregations, use MATERIALIZED VIEW + `REFRESH MATERIALIZED VIEW analytics.X`
5. Your product app/UI queries `analytics.*` (your views) — never `public.*` directly. That way schema changes on our side don't break you immediately (just refresh your view definitions).

### What to track in your repo

Keep a `migrations/` folder for YOUR schema. Every CREATE TABLE / VIEW / FUNCTION you make goes there. So your sandbox state is reproducible. We do the same for `public.*`.

---

## Source-rig context files you might want

If you want to understand HOW the data is produced or want context about the upstream system, these are worth a read:

- `docs/onboarding/01-architecture.md` — overall system map (briefly)
- `docs/onboarding/02-substrate-pipeline.md` — what each child table represents
- `docs/onboarding/04-scrapers.md` — what 4-tier ingestion looks like (so you know data quality patterns)
- `docs/DATA_QUALITY_AUDIT_2026-05-28.md` — per-field health
- `docs/PHASE1_20_COUNTRIES.md` — upcoming source expansion (means more data coming)

Skip the LLM infrastructure docs, runbooks, sprint plans — you don't operate the upstream system.

---

## Quality & safety rules

1. **Never assume our schema is stable.** Migrations happen. Use VIEWS in your own schema to insulate yourself.
2. **Don't query `articles` without filters.** 119K rows. Always include `WHERE substrate_status='ok'` or `WHERE collected_at > NOW() - INTERVAL '7 days'` or similar. Saves load on the prod DB.
3. **Use indexes.** `articles.collected_at` is indexed. `article_claims.article_id`, `article_quotes.article_id`, etc. all indexed. Vector indexes exist on `articles.labse_embedding` and `article_claims.embedding`.
4. **Materialize expensive aggregations.** If a query takes >1 second to run, wrap it in a MATERIALIZED VIEW and refresh nightly.
5. **Tell the rig team if you find data-quality issues.** You're a downstream consumer — your usage will surface gaps we missed.

---

## First action when you start

1. Connect via psql using the connection string above
2. Verify access:
   ```sql
   SELECT current_user, current_database();
   -- expect: analytics_user, rig
   
   SELECT COUNT(*) FROM articles WHERE substrate_status = 'ok';
   -- expect: ~92,000 (the count of fully-processed articles)
   
   SELECT current_schema(), schema_name FROM information_schema.schemata
    WHERE schema_owner = 'analytics_user';
   -- expect: 'analytics' shows up
   
   CREATE TABLE analytics.test_my_access (id int);
   DROP TABLE analytics.test_my_access;
   -- both should succeed (you own analytics)
   
   -- This SHOULD fail (verify the safety net):
   INSERT INTO articles (id, url) VALUES ('00000000-0000-0000-0000-000000000000', 'http://test');
   -- expect: ERROR: permission denied for table articles
   ```
3. Once verified, tell the user what your product is and start designing your `analytics` schema.

---

## Don't bother the user about

- Scrapers / drains / LLM pool — that's the rig team's domain
- Migrations against `public` — coordinate via the rig team
- Cerebras / Groq / Ollama configuration — irrelevant to you
- Frontend brief page redesign — different product

---

## Quick reference

| Thing | Value |
|---|---|
| Username | `analytics_user` |
| Password | `OCSjtTucdWQ83UOKHiMX6wsifVWxFH` (replace before pasting to chat) |
| Host | `178.105.63.154` (Hetzner public IP, port 5433) — OR via SSH tunnel to `localhost:5433` |
| Database | `rig` |
| Your sandbox schema | `analytics` |
| Read-only source schema | `public` |
| PostgreSQL version | 16 + pgvector extension |
| Vector dimension (LaBSE) | 768 |

Good luck building. The data is rich. Don't try to operate the upstream system — just build great things on top of it.
