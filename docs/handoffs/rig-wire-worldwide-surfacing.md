# RIG Wire — Worldwide Articles Surfacing (kickoff prompt)

> Paste this into a Claude Code session opened in the **RIG Wire** project. It hands over
> the upstream data contract and front-loads every question needed before building.
> The worldwide content-gen pipeline is OWNED ELSEWHERE — RIG Wire only **reads** its output.

---

## Role & goal

You are wiring **worldwide generated articles** into **RIG Wire**. An upstream pipeline on the
production server already synthesizes one publish-ready article per news cluster and stores it in
Postgres. **Nothing currently serves these to users — RIG Wire is the intended consumer.** Your job:
build the read path (backend endpoint + a RIG Wire view) so these articles reach users. Do **not**
modify the gen pipeline or write to its tables — this is **read-only consumption**.

## Where the data lives (production)

- **Server (Hetzner):** `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`
- **Postgres:** container `rig-postgres`, db `rig` → `docker exec rig-postgres psql -U rig -d rig -c "<sql>"`
- **Read-only role for app access:** `analytics_user` (RW only on the `analytics` schema; read on `public.*`). Use this, never the superuser, for the serving connection.
- Tables live in the **`analytics`** schema.

## Data contract — what to read

**Generated articles:** `analytics.story_generated_v8`
| column | meaning |
|---|---|
| `story_id` (uuid) | PK; joins to `story_clusters_v8.story_id` |
| `headline`, `deck`, `body` (text) | the article (body is full prose, markdown-ish) |
| `topic` (text), `tags` (text[]) | classification |
| `strategy` (text) | **`source-grounded`** = the good full articles (250–1200w, verified). Others: `Hybrid A/B` (older ~250w ledger), `stub` (legacy). |
| `status` (text) | publish gate — filter `status LIKE 'PUBLISHABLE%'` |
| `word_count` (int) | length |
| `claim_provenance` (jsonb) | `{claim -> [source ids]}` — use for inline citations / source cards |
| `verify` (jsonb) | `{hard_faith, contra, n_high, verdict, verifier}` — faithfulness audit (e.g. show a trust badge) |
| `tier` (int), `guard_c` (jsonb), `fact_version`, `run_id`, `member_hash` | internal |
| `updated_at` (timestamptz) | last regen time |

**Cluster metadata (join for title/recency/provenance):** `analytics.story_clusters_v8` on `story_id`
Useful cols: `representative_title`, `representative_article_id`, `last_seen_at` / `first_seen_at` (recency),
`independent_source_count`, `source_count`, `article_count`, `importance_score`, `topic`, `event_type`,
`primary_entities`, `languages`, `subject_country`, `subject_region`, `subject_locations`,
`representative_quote`, `sentiment`, `stance_distribution`.

**Canonical "ready to show" query (start here):**
```sql
SELECT g.story_id, g.headline, g.deck, g.body, g.topic, g.tags, g.word_count,
       g.claim_provenance, g.verify,
       c.last_seen_at, c.independent_source_count, c.importance_score,
       c.primary_entities, c.languages, c.subject_country, c.subject_region
FROM   analytics.story_generated_v8 g
JOIN   analytics.story_clusters_v8 c USING (story_id)
WHERE  g.status LIKE 'PUBLISHABLE%'
  AND  g.strategy = 'source-grounded'          -- highest quality; drop this line to include Hybrid
ORDER  BY c.last_seen_at DESC NULLS LAST
LIMIT  50 OFFSET :offset;
```

**Volumes (2026-06-20, growing):** ~580 source-grounded PUBLISHABLE, ~410 older Hybrid. A backlog
drain is actively generating more (writer = a local model; cloud verifier). Expect the count to rise.

**No images:** articles have no media. If RIG Wire needs thumbnails, derive from the representative
source article (`representative_article_id` → `public.articles`) or use topic/entity iconography.

## ANSWER THESE before building (the things I need from you)

**RIG Wire codebase & access**
1. Where is the RIG Wire repo (path / git remote)? Is it a separate repo from `rig-surveillance`?
2. Stack: frontend framework + backend framework/language? (Next.js? Vite+React? FastAPI? Node?)
3. How do I run it locally (install / dev-server / build commands) and where does it deploy (domain, Caddy route, container)?

**Data access pattern**
4. Does RIG Wire talk to its own backend/API, or read a DB directly? If DB — can it reach the Hetzner Postgres `analytics` schema, and with which role/DSN? If not, where should the new read endpoint live?
5. Is there an existing "wire/feed" data layer or article model I should extend, rather than inventing a new one?

**Product placement & behavior**
6. Where exactly in RIG Wire should worldwide articles appear — a dedicated page/route, a feed section, a "Wire" stream? What's the URL/nav entry?
7. Sort order: recency (`last_seen_at`) or `importance_score`? Default page size / pagination style?
8. Filters needed: by topic, language, region/country, entity? RIG Wire's audience — global or India/Telangana-focused like the rest of the system?
9. Detail view: full `body` + cited source cards (from `claim_provenance`)? Show the faithfulness badge from `verify`?
10. Only `source-grounded`, or include the older `Hybrid` articles for volume?

**Auth / scope**
11. Is RIG Wire public or per-user authed? Any per-user filtering (by entity/geo/preferences), or one global feed for everyone?
12. Any design system / component library / styling conventions I must follow?

## Guardrails
- **Read-only** on `analytics.*`; never write to `story_generated_v8` / `story_clusters_v8`.
- Do **not** run LLM/yt-dlp probes against the local GPU boxes (`100.96.25.59`, `100.105.228.103`) — one is an in-use workstation.
- The gen pipeline is owned by another workstream; coordinate, don't modify it.

## Deliverable
A read-only `/worldwide` (or RIG-Wire-native) endpoint backed by the query above + a RIG Wire view
that lists and renders the articles with citations. Confirm answers to the questions above first,
then propose the implementation plan before coding.
