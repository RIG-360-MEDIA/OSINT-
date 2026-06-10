# Newspaper Clippings — data model, enrichment, and daily processing design

Design for taking the hybrid newspaper extractor into the main system. Borrows
the article pipeline's enrichment patterns (fixed taxonomy, "don't hedge",
`/no_think`, few-shot, translate-then-classify, LaBSE embeddings) and adapts them
to newspaper editions.

---

## 1. Database schema — `newspaper_clippings`

Three field groups: **extraction** (deterministic, from the pipeline),
**provenance/quality** (trust signals), **enrichment** (LLM/model-filled, async).

### A. Identity / source
| column | type | source |
|---|---|---|
| `id` | UUID PK | gen |
| `newspaper_id` | UUID FK → newspaper_sources | task |
| `newspaper_name` | TEXT | task |
| `newspaper_language` | TEXT (te/hi/en/…) | source |
| `edition_date` | DATE | task (today) |
| `page_number` | INT | pipeline |
| `collected_at` | TIMESTAMPTZ | NOW() |

### B. Extraction (from `extract_articles_hybrid`, deterministic)
| column | type | meaning |
|---|---|---|
| `headline` | TEXT | Vision, verbatim |
| `subheadline` | TEXT | Vision deck/strap |
| `byline` | TEXT | Vision author/dateline |
| `body_text` | TEXT | **OCR within the crop** (grounded; cannot hallucinate) |
| `vision_text` | TEXT | Vision retelling — kept as *unverified* reference only |
| `text_source` | VARCHAR(8) | `ocr` \| `vision` \| `none` |
| `section` | VARCHAR(20) | canonical (Politics/Business/…); Indic labels normalized |
| `detected_language` | VARCHAR(8) | per-article lang |
| `bbox` | JSONB / 4×FLOAT | crop box in PDF points |
| `clip_source` | VARCHAR(8) | `text` \| `body` \| `none` (localization trust) |
| `clipping_image_b64` | TEXT | the snapshot JPEG (base64) |

### C. Provenance / quality (the trust layer — the whole point of this work)
| column | type | meaning |
|---|---|---|
| `extraction_confidence` | FLOAT | mean OCR per-line confidence over the crop |
| `needs_review` | BOOL | confidence < 0.55 → garbled, route to the snapshot |
| `is_notice` | BOOL | statutory/IPO/auction notice, not news → filtered from feed |
| `is_duplicate` | BOOL | front-page teaser of an inside-page story |
| `duplicate_of` | INT | canonical page_number when duplicate |

### D. Enrichment (filled by the SINGLE substrate call — section 2)
> These are written by the one substrate extraction + its child tables, NOT by
> separate per-field LLM calls. Flat columns below are the convenience surface;
> the authoritative structured data lives in the `clipping_*` child tables
> (claims/quotes/stances/locations/events/numbers) for article-parity analytics.
| column | type | filler |
|---|---|---|
| `headline_translated` | TEXT | LLM translate (Indic→en) |
| `body_text_translated` | TEXT | LLM translate (Indic→en) |
| `topic_category` | VARCHAR(20) | LLM (coarse 15) |
| `topic_fine` | VARCHAR(20) | LLM (fine 25) |
| `entities_extracted` | JSONB | LLM NER → [{name,type}] |
| `geo_primary` | TEXT | LLM (state) |
| `geo_district` | TEXT | LLM (district) |
| `sentiment` | VARCHAR(12) | LLM tone |
| `summary_short` | TEXT | LLM 2-sentence abstractive (grounded on body_text) |
| `relevance_score` | FLOAT | relevance to watched entities + geo |
| `relevance_explanation` | TEXT | why relevant |
| `labse_embedding` | vector(768) | LaBSE model (not LLM) — semantic search/dedup |
| `enriched_at` | TIMESTAMPTZ | coverage tracking |
| `enrichment_status` | VARCHAR(16) | pending \| partial \| done |

**Dedup key:** `UNIQUE(newspaper_id, edition_date, md5(headline))`.
**Indexes:** edition_date DESC, language, topic_fine, relevance_score DESC, HNSW on labse_embedding.

---

## 2. Enrichment — route through the SUBSTRATE path, not bespoke prompts

> **Learning from the YouTube-clips design:** do NOT hand-roll separate calls for
> translate / topic / entities / geo / stance / summary. The article system does
> **ONE structured-JSON substrate call** per item that emits all of it at once,
> writes substrate-parity **child tables**, and resolves entities via the
> `entity_lookup` matview. A clipping is **"an article whose body is an OCR'd
> crop"** — so it rides the same path. This is cheaper, consistent, and makes
> clippings feed the *same* analytics as articles.

### 2.1 One call per clipping — SAME schema, NEWSPAPER-SPECIFIC prompt
Adapt, don't copy. The article `GROQ_SYS` assumes clean fetched HTML; newspaper
input is an **OCR'd print crop** and needs its own instructions. So use a
dedicated `GROQ_SYS_NEWSPAPER` system prompt that emits the **identical substrate
output object** (for analytics parity) but is tuned to print + OCR. (Mirrors the
YouTube design's "transcript-adapted Prompt G" — schema kept, instructions changed.)
```python
call_groq(system=GROQ_SYS_NEWSPAPER,             # newspaper-tuned, substrate schema
          user=f"HEADLINE: {headline}\n\nBODY (OCR):\n{body_text}",
          model=FAST_MODEL, task_type="clipping_extraction",
          json_response=True, max_tokens_override=3000)
```
**Output object (UNCHANGED from substrate — keeps child-table parity):**
`article_type, primary_subject, summaries{preview,snippet,executive},
locations[]{country(full English)/region/city/is_primary}, events[],
quotes[]{speaker,text,context,is_verbatim}, actor_stances[]{actor,stance,intensity},
claims[]{subject,predicate,object,text,claimant,type,verifiable}, numbers[],
register{rhetorical_style,primary_emotion,is_breaking}, entities_extracted[]`.
Indic clippings: same prompt **+** an `english_translation` field (≤1500 chars),
so translation happens inside the one call.

**What `GROQ_SYS_NEWSPAPER` adds over the article prompt (the bespoke part):**
```
You are reading ONE article cut from a printed newspaper page. The BODY is OCR
text — it may contain merged words, broken end-of-line hyphenation, stray column
bleed, photo-caption fragments, and jump references ("Contd. on page 5"). Read
THROUGH this OCR noise; treat artifacts as noise, not content.
RULES:
- Ground STRICTLY in the body. Do NOT invent text to bridge illegible/garbled
  spans. If a number, name, or ₹ figure is unreadable, OMIT it — never guess.
- This is the final text; there is nothing more to fetch.
- Indian print conventions: byline+dateline (e.g. "By R. Sharma, Hyderabad"),
  ₹/lakh/crore figures, regional place + party names — use official English forms
  in locations[]/entities_extracted[].
- Ignore jump-refs, page furniture, and caption-only fragments.
<then the standard substrate schema + SPO addendum>
```

### 2.2 Substrate-parity child tables (not flat columns)
Mirror the article child tables so clippings join the same analytics:
`clipping_claims` (SPO) · `clipping_quotes` · `clipping_stances` (actor/target/
stance/intensity — this **is** the directed sentiment, all entities not just the
subject) · `clipping_locations` (full country/region/city) · `clipping_events` ·
`clipping_numbers`; plus `entities_extracted JSONB` on the row.

### 2.3 Entity resolution — `entity_lookup` matview, not a resolver prompt
`entities_extracted` → `entity_lookup(name_norm)` → `entity_dictionary` via a
`clipping_entity_mentions` **matview** (exact mirror of `article_entity_mentions`;
unambiguous aliases only — "Congress"-type excluded). No ALIAS_MAP, no extra LLM
call. ALL entities resolve, so a clipping surfaces for every watched name.

### 2.4 Topic + embedding (the two genuinely separate steps)
- **Topic:** reuse `classify_topic_fine` (25 India-aware buckets, don't-hedge,
  few-shot) on `headline + english_translation[:500]`; coarse = `coarse_from_fine`.
- **Embedding:** LaBSE over `headline(_translated) + summaries.snippet` →
  `labse_embedding` (model, not LLM) for search / cross-paper clustering / near-dup.

### 2.5 Lifecycle (copy substrate, don't invent)
`substrate_status` (pending→processing→ok / extract_failed / junk),
`extraction_version=3`, atomic claim `UPDATE … RETURNING … FOR UPDATE SKIP
LOCKED`, **2-attempt retry**, robust JSON parse (strip fences, isolate outer
`{}`). One drain worker pulls pending clippings — same shape as the article drain.

### 2.6 Cost — local GPU **when it's up**, else Groq+Cerebras
The substrate call rides the unified pool, which is **local-primary ONLY while the
local slot is reachable** (`LOCAL_LLM_PRIMARY=1` → Ollama on the RTX 4090 / Trijya
via Tailscale). While it's up, enrichment is essentially free and barely touches
cloud quota. **If the 4090 is down** (Tailscale/WSL/Ollama offline), the pool fails
over to **Groq + Cerebras (cloud only)** — and then the morning newspaper
enrichment burst **does** compete with article NLP for the shared cloud budget.
→ That GPU-down case is exactly why `enrich_clipping` still runs at **bounded
concurrency on its own queue** (§6.2): a safety net, not redundant.

The **Vision page-segmentation** step is **always cloud** (Groq Scout — no vision
on local/Cerebras), one call per page; pace it regardless of GPU state.

---

## 3. Per-day firing logic

```
Beat (celery_app.py), timezone=UTC, IST = UTC+5:30:
  collect-newspapers-primary   crontab(hour=2, minute=0)   # 07:30 IST
  collect-newspapers-fallback  crontab(hour=3, minute=0)   # 08:30 IST (idempotent)
  queue = documents
```
**Two runs, both idempotent.** 07:30 IST is the primary pass. The 08:30 IST pass
is a **catch-up that only fires papers with NO clipping row for today** —
```
missing = sources WHERE is_active
          AND id NOT IN (SELECT DISTINCT newspaper_id FROM newspaper_clippings
                         WHERE edition_date = CURRENT_DATE)
```
so papers collected at 07:30 are skipped; only the ones whose edition wasn't up
yet (or failed) are retried. The on-boot >24h catch-up stays as a final net.
*(CareersWave upload times vary per paper — some may not be posted by 07:30; the
08:30 idempotent retry covers late risers. Measure real upload windows to tune.)*

**Fan out per paper.** Both runs dispatch `collect_one_newspaper.delay(paper_id)`
per source (not one loop over 51) → independent retry/timeout, parallel across the
worker; one dead Drive link can't sink the batch. Enrichment is decoupled: each
insert enqueues `enrich_clipping.delay(id)` on the `nlp` queue, so ingest never
waits on LLMs.

---

## 4. End-to-end processing — one newspaper

```
collect_one_newspaper(paper_id)
  1. RESOLVE   get_pdf_url_from_careerswave(url)  → today's PDF link
  2. DOWNLOAD  download_pdf_from_url → /tmp/<paper>.pdf
  3. EXTRACT   extract_articles_hybrid(pdf, language)   [parallel pages]
        per page (concurrent):
          render @ native res (cap 2500px) → Tesseract LSTM-best OCR (lines)
          Vision segment_page (8192 tok, truncation-salvage) → articles
          anchor each article (headline→OCR, else body-probe) → crop box
          guards (no sliver / no wrong region) → snapshot crop
          grounded body = OCR-in-box (₹ + merge repair, Vision-corroborated)
          confidence = mean OCR conf ; needs_review = conf < 0.55
  4. POSTPROCESS  normalize_section · is_notice · mark_duplicates (cross-page)
  5. FILTER    drop is_notice + is_duplicate  (statutory pages, teasers)
  6. RELEVANCE is_relevant_to_user(headline, BODY_TEXT, watched_entities, geo)
        → keep relevant (or store all, scored) ; uses the GROUNDED body
  7. WRITE     INSERT … newspaper_clippings (extraction + provenance fields)
                ON CONFLICT (source,date,md5(headline)) DO NOTHING
  8. ENQUEUE   for each new clipping → enrich_clipping.delay(id)  [nlp queue]

enrich_clipping(id)            [async, never blocks ingest]
  translate → topic_fine/coarse → entities(+resolve) → geo → sentiment
  → summary_short → LaBSE embedding → enrichment_status='done'
```

### 4.1 Downloaded-PDF retention
Today the task downloads to a tempfile and `os.unlink`s it after processing —
**not kept**. Change to **short retention**: store the edition at
`/data/newspapers/<paper>/<edition_date>.pdf` (host volume), record the path in a
`source_pdf_path` column, and a daily cron purges editions older than **14 days**.
- *Why keep at all:* re-extract/debug/audit recent editions without re-downloading
  (valuable when the IP is blocked or the Drive link has rotated).
- *Why short:* a year of 51× ~20 MB editions ≈ 300–580 GB; the per-article
  **snapshots already live in the DB**, so the full PDF is only for re-processing.
- *Scale note:* `clipping_image_b64` in Postgres is fine at current volume; at
  scale, move snapshots to object storage (R2/S3) and keep a URL — same as the
  PDF retention pattern.

---

## 5. What we borrow from the article system (and what differs)

| Aspect | Article pipeline | Newspaper clippings |
|---|---|---|
| Topic taxonomy | `classify_topic_fine` (25 buckets, don't-hedge, few-shot) | **reuse identical** |
| Translate→classify | translate, then classify on English | **same order** |
| Entities | NER → resolve to `entity_dictionary` | **same resolver** |
| Stance/sentiment | directed `article_stances` (not event-emotion) | **borrow stance.py** |
| Embedding | LaBSE 768 | **same model/column** |
| Enrichment dispatch | `nlp_processor` per-item fan-out on `nlp` queue | **same pattern** |
| Body source | scraped HTML text (clean) | **OCR-in-crop** (newsprint has no HTML) |
| Localization/snapshot | n/a (web articles) | **hybrid OCR+Vision crop** (new) |
| Notice/ad/teaser filter | n/a | **new** (`postprocess.py`) |
| Prompt style | `/no_think`, JSON-only, fixed enums, few-shot | **same conventions** |

**Net:** the *enrichment brain* is shared with articles (taxonomy, NER, stance,
embedding, dispatch) — only the **front half** (OCR localization, grounded body,
snapshot, notice/dedup) is newspaper-specific. That's the design: one enrichment
spine, two ingestion heads.

---

## 6. Integration & isolation — must NOT disturb article processing

### 6.1 Database isolation
- **Separate tables.** Clippings live in `newspaper_clippings` (+ child
  `clipping_entity_stances`). The migration is **ADD-only on clipping tables** —
  it never `ALTER`s `articles`, `article_stances`, or any substrate table. Zero
  schema impact on articles.
- **Shared, read-mostly tables.** Enrichment **reads** `entity_dictionary` /
  `user_watched_entities` to resolve names (same as articles) and may **add** new
  entities — additive, exactly what the article path already does.
- **Keep clipping entity-links OUT of article matviews.** Store
  clipping→entity links in their **own** table (or an `article_entity_mentions`
  row carrying `source_type='clipping'`), so the article entity matviews / CM
  metrics / district rollups stay article-only and are not polluted.

### 6.2 Celery isolation (the key lever)
- **Collection** runs on the **`documents`** queue — already where newspapers/
  govt-docs live. The **`collectors`** queue (RSS/HTML for articles) is untouched,
  so article *ingestion* is unaffected.
- **Enrichment** must NOT go on the **`nlp`** queue: that worker (concurrency 4)
  is what article NLP uses, and sharing it would steal article throughput. Route
  `enrich_clipping` to the **`documents`** queue (or a dedicated `clippings`
  queue) so article NLP keeps all four `nlp` slots.
- **Beat:** add the two entries to the existing `beat_schedule` dict — do **not**
  start a second Beat (double-fire footgun per CLAUDE.md).
- **Worker topology:** no new worker required if we reuse `documents`; if a
  dedicated `clippings` queue is chosen, add ONE consumer in `start.sh` (and
  remember it's an in-container process, per the deployment notes).

### 6.3 Code isolation
New code only: `collectors/newspaper_layout/*`, `tasks/newspaper_task.py`,
`tasks/clipping_enrich.py`. It **reuses article enrichment functions** (
`classify_topic_fine`, `cm/stance.py`, entity resolver, LaBSE) but writes to
clipping tables. `substrate/*` and `nlp_processor` (the article tasks) are
**byte-for-byte untouched** — the article code path does not change.

### 6.5 Consumability — usable everywhere articles are
Clippings share the **entity graph, LaBSE embedding space, topic taxonomy, and
stance model** with articles, so they can feed the same features. They live in a
**separate table** for isolation, so each consumer (Brief, Analyst RAG, relevance
feed, story clustering) must be pointed at clippings to use them. Clean path: a
**unified read view** —
```sql
CREATE VIEW content_items AS
  SELECT id,'article'  src, headline, body_text, topic_fine, edition_date, ... FROM articles
  UNION ALL
  SELECT id,'clipping' src, headline, body_text, topic_fine, edition_date, ... FROM newspaper_clippings;
```
— so any feature queries one place and gets both, with a `src` discriminator.
Same-entity links + shared embeddings mean "everything about entity X" and
cross-source story clustering span articles + clippings automatically once
consumers read the view.

### 6.4 LLM provider — same Groq+Cerebras pool as articles
- **Text enrichment** (translate / topic / entities / stance / summary) calls the
  same `groq_client.classify()` / unified pool → **Groq primary with automatic
  Cerebras failover** when Groq quota exhausts. **Identical** to articles.
- **Vision segmentation** (`segment_page`) is **Groq-only** — it uses the Scout
  vision model via `groq_manager` key-rotation; Cerebras has no vision endpoint,
  so there is nothing to fail over to (text-only models). This is the one place
  the two providers differ, by necessity.
- **Local-primary WHEN UP, else cloud:** with the 4090 reachable
  (`LOCAL_LLM_PRIMARY=1`, Ollama via Tailscale), substrate **text** enrichment is
  GPU-bound and ~free. **When the 4090 is down it fails over to Groq+Cerebras
  (cloud)** and then competes with article NLP — so keep enrichment on its own
  queue at bounded concurrency as the safeguard for that window.
- **Vision is always cloud:** `segment_page` (Scout vision) is Groq-only, once per
  page — the steady cloud load regardless of GPU state. Pace it via the extractor's
  per-page concurrency cap.
```
