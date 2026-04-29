# Clips — Data Quality Report

**Date:** 2026-04-25
**Scope:** Are the clips the scraper is producing actually *useful to the user*?
**Method:** Inspected the production Supabase DB (project `nwqstdfoqfygyifrjtcw`), 204 rows in `video_clips` (window 2026-04-16 → 2026-04-23, ~7 days).
**Verdict:** ❌ **Low signal-to-noise.** Roughly **1 in 3 clips is filler or off-topic**, and a critical schema mismatch means the `/clips` page in this repo cannot render production data at all.

---

## 0. Critical finding — schema mismatch (blocks the whole feature)

The `/clips` page (`backend/routers/clips_router.py`) reads from a table named `youtube_clips` defined in [scripts/migrations/003_youtube_clips.sql](../../scripts/migrations/003_youtube_clips.sql).

**That table does not exist in the production database.** What exists is a different table called `video_clips` with a completely different schema:

| `youtube_clips` (what the router queries) | `video_clips` (what's actually populated) |
|---|---|
| `video_id`, `channel_id`, `channel_name` | `article_id`, `keyword` |
| `embed_url`, `clip_start_seconds`, `clip_end_seconds` | `clip_url`, `start_time`, `end_time` |
| `transcript_translated`, `matched_entity` | `ai_summary` (no entity field) |
| `relevance_score`, `processed`, `labse_embedding` | none of these |

→ Until the migration is run **or** the router is pointed at `video_clips`, the user sees an empty Clip Room regardless of how many clips the collector creates. This is a **release-blocking** defect that supersedes everything else in this report.

---

## 1. Aggregate quality numbers (`video_clips`, 204 rows)

| Metric | Value | Interpretation |
|---|---|---|
| Total clips | 204 | ~7 days |
| Distinct source articles | 200 | almost no clustering — barely any topic gets >1 clip |
| Distinct keywords | 45 | reasonable coverage |
| Avg clip duration | 26.8 s | sensible length |
| Bad time window (`end ≤ start`) | 0 | clean |
| Empty transcript | 7 (3%) | acceptable |
| Transcript < 25 chars (effectively empty) | 11 (5%) | speaker says "Thank you", filler, or just punctuation |
| **Filler AI summary** ("too short to summarise", "Opening clip…", "Clip around X at 0:00") | **~30 %** | **the user is being shown a thumbnail with no real synopsis** |
| **Keyword not present in transcript OR summary** | **63 (31 %)** | match precision ≈ 69 %; users will see clips that don't actually mention the topic they're tracking |

---

## 2. The keyword-list is polluted — "`clip`" is itself a tracked keyword

Top-15 keywords by clip count, with % filler summaries:

| Keyword | Clips | % filler | Smell test |
|---|---|---|---|
| **`clip`** | 17 | **65 %** | This is a literal English word, not an entity. Whatever seeded the keyword list let this through — it matches every video about anything |
| `Odisha police encounter` | 10 | 60 % | most are off-topic |
| `Mahanadi river Odisha` | 7 | 57 % | |
| `Odisha Legislative Assembly` | 8 | 50 % | |
| `heat wave Odisha` | 6 | 50 % | |
| `Smart City Bhubaneswar` | 6 | 50 % | |
| `Tata Steel Kalinganagar` | 10 | 40 % | |
| `Lok Sabha women seats` | 12 | 33 % | |
| `Lok Sabha Odisha` | 8 | 25 % | |
| `delimitation women reservation` | 5 | 20 % | |
| `OBC women reservation` | 6 | 0 % | clean |
| `Sonia Gandhi reservation` | 10 | 10 % | clean |
| `Congress women reservation` | 12 | 8 % | clean |

**Pattern:** *broad geographic keywords* ("Odisha X") and *generic words* ("clip") drag the ratio down. *Named-entity keywords* ("Sonia Gandhi", "Congress …") are the cleanest.

---

## 3. Concrete examples of useless clips currently shown to the user

These are real rows pulled from the DB:

| keyword | start | dur | transcript / summary |
|---|---|---|---|
| `clip` | 0 | 30 s | transcript is Gujarati/Odia about a heat-wave; summary admits *"the transcript segment mentions 'clip' only incidentally, if at all"* |
| `women political representation` | 1 | 33 s | transcript: **"I don't know I'm I'm"** — pure filler |
| `women politicians` | 0 | 30 s | transcript: **"Thank you very much."** — speaker thanking the audience |
| `PM Modi women bill` | 0 | 28 s | transcript: **"। । । । । । ।"** — only Devanagari full-stops, no actual words |
| `crime Odisha` | 0 | 29 s | summary is in Gujarati script *(non-English transcript surfaced raw to the English UI)* |
| `Odisha government scheme` | 1 | 28 s | summary: **"Opening clip from this video (1s - 29s)."** — i.e. no analysis at all |
| `INDIA alliance` | 3 | 26 s | summary mentions *"changed the face of the syndicate"* — Whisper/translation hallucination from likely "ASI" or similar |

Every one of these would waste a user's attention. None of them carry actionable political-intelligence signal.

---

## 4. Root causes (where to fix it, not just what's broken)

The `/clips` UI implies a YouTube-channel × political-entity pipeline (per [backend/collectors/youtube_collector.py](../../backend/collectors/youtube_collector.py) — that file *is* high-quality: per-entity Groq prompts with strong Telangana-politics disambiguation, hallucination rejection, embedding generation). But the data populating production today is from a **different, lower-quality pipeline** writing to `video_clips` keyed by free-text `keyword`, not by entity.

That older pipeline has four defects:

1. **No entity validation.** The keyword `"clip"` should never have made it past a sanity check. There is no equivalent of the `entity_lookup` rejection that `youtube_collector.analyze_transcript_with_groq` uses (line 472-484).
2. **No "low-importance" filter.** When the LLM has nothing to say, the row is still inserted with a placeholder summary ("Clip around X at 0:00", "Transcript segment too short to summarise"). The newer collector's `if c.get("importance") == "low": continue` is missing here.
3. **No transcript language gating.** Odia / Gujarati / Telugu transcripts are stored *verbatim*, not translated. The `/clips` UI is English-only — the user cannot read the quote.
4. **Keyword-substring matching, not entity matching.** A clip about an Odisha *heat wave* matches `"Odisha"` and gets stored under that keyword.

---

## 5. Recommendations (concrete, ordered by ROI)

### Now (1–2 hours each)

1. **Run [scripts/migrations/003_youtube_clips.sql](../../scripts/migrations/003_youtube_clips.sql) on the production DB**, or repoint the router at `video_clips`. Without this, the `/clips` page is dead. **(Release blocker.)**
2. **Strip the `clip` keyword and any single-word generic English word** from the keyword seed list. Add a guard: reject keywords < 4 chars or in a small stop-list (`clip`, `news`, `video`, `update`).
3. **Reject filler summaries at insert time.** If `ai_summary` matches `^(Clip around|Opening clip|.*too short to summarise)`, drop the row. This alone removes ~30 % of noise.
4. **Drop rows where `keyword` does not appear in `transcript_segment` OR `ai_summary`** (case-insensitive substring). 31 % of rows fail this — and they are precisely the rows users complain about.

### Next (1 day each)

5. **Mandate translation for non-English transcripts.** Add a Groq prompt step or use the existing `transcript_translated` field from `youtube_clips`. Don't let a Gujarati-only summary into the English UI.
6. **Score relevance, then filter at query time.** Surface only `relevance_score >= 0.6` (medium+) on the default `/clips` view. The `youtube_clips` schema already supports this.
7. **Migrate the legacy pipeline to the entity-based prompt** in [backend/collectors/youtube_collector.py:429-451](../../backend/collectors/youtube_collector.py:429) — its Telangana disambiguation block is the kind of guardrail the legacy pipeline lacks.

### Later (one sprint)

8. **Add a per-clip user feedback signal** (👍 / 👎 on each card). Train a re-ranker on negative feedback so the bottom-quartile clips never reach future users. The schema needs one new table `clip_feedback (clip_id, user_id, score, created_at)`.
9. **Aggregate per-channel quality.** Channels whose clips have a feedback score below a threshold (or filler-rate above one) should be auto-deactivated (`is_active = FALSE`).

---

## 6. Summary table — is the user well-served?

| Dimension | Verdict |
|---|---|
| Are clips reaching the user? | ❌ **No** — schema mismatch breaks the page |
| If they did reach the user, would they be relevant? | ⚠️ **~70 % of the time.** 31 % don't even contain the keyword |
| Are clip durations sensible? | ✅ Yes (avg 26.8 s, no malformed windows) |
| Is the AI summary informative? | ⚠️ ~30 % are filler boilerplate, not analysis |
| Is the transcript readable? | ❌ Multilingual transcripts surfaced untranslated to an English UI |
| Is keyword/entity matching honest? | ❌ Substring matching with no entity validation |
| Is there a feedback loop to improve quality? | ❌ None |

**Bottom line:** the `/clips` *code* is now in good shape (per the earlier debug + quality round), but the *content* the page would surface — once the schema mismatch is resolved — is **roughly 30 % noise**. The biggest wins are not more code: they are **(a) running the migration, (b) cleaning the keyword seed list, and (c) rejecting filler summaries at insert time**.
