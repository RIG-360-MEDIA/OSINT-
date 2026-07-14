# Democracy News Live — Vercel ⇄ data architecture

**Decision: Neon (serverless Postgres) as an isolated read plane, fed by logical
replication from the Hetzner box. `rigwire.*` created natively on Neon (writable).
Vercel talks ONLY to Neon's transaction pooler.**

## Why this, defended against the alternatives
The binding constraint is **#1 (isolation)**. Only a design where the public reader
reads a *separate database* satisfies it:

| Option | Reader load lands on | Verdict |
|---|---|---|
| (a) public pgBouncer on box | **primary OSINT DB** | ❌ a traffic spike can starve clustering/watchdog |
| (d) read-through API on box | **primary OSINT DB** (via API) | ❌ same — still the pipeline's DB |
| (e) Cloudflare Tunnel / Tailscale | **primary OSINT DB** | ❌ same; also awkward from serverless |
| (c) Vercel Postgres | Neon (it IS Neon under the hood) | ✅ = (b), less control |
| **(b) Neon replica** | **Neon** | ✅ physical read-plane separation |

Neon uniquely gives: serverless **transaction pooler** (pgBouncer-equivalent, built for
Vercel), scale-to-zero, managed TLS/backups, **and inbound logical replication from a
self-hosted Postgres** — the exact shape needed. Public traffic hits Neon; the box only
streams one async WAL feed (negligible vs clustering).

## The shape
- **Box (publisher, PG16) → Neon (subscriber)** for read tables: `story_clusters_v8`,
  `story_generated_v8`, `story_facts_v8`, `story_cluster_members_v8`, `auth.users`, and
  `public.articles` **row-filtered** (see below). Read-only on Neon.
- **`rigwire.*`** (`editorial_overrides, editorial_audit, manual_stories, ranking_weights,
  image_checks`) created **natively on Neon, writable** — Neon is their source of truth.
  Low volume → no scale concern, no read-replica-write conflict.
- **Integration seam (the one thing to wire):** if the box's Worldwide generator reads
  `rigwire.editorial_overrides`, point it at Neon (small read) OR reverse-replicate
  `rigwire.*` Neon→box. Editorial overrides are low-frequency, so a direct box→Neon read is fine.

## Keep Neon lean/fast/cheap
`public.articles` is large. Use a PG16 **publication row filter + column list** to ship only
the reader-relevant slice, e.g.:
```sql
CREATE PUBLICATION dnl_pub
  FOR TABLE analytics.story_clusters_v8,
            analytics.story_generated_v8,
            analytics.story_facts_v8,
            analytics.story_cluster_members_v8,
            auth.users,
  TABLE public.articles (id, title, url, lead_text_translated, published_at, geo_primary,
                         topic_category, source_id)
        WHERE (collected_at > now() - interval '120 days');
```

## Provisioning
**On rig-postgres (box):**
1. `wal_level = logical` in postgresql.conf → **one restart** (schedule it; watchdog + pipeline auto-resume). Verify `SHOW wal_level;`.
2. `CREATE ROLE dnl_repl WITH REPLICATION LOGIN PASSWORD '…';` + the `CREATE PUBLICATION` above.
3. Firewall: allow 5432 **only from Neon's egress IPs** (allowlist), `sslmode=require`. Not open to the internet.

**On Neon (project `dnl`, region `eu-central-1` Frankfurt):**
4. Create matching DDL for the replicated tables, then
   `CREATE SUBSCRIPTION dnl_sub CONNECTION 'host=BOX … sslmode=require' PUBLICATION dnl_pub;` (initial copy + stream).
5. Create `rigwire` schema + its 5 tables natively (writable).
6. Two least-priv roles:
   - `reader_ro` → `GRANT SELECT` on the replicated tables + `rigwire`.
   - `cms_rw` → `SELECT` on replicated; `SELECT,INSERT,UPDATE,DELETE` on `rigwire.*` only.

## Connection strings (Vercel env)
Reads — `DATABASE_URL`:
```
postgresql://reader_ro:PWD@ep-xxxx-pooler.eu-central-1.aws.neon.tech/dnl?sslmode=require&pgbouncer=true&connect_timeout=10
```
rigwire writes — `RIGWIRE_DATABASE_URL`:
```
postgresql://cms_rw:PWD@ep-xxxx-pooler.eu-central-1.aws.neon.tech/dnl?sslmode=require&pgbouncer=true&connect_timeout=10
```
Migrations only (session mode, **non**-pooler host):
```
postgresql://cms_rw:PWD@ep-xxxx.eu-central-1.aws.neon.tech/dnl?sslmode=require
```
- App traffic → **`-pooler`** host (transaction mode). DDL/migrations → non-pooler (session mode).
- Prisma: keep `?pgbouncer=true`. For lowest cold-start on Vercel, consider the
  `@neondatabase/serverless` HTTP/WebSocket driver. Keep per-invocation pool size = 1.

## Latency
Neon `eu-central-1` (Frankfurt) + Vercel functions region `fra1`, both co-located with the
Hetzner Nuremberg box → Vercel↔Neon single-digit ms. Box→Neon replication is async (lag
~sub-second–seconds; fine for a reader).

## Tradeoffs (honest)
- **Eventual consistency:** Neon reads lag the box slightly — fine for news; `rigwire`
  writes are native/strong on Neon so read-after-write there is correct.
- **One-time restart** for `wal_level=logical`.
- **Two data homes** + the one generator-reads-overrides seam.
- Cost scales with Neon storage/compute — the row filter controls it.

## Phase-0 (ship TODAY, before replication is live)
Create `rigwire.*` on Neon now and cut CMS **writes** over immediately. For **reads**,
temporarily front the box with a thin **cached** read-through API (short TTL, so the box
isn't hit per request), then flip reads to the Neon replica once `dnl_sub` is streaming.
De-risks the launch without ever exposing the box's DB.
