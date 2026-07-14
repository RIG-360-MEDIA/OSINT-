# Neon setup — step by step (Democracy News Live)

Two phases. **Phase 1 (Neon-only) can be done today** — it stands up the writable
`rigwire.*` DB for the CMS. **Phase 2** adds the replicated read tables from the box.

---

## PHASE 1 — Create Neon + the writable CMS DB (≈15 min, all clicks/SQL)

### 1. Create the project
1. Go to **console.neon.tech** → sign up (GitHub/Google). Free tier is fine.
2. **Create project**:
   - Name: `dnl`
   - Postgres version: **16**
   - Region: **AWS Europe (Frankfurt) — `eu-central-1`** (nearest to your Hetzner box + Vercel `fra1`)
   - Database name: `dnl`
3. Neon shows a **connection string**. Note two host forms:
   - Pooled (app):  `ep-xxxx-pooler.eu-central-1.aws.neon.tech`
   - Direct (DDL/migrations):  `ep-xxxx.eu-central-1.aws.neon.tech`

### 2. Create the CMS schema + tables (Neon console → **SQL Editor**)
```sql
CREATE SCHEMA IF NOT EXISTS rigwire;
-- match your existing rigwire.* DDL exactly. Example shape:
CREATE TABLE rigwire.editorial_overrides ( story_id text PRIMARY KEY, payload jsonb, updated_at timestamptz DEFAULT now() );
CREATE TABLE rigwire.editorial_audit     ( id bigserial PRIMARY KEY, actor text, action text, at timestamptz DEFAULT now(), detail jsonb );
CREATE TABLE rigwire.manual_stories      ( id text PRIMARY KEY, body jsonb, created_at timestamptz DEFAULT now() );
CREATE TABLE rigwire.ranking_weights     ( key text PRIMARY KEY, weight double precision );
CREATE TABLE rigwire.image_checks        ( id text PRIMARY KEY, result jsonb, checked_at timestamptz DEFAULT now() );
```
> Get the real DDL from the box: `docker exec rig-postgres pg_dump -U rig -d rig --schema=rigwire --schema-only` and paste it here instead of the example.

### 3. Create least-priv roles (SQL Editor)
```sql
CREATE ROLE reader_ro LOGIN PASSWORD 'STRONG_PW_1';
CREATE ROLE cms_rw    LOGIN PASSWORD 'STRONG_PW_2';
GRANT USAGE ON SCHEMA rigwire TO reader_ro, cms_rw;
GRANT SELECT ON ALL TABLES IN SCHEMA rigwire TO reader_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rigwire TO cms_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA rigwire GRANT SELECT ON TABLES TO reader_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA rigwire GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO cms_rw;
```

### 4. Put the connection strings in Vercel (Project → Settings → Environment Variables)
```
DATABASE_URL          = postgresql://reader_ro:STRONG_PW_1@ep-xxxx-pooler.eu-central-1.aws.neon.tech/dnl?sslmode=require&pgbouncer=true&connect_timeout=10
RIGWIRE_DATABASE_URL  = postgresql://cms_rw:STRONG_PW_2@ep-xxxx-pooler.eu-central-1.aws.neon.tech/dnl?sslmode=require&pgbouncer=true&connect_timeout=10
MIGRATE_DATABASE_URL  = postgresql://cms_rw:STRONG_PW_2@ep-xxxx.eu-central-1.aws.neon.tech/dnl?sslmode=require     # non-pooler, for migrations only
```
→ **CMS writes work now.** (Prisma: keep `?pgbouncer=true`. Or use `@neondatabase/serverless` for fastest cold-starts.)

---

## PHASE 2 — Replicate the read tables (box → Neon)

### 5. On the box (rig-postgres) — one-time
```sql
-- as superuser inside the container: docker exec -it rig-postgres psql -U rig -d rig
ALTER SYSTEM SET wal_level = 'logical';           -- needs ONE restart of rig-postgres
CREATE ROLE dnl_repl WITH REPLICATION LOGIN PASSWORD 'REPL_PW';
GRANT USAGE ON SCHEMA analytics, public TO dnl_repl;
GRANT SELECT ON analytics.story_clusters_v8, analytics.story_generated_v8,
  analytics.story_facts_v8, analytics.story_cluster_members_v8, public.articles TO dnl_repl;
CREATE PUBLICATION dnl_pub FOR TABLE
  analytics.story_clusters_v8, analytics.story_generated_v8,
  analytics.story_facts_v8, analytics.story_cluster_members_v8,
  TABLE public.articles (id,title,url,lead_text_translated,published_at,geo_primary,topic_category,source_id)
        WHERE (collected_at > now() - interval '120 days');
```
Then **restart** rig-postgres (schedule it; watchdog + pipeline auto-resume) and confirm `SHOW wal_level; -- logical`.
Firewall: allow TCP 5432 **only from Neon's egress IPs** (Neon → Settings shows them), TLS required.

### 6. On Neon — create matching empty tables + subscribe
- Create the 5 read tables with the **same DDL** as the box (use the `pg_dump --schema-only` for `analytics` + the article columns above). No pgvector needed (embeddings are excluded).
```sql
CREATE SUBSCRIPTION dnl_sub
  CONNECTION 'host=BOX_PUBLIC_IP port=5432 dbname=rig user=dnl_repl password=REPL_PW sslmode=require'
  PUBLICATION dnl_pub;         -- does the initial copy, then streams live
```
- Verify: `SELECT * FROM pg_stat_subscription;` and row counts climbing.
- Grant reads: `GRANT SELECT ON <the 5 tables> TO reader_ro, cms_rw;`

### 7. Flip Vercel reads to Neon
`DATABASE_URL` already points at Neon — once `dnl_sub` shows `streaming`, the reader is fully served from Neon and **never touches the box**.

---

## Notes
- **Do Phase 1 first**, ship the CMS. Add Phase 2 when you're ready — until then, reads can stay on your current tunnel/dev path or a short-TTL cached API.
- The one seam: if the box's Worldwide generator reads `rigwire.editorial_overrides`, point it at Neon (small read) — see `dnl-vercel-data-architecture.md`.
