# Mistakes log

A running list of the wrong turns we took, why each happened, and how it
was fixed. The goal is not blame — it is to recognise the *shape* of each
mistake so the next time the same shape shows up, we catch it before the
hours burn.

Each entry: **What** (the bug). **Why** (the underlying cause — usually a
wrong assumption, not bad code). **Fix** (what made it work). **Lesson**
(the rule we should follow next time).

---

## 1 · Substrate runner — missing `db.commit()` in failure paths

**When:** Sprint 0 substrate pass, first attempt.
**What:** First substrate run reported "processed 67,520 articles" but only
460 rows persisted in the DB. Roughly 99% of work was silently dropped.
**Why:** The runner's `fetch_failed` and `junk` paths called `db.execute()`
with the status update but never `await db.commit()` afterwards. SQLAlchemy
session rolled back when the session closed, throwing away the work.
**Fix:** Added `await db.commit()` to every terminal path in `process_one`.
**Lesson:** Every async DB write in this codebase must end with an
explicit commit. Never assume autocommit. The fact that the *successful*
path committed and the *failure* paths didn't is a copy-paste asymmetry
that's easy to miss — look for it in every new task.

---

## 2 · `COUNT(*) … ORDER BY` rejected by Postgres

**What:** Substrate runner crashed with a SQL syntax error when counting
the pending corpus.
**Why:** The query was `SELECT COUNT(*) FROM articles ... ORDER BY
collected_at DESC LIMIT :lim` — Postgres rejects `ORDER BY` on a bare
aggregate without a grouping clause.
**Fix:** Wrapped the LIMIT-and-order in a subquery, then counted the
subquery.
**Lesson:** `ORDER BY` and `LIMIT` need a real row stream to act on. If
you're aggregating, do the limiting in a subquery first.

---

## 3 · `call_groq()` unexpected keyword `response_format`

**What:** Substrate runner crashed instantly with a TypeError.
**Why:** I called the wrapper with `response_format={"type": "json_object"}`
copy-pasted from the OpenAI client signature. Our wrapper uses
`json_response=True` instead.
**Fix:** Renamed the kwarg.
**Lesson:** When wrapping a third-party SDK, the wrapper's signature is
authoritative — not the SDK it wraps. Read the wrapper docstring before
calling, every time.

---

## 4 · Classification task hard-capped at 50 tokens

**What:** Article classification calls were returning truncated JSON that
couldn't be parsed, so the runner dropped semantic results for everything.
**Why:** `TOKEN_LIMITS["classification"] = 50` was tuned for one-word
labels. The substrate task needed `article_type + locations + events` in
one JSON — easily 200-600 tokens.
**Fix:** Switched the substrate `task_type` to `relevance_explanation`
(200 token cap). Later moved to `profile_extraction` (1000) for full
fidelity.
**Lesson:** Token caps are tuned for a specific use-case, not the call.
If you reuse a task_type for a new shape of output, re-derive the budget.

---

## 5 · Sprint 1.2 — bolted-on HOME components, no design system

**What:** Built a stack of HOME-page components (Editor's Note, Threads,
Quotes, Sentiment, Brewing) as direct add-ons to the existing dashboard
shell. Result felt incoherent — user response was sharp: *"fire Maya
elias if this is the best she can do."*
**Why:** I built components without first locking the type scale,
colour roles, zone rhythm, or the rule for which surfaces are raised
vs flush. Each new piece imported its own decisions, and they fought.
**Fix:** Scrapped Sprint 1.2. Rebuilt from a design system first —
typography ladder, three depth tokens (`bg-recessed / bg-base /
bg-raised`), zone rhythm 112 / 72 / 36 / 14, one motion moment per
zone, strict palette with semantic colour roles.
**Lesson:** When the page is meant to feel cinematic, layout decisions
made *per component* never add up. Lock the system before you build the
first surface. Always.

---

## 6 · Pure black bg `#000` felt "fake"

**What:** Initial HOME used pure `#000` as the page background. User
reported it felt "fake and uneasy" — flat, void-like, OLED-clipping.
**Why:** True black has no light bouncing inside it. Real rooms always
have ambient lift; eyes expect it. Pure-black UIs cause edge vibration
and a sense that the page is "off."
**Fix:** Moved to warm near-black `#0A0705` with subtle radial light
washes distributed evenly across the canvas. Added film grain at 0.25
opacity. Three depth tokens give zones a sense of material.
**Lesson:** Pure `#000` is almost never the right answer for long
reading sessions. Lift to a near-black with a slight chromatic
undertone — warm or cool — and add a single subtle texture layer.

---

## 7 · Synchronous `trafilatura.fetch_url()` inside an async coroutine

**When:** Mid-corpus substrate pass. Throughput was 28-55 articles/minute
instead of the expected 1500+.
**What:** The substrate runner used `asyncio.Semaphore(8)` to allow eight
articles to process in parallel. In practice they ran *serially* — only
one HTTP fetch happened at a time, the other seven waited.
**Why:** `trafilatura.fetch_url(url)` is a **synchronous** function — it
uses `urllib.request` under the hood and blocks the event loop while the
HTTP call is in flight. So even though the semaphore permitted eight
concurrent coroutines, every fetch monopolised the loop until it
completed. Effective concurrency = 1.
**Fix:** Wrapped the call in `asyncio.to_thread`:
```python
html = await asyncio.to_thread(trafilatura.fetch_url, url)
```
Throughput jumped from ~28/min to ~163/min immediately (CPU usage 14% →
73%). 3-6x speedup.
**Lesson:** A sync I/O call inside an `async def` is a silent throughput
killer. Any blocking call inside an async function must be wrapped in
`asyncio.to_thread` (or run in an executor). The semaphore is a *lie*
without it.

---

## 8 · "All 20 Groq keys exhausted" — when they weren't (Cloudflare 1010)

**When:** Most of the substrate pass, 13+ hours of failed enrichment.
**What:** Substrate logs were full of `GROQ_POOL_EXHAUSTED: all 20 key(s)
exhausted. Pipeline will stall until daily reset.` Every single call
appeared to be rate-limited. 34,719 articles got marked `article_type =
'other'` with no locations and no events.
**Why:** Groq's API sits behind **Cloudflare WAF**, and Cloudflare was
rejecting our requests with `error code: 1010 / HTTP 403` — its
"banned based on browser signature" response. The Python `openai`/`groq`
SDKs default to a User-Agent like `openai-python/1.x.x`, which the WAF
rule treats as a bot. None of our keys ever got authenticated; Cloudflare
slammed the door before they were checked.
But our code's error handler treated *every* failed call as a
rate-limit candidate and called `mark_exhausted()` on the key.
After 20 such calls in a row, the pool reported itself fully exhausted.
The label was a lie — every key was healthy.
**Fix:** Two changes:
1. Pass a custom `httpx.AsyncClient` to `groq_sdk.AsyncGroq` with a real
   browser User-Agent (`Mozilla/5.0 … Chrome/124 …`). Cloudflare lets it
   through. All 20 keys immediately work.
2. Wire an HTTP-code-aware error classifier so a 403 is never again
   re-labelled as a rate-limit (see guardrails below).
**Lesson:** **Trusting your own log labels without verifying the HTTP
status code is the most expensive mistake in this category.** A 403 and
a 429 are completely different problems with completely different
recovery paths. When everything fails at once and your error handler
says "rate-limited" — read the actual response body before believing it.

---

## 9 · Built a token-math theory on the wrong premise

**When:** Right after seeing the "GROQ_POOL_EXHAUSTED" logs.
**What:** I proposed an elegant theory — *"50k articles × 1,400 tokens
each = 70M tokens demand; 20 keys × 500k TPD = 10M supply; therefore the
pool dies after 1/7th of the corpus."* Then I recommended *"add 15
Cerebras keys to soak the overflow."* The math was tidy, the
recommendation was clear, and **the whole thing was wrong**, because the
premise (keys actually being used) was never verified.
**Why:** I anchored on the symptom log (`POOL_EXHAUSTED`) and built a
narrative that explained it. The narrative was internally consistent —
it just had nothing to do with reality, because the actual failure was
upstream of any key usage.
**Fix:** Stopped, ran a 5-line test that hit one Groq endpoint with each
key. Got 20× `HTTP 403, Cloudflare error code: 1010`. The math theory
evaporated; the real bug surfaced in 30 seconds.
**Lesson:** **Before you theorise from logs, read one raw response body.**
A single `curl` with a real key tells you more than an hour of
spreadsheet math. When throughput drops, do not theorise — *go and
look*.

---

## 10 · Throwing capacity at a software bug

**When:** Same incident as #9.
**What:** Proposed adding 15 Cerebras keys (from a user's quota) to
"compensate" for Groq being out. They were duly added. They could not
have helped — the bug was in our HTTP client, not in either provider's
limits. Cerebras was actually still healthy; we just couldn't *reach* it
properly either through the wrong-symptom logging path.
**Why:** When you're holding a hammer (more keys / more capacity), every
problem looks like under-provisioning. It's especially seductive when
the visible symptom is the word "exhausted."
**Fix:** The UA fix on the Groq client. The 15 Cerebras keys *do* now
provide real failover capacity — no harm done — but they didn't fix
anything that was actually broken.
**Lesson:** **Never scale to fix a bug.** A scaling change is a
multiplier; if the underlying behaviour is wrong, you multiply the
wrong behaviour. Confirm the bug is mechanical (under-provisioning,
genuine throttling) before adding hardware.

---

## 11 · ETA extrapolation from a burst window

**What:** I gave ETAs of "1 hour" then "2-3 hours" then "6-12 hours" for
the substrate pass — successively further apart. Each was off.
**Why:** I extrapolated from short throughput samples without realising
the rate was wildly heterogeneous: a batch of fast-domain articles gave
~15k/hour for one window, a batch of slow/blocked-domain articles gave
~360/hour. Each extrapolation was correct for the window it sampled and
useless for the corpus average.
**Fix:** Mostly cosmetic — I now report the 1-min, 30-min, and 1-hour
rates side by side, and label which is which. The user can read the
trend rather than trust one number.
**Lesson:** When throughput is variable, **report several windows, not
one ETA**. A single forecast hides the variance that matters.

---

---

## 12 · Same Cloudflare-1010 bug — Cerebras provider, second time the same hour

**When:** Three hours after fixing the Groq instance of this exact bug
(see #8). User asked "test the Cerebras keys directly" — I did, and
**all 16 returned `HTTP 403 / Cloudflare error code: 1010`.** The same
Cloudflare WAF rule that had been blocking Groq was also blocking
Cerebras. We had been logging "Cerebras failover exhausted" for hours
without realising the failover lane was completely dead — Cloudflare
was rejecting every request before the API key was ever checked.

**Why:** When I fixed the Groq UA in `groq_client.py`, I only patched
the `groq_sdk.AsyncGroq` client constructor. The Cerebras call in the
**same file** uses raw `httpx.AsyncClient` without specifying any
headers — so it sent `python-httpx/0.27.x` as its User-Agent, which
Cloudflare's WAF blocks identically.

**Fix:** Add `"User-Agent": _BROWSER_UA` to the headers dict in
`_call_cerebras` (the constant was already defined for the Groq fix).
Cerebras now returns 200 OK on all 16 keys.

**Lesson — the meta-lesson:** when you find a fix that's about your
**client behaviour** (User-Agent, TLS fingerprint, header ordering),
**audit every other HTTP client in the codebase for the same hole.** I
fixed the symptom in the Groq path and walked away. The bug class
existed elsewhere in the same file, one function down. The HTTP-code
guardrail I added (Guardrail #1) would have caught this earlier if I'd
let it run — but I assumed the "Cerebras 429" line in the logs was
real because Cerebras *had* shown one 429 earlier (different code
path, the one with limited keys). Once I stopped reading my own logs
and probed the keys directly, the truth surfaced in 30 seconds.

**This is the same shape as #8, repeating.** I had even *written down*
the rule "audit body capture on non-2xx" — but the existing logs
during the Cerebras path only showed "Cerebras key rate-limited;
trying next" (line 383 of groq_client.py), without a body capture,
because that code path was written before the guardrail. So Guardrail
#2 was incomplete — only the Groq path got it. **Next fix:** add body
capture to the Cerebras path too, and audit every other LLM call in
the codebase for the same gap.

---

# Recurring shapes — patterns that show up more than once

Mistakes #8 and #9 are the same shape, and so are #1 and #4: a place
where **we trusted a label instead of the underlying signal.**

- #1, #4 — Function name / token cap implies one thing, actual behaviour
  is different. Read the source, not the name.
- #8, #9 — Error message implies a cause, actual HTTP code shows a
  different cause. Read the response, not the log line.

The remedy is the same in both: **prefer the raw signal over the human
summary of the signal.** The summary was written by another piece of
software, and that piece of software is often the one that's wrong.

# Guardrails being added (see PR following this commit)

Four mechanical defences against the recurring shape:

1. **HTTP-code-aware error classifier** (`groq_client.py`) — every
   non-2xx response is bucketed by code (401 / 403 / 429 / 5xx) and
   routed to a different recovery path. A 403 never gets re-labelled
   as "rate limit" again.
2. **Response-body capture on non-2xx** (`groq_client.py`) — every
   failed call logs its body. If Cloudflare ever 1010s us again, the
   string "Cloudflare error code: 1010" will be in the log in minute
   one, not hour fourteen.
3. **Boot-time provider health-check** (`backend/main.py`) — on
   container start, fire one tiny call per provider. Log loudly if any
   returns non-200. A 30-second probe at boot would have caught #8
   before deploy.
4. **`/admin/health/llm` endpoint** — runs the same check on-demand for
   debug + monitoring.

---

# Polish backlog — single migration after the substrate + re-pass finish

These are tracked separately because they should land as **one audited
migration**, not scattered fixes. Doing them piecemeal creates the same
"multiple conventions in the codebase" pattern that caused half the
mistakes above.

**Rule 1 — Literal `"null"` / `"None"` / `""` → SQL NULL.**
Found in `article_locations.region` (38 rows) and `.city` (43 rows).
Groq returns the string `"null"` when it has no value; our persistence
layer should normalise to actual SQL NULL.
Fix: `UPDATE article_locations SET region = NULL WHERE region IN
('null','None',''); UPDATE article_locations SET city = NULL WHERE city
IN ('null','None','');` — plus an INSERT-time check in
`_persist_locations`.

**Rule 2 — Indic-script duplicates merged to canonical Roman.**
Examples:
- `ఆదిలాబాద్` → `Adilabad`
- `పెద్దపల్లి` → `Peddapalli`
- `గద్వాల` → `Gadwal`
- `నర్సంపేట` → `Narsampet`
Fix: small Telugu-script lookup table for the ~33 Telangana district
HQs; apply at insert time and as a one-off UPDATE on the existing rows.
Same approach for Hindi / Devanagari, Kannada, Bengali if/when they
show up.

**Rule 3 — Common Indian city name variants → canonical.**
- `Bangalore` / `Bengaluru` → `Bengaluru` (canonical post-2014 rename)
- `Bombay` / `Mumbai` → `Mumbai`
- `Madras` / `Chennai` → `Chennai`
- `Calcutta` / `Kolkata` → `Kolkata`
- `New Delhi` / `Delhi` → choose one (likely `New Delhi` for capital,
  `Delhi` for the NCR; needs a product decision)
- `Mahbubnagar` / `Mahabubnagar` → `Mahabubnagar`
Fix: alias table + canonicalisation pass.

**Rule 4 — Reject non-country tokens in `country` field.**
- `Mars` (planet)
- `EU` (political union, not a country)
- `Asia-Pacific`, `Balkans`, `Caribbean` (regions)
- `Israel/Palestine` (ambiguous — pick one)
- `Telugu` (language — should be country=India, language=Telugu)
Fix: tighten the substrate Groq prompt with explicit rule
*"`country` MUST be a real sovereign nation — never a region, union,
language, planet, or aggregate. If unsure, return empty array."* Plus a
post-insert filter against an ISO-3166 country list to reject anything
not in the canonical set.

**Implementation plan when ready:**
- New migration `scripts/migrations/069_normalise_locations.sql` —
  applies rules 1, 2, 3 as UPDATE statements on existing rows.
- Edit `backend/tasks/substrate/run_corpus_pass.py` `_persist_locations`
  with the same rules at INSERT time so future articles land clean.
- Edit `GROQ_SYS` prompt in same file with the rule-4 tightening.
- One commit, one PR, one set of tests.

---

# Need Fixing — running track

Everything we discussed in this session that's been *deferred* rather than
done. Tagged by priority so the next session can pick up cleanly.

Priority key:
- **🔴 Critical** — do before onboarding any second user / before public launch
- **🟡 Soon** — this week if scaling, this month otherwise
- **🟢 Later** — polish, not blockers, do whenever convenient

## Scraper sources — per-source fixes

Many of these are recoverable with small per-source edits. Total potential
recovery: ~4,000+ articles currently marked `fetch_failed`, `junk`, or
`extract_failed`.

- 🟡 **PIB (Press Information Bureau) — 286 articles**
  Root cause: default Python User-Agent blocked.
  Fix: 5-minute change to send a Chrome UA in the govt-source HTTP client.
  Recovers: government press releases — high-value signal for Telangana
  user.

- 🟡 **Siasat Daily — 56 articles**
  Root cause: probably same UA issue as PIB, OR post-extraction filter
  in the substrate runner is bailing.
  Fix: 30 min investigation. Same UA fix likely.
  Recovers: Telangana-relevant English coverage from Hyderabad-based
  outlet.

- 🟡 **Dharitri — 197 articles**
  Root cause: junk threshold is tuned for English char counts, rejects
  valid Odia content as "too short."
  Fix: per-script char-count threshold (Indic scripts pack more meaning
  per char).

- 🟡 **TV9 Telugu — 227 articles**
  Root cause: `/photo-gallery/` URL paths are slideshows (inherently
  short), being correctly junk-classified but never should have been
  ingested.
  Fix: add URL exclude pattern in the source adapter.

- 🟢 **Prajavani — 1,509 articles**
  Root cause: article body lazy-loaded by JS; trafilatura sees the
  shell page only.
  Decision: low ROI — Prajavani is a Karnataka paper, not Telangana.
  Plan: narrow section subscription to news / elections / op-ed /
  business / explainer (drop district / horoscope / cartoons /
  astro-vastu / entertainment). Custom Playwright extractor only if
  user explicitly needs Karnataka spillover.

- 🟢 **NDTV — 1,111 articles**
  Root cause: Akamai bot-detection blocking the scraper IP via
  TLS fingerprint, not UA.
  Fix path A: `curl-impersonate` or `CycleTLS` to spoof a real Chrome
  TLS handshake. 4-8 hour build.
  Fix path B: ingest NDTV via their RSS feed only (less rich, but works).
  Recommend path B for v1, path A if RSS proves insufficient.

- 🟢 **Sportskeeda — 3,694 articles**
  User said skip. India-cricket-sports outlet. Not relevant for
  political-intelligence product.

- 🟢 **Sky News, Vanguard Nigeria, Sunday Guardian, Financial Times,
  ESPNcricinfo, TASS, CBC** — fetch_failed in bulk
  Same Akamai / Cloudflare / paywall family as NDTV. Defer until the
  TLS-fingerprint approach is built once, then apply to all of them in
  one pass.

## Data quality — polish pass (already detailed above)

See the four normalisation rules in the "Polish backlog" section above.
Status: **deferred** — to land as one migration after substrate +
re-pass finish, not as scattered fixes.

- 🟡 Rule 1 — literal `"null"` strings → SQL NULL (38 region + 43 city)
- 🟡 Rule 2 — Indic-script duplicates → canonical Roman
- 🟡 Rule 3 — Indian city name variants → canonical
  (Bengaluru/Bangalore, Mumbai/Bombay, Madras/Chennai, etc)
- 🟡 Rule 4 — reject non-country tokens (Mars, EU, regions, languages)

## Frontend / design system

- 🟡 **Lock the palette + background mood** — `demo-no-lines-v3.html` is
  the current candidate (warm near-black `#0A0705` + brass + sage +
  periwinkle + cream + red, even-distributed warm room, no separator
  lines). Need a yes/no from the user before porting to React.

- 🟡 **Sprint 1.3 v2 — rebuild HOME component-by-component** once palette
  locks. All 8 zones:
  1. Today's Reading (lede + exposure)
  2. Breaking Now
  3. Notable Quotes
  4. Narrative Threads + Watchlist + Sentiment
  5. Tracked Subjects
  6. Brewing Horizon
  7. Feed
  8. Brief footer

- 🟢 **Sprint 1.4 — article reader redesign**

- 🟢 **Sprint 1.5 — mobile responsive across HOME** (~1320px desktop is
  the current target; phone layout TBD)

- 🟢 Strip the legend strip from `demo-no-lines-v3.html` before
  production-ship (it's a working note, not a UI element)

## Production-readiness — backup / disaster recovery

- 🟡 **Off-server backup destination** — currently all `pg_dump` files
  live on the same VM as the live database. Catastrophic VM failure or
  ransomware loses both.
  Recommended: Hetzner Storage Box (BX11 1 TB, €3.45/month) accessible
  via rsync/sftp. Update `/root/backup-db.sh` to push each fresh dump
  off-server after creation. Keep 30 days off-server, 7 days local.
  **Trigger to actually do this:** before onboarding any second user,
  or before any risky schema migration.

- 🟡 **Hetzner VM-level Backups** — set in Hetzner Cloud Console (web
  UI, not CLI). Costs ~20% of server price; gets daily full-VM
  snapshots kept for 7 days, restorable in one click. Different
  failure-mode coverage than pg_dump (protects against disk failure /
  accidental `rm -rf`).
  **Action:** check console.hetzner.cloud → server → Backups tab. If
  disabled, enable.

- 🟢 Backup-cron failure alerting — currently if the cron at 20:30 UTC
  silently stops succeeding, we'd only notice when we tried to restore.
  Add: a check that compares `ls /root/backups` mtime against
  `now() - 26h` and fires an email / Slack / log alert on miss.

## Observability — what we still can't see

These are gaps in our ability to debug *the next* problem fast.

- 🟢 **Daily Groq / Cerebras token-usage tracking** — currently we know
  individual 429s but not "we're at 80% of daily TPD across the pool
  with 8 hours of work left." A small counter inside `groq_client.py`
  that aggregates per-key token usage + an `/admin/health/llm-budget`
  endpoint would surface trend before it bites.

- 🟢 **Per-source success-rate dashboard** — right now we manually
  query `articles WHERE source_id = X AND substrate_status = …`
  to find broken sources. A daily-rolling-counter per source would
  surface a regressing source within hours instead of weeks.

- 🟢 **Substrate runner progress endpoint** — `/admin/substrate/status`
  that returns `{pending, ok, junk, fetch_failed, extract_failed,
  current_rate}`. Currently we SSH and SQL — fine for now, won't scale.

## Documentation gaps

- 🟢 **`sources` table contract** — what each `source_tier` (1/2/3)
  actually means, what tagging convention is used, who decides.

- 🟢 **`thread_id` / narrative-cluster model** — how articles get
  grouped into threads, what the lifecycle looks like, when threads
  retire.

- 🟢 **The legacy `geo_primary` / `geo_secondary` / `entities_extracted`
  columns** — decision: keep parallel to the new `article_locations`
  child table, or drop after the substrate pass canonicalises the new
  one. Currently in limbo.

- 🟢 **Disaster-recovery runbook** — concrete steps for "the VM is
  gone, restore from a backup." Should fit on a one-pager so it's
  usable at 3am.

## Risk / unknowns to revisit

- 🟢 **Was the UA fix on `groq_client.py` strictly necessary, or did
  the `to_thread` fix carry the throughput improvement alone?** Test:
  temporarily revert the UA fix and see if the SDK still gets 200s.
  (Don't actually do this in prod — but worth knowing for the
  retrospective.)

- 🟢 **NDTV throughput is 1/4 of the May 4-7 baseline** — assumed to
  be residual throttle conservatism after the 2026-05-09 IP burn. If
  it doesn't recover within another 48-72h, the cause is something
  else and the throttle config needs review.

## 13 · Qwen3 silently ate the token budget via "thinking" mode

**When:** First integration of Qwen3:30b-a3b on the RTX 4090
(TRIJYA-7) into the unified LLM pool, 2026-05-13.
**What:** Every extraction call returned HTTP 200 from Ollama but
`message.content` was an empty string. The pool kept marking local
"cooled for 10s" and falling through to free providers (which were
also dead). Zero articles got persisted from local for hours.
**Why:** Two compounding issues. (a) We called Ollama's
**OpenAI-compatible endpoint** `/v1/chat/completions`, which silently
routes Qwen3's reasoning tokens into a *separate* `reasoning` field
the OpenAI spec doesn't expose, leaving `content=""` when the model
hit `finish_reason=length`. (b) We tried to disable thinking by
prepending `/no_think` to the system message — the OpenAI-compat
shim ignored it. The 1500-token budget got fully eaten by hidden
reasoning the caller never saw.
**Fix:** Switched the local-slot HTTP path to Ollama's **native**
endpoint `/api/chat` and passed an explicit `think: false` field in
the body. Response parsing changed from
`data.choices[0].message.content` to `data.message.content`.
**Lesson:** When wrapping a reasoning model, **the model's native
endpoint is the source of truth**, not the OpenAI-compat wrapper.
The wrapper exists for portability, not feature parity. Hidden
output channels (reasoning, tool_calls, tool_results) get dropped
or relocated in translation. Verify by inspecting the raw response
body the first time — don't trust the shape you expect.

---

## 14 · Oversubscribing Ollama with more workers than it could handle

**When:** First LOCAL-PRIMARY mode launch with
`LOCAL_LLM_MAX_CONCURRENT=8`, 2026-05-13.
**What:** Within seconds of starting `semantic_repass`, the log
filled with `httpx.HTTPError` exceptions with **empty messages** —
`UnifiedPool local network error () — cooling 10s` repeating every
~250ms. Local was being marked exhausted constantly even though
Ollama itself was healthy when probed directly.
**Why:** Ollama's default `OLLAMA_NUM_PARALLEL=4` means only 4
requests truly run in parallel; the rest queue at the server side.
We had 8 worker coroutines all grabbing the local slot
simultaneously (it's PRIMARY, get_slot returns it first). Ollama
accepted the connection on the 5th-8th workers and then either
dropped them mid-request or held them so long that httpx's
`ReadTimeout` fired with an empty exception message —
connection-level failures often have no `.args[0]` to print.
**Fix:** Set `LOCAL_LLM_MAX_CONCURRENT=4` to match
`OLLAMA_NUM_PARALLEL`. Bumped `OLLAMA_TIMEOUT_SECONDS` from 120 →
300 to absorb queue waits. Also improved the error log to include
`type(exc).__name__` so empty-message exceptions are still
identifiable (we'd been looking at `()` for an hour before figuring
out it was `ReadTimeout`).
**Lesson:** Always **match client-side concurrency caps to the
server's parallel-request capability**. Local LLM servers (Ollama,
vLLM, llama.cpp) have explicit parallel-request settings; learn
what they are and don't exceed them. And: when a logged exception
has an empty message, always also log the **class name** — that
alone often identifies the bug.

---

## 15 · Pool `min()` crash on empty-sequence in LOCAL-ONLY mode

**When:** Adding `LLM_LOCAL_ONLY=1` env flag so the unified pool
builds with only the local slot (no Groq, no Cerebras), 2026-05-13.
**What:** Pool ran fine for 5-15 successful calls, then began
crashing with `min() arg is an empty sequence` on subsequent
articles. 123 out of 128 attempts errored. Only 5 articles
persisted.
**Why:** Two assumptions in `get_slot()` both broke at once. (a)
The fallback branch `if not available: ... soonest_idx =
min(self._exhausted_until.items(), ...)` assumes there is *always*
at least one cooled slot to fall back to when no slot is
immediately available. (b) The local-slot capacity gate
`if self._local_inflight < _LOCAL_MAX_CONCURRENT` would skip local
when at capacity. In `LOCAL_ONLY` mode with 4 concurrent in-flight
and `_exhausted_until={}` (nothing cooled yet), the 5th request
found: zero available non-local slots, zero cooled slots, local
skipped due to capacity → `min({}.items(), ...)` → crash.
**Fix:** Added an explicit branch: in `_LLM_LOCAL_ONLY` mode,
return the local slot unconditionally — let Ollama queue internally
instead of relying on the caller-side cap. Ollama queues are robust
and the caller's 300s timeout absorbs the wait.
**Lesson:** **Edge cases compound.** Each individual rule
("return local first", "respect concurrency cap", "fall back to
soonest-cooled when nothing available") is correct in isolation.
Their *intersection* in a new mode created an empty set where one
of them assumed non-emptiness. When you add a mode flag
(e.g. `LOCAL_ONLY`), trace through *every* fallback path the
existing code uses — each one is an implicit assumption about pool
shape that the new flag may violate.

---

## What was *done* in this session — for the record

To distinguish "fixed already" from "still pending" when revisiting
later:

- ✅ Substrate runner async-fetch fix (`asyncio.to_thread`)
- ✅ Groq HTTP client UA fix (Cloudflare 1010 → 200)
- ✅ 15 new Cerebras keys added to .env.prod + docker-compose mapping
- ✅ Error classifier with 401 / 403 / 429 / 5xx routing
- ✅ Response-body capture on every non-2xx
- ✅ Boot-time LLM provider health-check (`@app.on_event('startup')`)
- ✅ `/admin/health/llm` endpoint
- ✅ Semantic re-pass task (`backend/tasks/substrate/semantic_repass.py`)
- ✅ This document (`docs/mistakes.md`) created with 11 mistakes +
  recurring shapes + guardrails + polish backlog + need-fixing track

---

## 2026-05-15/16 — v3 deployment + scraper recovery

A two-day cluster of incidents during the v3 substrate drain and the
parallel attempt to recover the RSS scraper after the FreshRSS data
loss event. Recorded contemporaneously so the *shape* of each
mistake is preserved for the next time.

### 16 · Ollama daemon CUDA-DLL corruption

**What:** Local model inference was running at 0.03 tokens/sec — a
RTX 4090 throughput consistent with a CPU fallback, not a GPU run.
No error appeared in the Ollama startup log; the daemon simply
loaded the model and *never* engaged the GPU.
**Why:** The Ollama install on disk was 553 MB. A healthy GPU-enabled
install is >1 GB because it bundles CUDA DLLs. The truncated install
silently failed CUDA detection and fell back to CPU. Nothing in the
startup banner indicated CUDA was missing — the daemon happily
served requests at CPU speed.
**Fix:** Full uninstall of Ollama, fresh reinstall from the official
installer. New install was 2 GB on disk and engaged the GPU on first
model load. Throughput jumped from 0.03 tok/s to ~85 tok/s.
**Lesson:** When "GPU detection silently fails" with no error in the
startup log, the very first check is the install size on disk — a
sub-1-GB Ollama install is *definitively* broken regardless of what
the logs say. Verify hardware-bound dependencies by binary size, not
by absence of error messages.

### 17 · FreshRSS admin user deleted (cause unknown)

**What:** All 574 RSS sources stopped returning new articles. The
backend's `collect_rss` task reported `sources_checked=0` despite the
DB having 574 active `source_type='rss'` rows.
**Why:** The `admin` user directory under
`/config/www/freshrss/data/users/admin/` was missing entirely from
the FreshRSS container. With no admin user, the GReader API
authentication returned 403 on every request and the subscription
list (574 feeds) was effectively unreachable. Root cause of the
deletion itself was never determined — likely a stray `rm` against
the wrong path during an unrelated debug session, or a volume mount
mishap during a container restart.
**Fix:** Recreated the admin user via the FreshRSS CLI inside the
container; `chown abc:users` on the user directory; restored
`/config/www/freshrss/data/config.php` from the default template
with `api_enabled => true`. *Side effect:* the subscription list for
all 574 feeds was wiped along with the user data and had to be
re-subscribed via the GReader `subscription/quickadd` API.
**Lesson:** FreshRSS state lives in a single mounted directory with
no integrity check at startup — losing the admin user directory is
silent (no error, just 403s everywhere). Add a boot-time health probe
that hits the FreshRSS GReader auth endpoint with a known cred and
alerts loudly on failure; without it, a missing user looks
identical to "no new RSS today."

### 18 · Cerebras TPD quota burn — 99.5% in a single 8h window

**What:** A single drain run consumed **26.87 M of 27 M** daily
tokens (99.5%) in one 8-hour burst. The next 16 hours of pipeline
work had zero Cerebras budget and stalled on rate-limit refusals.
**Why:** The drain throughput controller knew about per-minute rate
limits (RPM / TPM) but had no concept of the per-day token budget.
It cheerfully sent requests at the maximum sustainable RPM,
exhausting the TPD ceiling roughly a third of the way through the
day.
**Fix:** Workaround for this run was to fail over to Ollama + Groq
once Cerebras returned 429s. Real fix is pending: introduce a
**TPD-aware back-pressure controller** that tracks rolling 24h token
consumption per provider and throttles the drain when consumption
exceeds the daily-budget pace (i.e. if you're 50% through the day,
you should be ~50% through the daily budget, not 99%).
**Lesson:** Rate limits and quota limits are different signals.
RPM/TPM throttle protects the *provider* from instantaneous spikes;
TPD/MTD protects *you* from premature exhaustion. A drain that
respects only the first runs flat-out and blows the second. Any
substrate controller that runs continuously needs awareness of both.

### 19 · Groq organization-restricted — all 24 keys blocked

**What:** All 24 Groq keys began returning `400 organization_restricted`
on every request. Health-check endpoint showed every Groq slot in
the unified pool as failed.
**Why:** Hypothesis (not confirmed by Groq support yet): aggressive
sustained request volume during the v3 drain triggered a
platform-side block on the org. Cloudflare UA hack still works (so
this is *not* a repeat of #8 / #12), the requests are reaching
Groq's actual API layer — they're just being refused at the org
level with a structured error code, not a WAF rejection.
**Fix:** Two-track. (a) Contacted Groq support to investigate the
restriction; awaiting response. (b) Reduced dependency on the Groq
lane in the unified pool — pipeline now defaults to Cerebras +
Ollama, with Groq treated as opportunistic capacity when available.
**Lesson:** Provider-side org blocks are a different failure class
than rate limits — they don't lift with cooldown timers and aren't
fixable by client-side changes. The pool's "cool the slot" recovery
strategy is appropriate for 429 but not for 400-with-structured-
reason. Add a separate "provider-disabled" state that doesn't auto-
recover and requires explicit human re-enable; otherwise the pool
spends cycles probing dead lanes indefinitely.

### 20 · Load average 130 from simultaneous worker restart

**What:** After a long maintenance pause, restored all 7 Celery
worker types (collectors, social, youtube, documents, nlp,
relevance, brief) simultaneously. Load average on the VM spiked to
130 within 30 seconds. SSH banner timeouts began appearing; web UI
became unresponsive. Recovery took ~20 minutes of slow,
hand-throttled work.
**Why:** Each worker pool, on startup, fires its full prefetch
batch at once — that's `concurrency * prefetch_multiplier` tasks
admitted per pool in the first second. Across 7 pools that's
~30-40 concurrent tasks immediately, every one touching Postgres
and/or making outbound HTTP. The DB connection pool saturated, lock
contention spiked, and the kernel's run queue exploded.
**Fix:** Future restart procedure is now: bring workers up **one
queue at a time, with a 30-60s gap between each**. Verify each pool
reaches steady state (CPU back below 30%, no DB lock waits) before
starting the next one. Order matters too — `nlp` last because it's
the heaviest.
**Lesson:** A multi-pool restart looks like one command but is
actually N separate thundering-herd events overlapping. Stagger them.
If you can't stagger, at least bring up the lightest pools first
and let the heavy ones land on a warm system.

### 21 · `semantic_repass.py` ignored `LOCAL_LLM_*` env flags

**What:** During the v3 drain, monitoring showed "traffic going to
Groq/Cerebras NOT Ollama" — exactly the opposite of what
`LOCAL_LLM_PRIMARY=1` was supposed to enforce. Local inference was
sitting idle while the cloud lanes burned quota (see #18).
**Why:** The `LOCAL_LLM_PRIMARY` flag was wired only into the
unified-pool entry point. `semantic_repass.py` calls the LLM through
a different code path that constructs its provider list manually
and never consulted the local-primary flag. Result: the flag
"worked" in the sense that it was set and read, but the code path
the drain actually exercised ignored it.
**Fix:** Added a new `LLM_LOCAL_ONLY=1` env var that *does* gate at
the unified-pool level (forcing the pool to return only the local
slot). Switched the drain to set this flag, which works because
all of semantic_repass's calls eventually reach the unified pool —
the routing decision moves up the stack to where the gate lives.
**Lesson:** Env-flag plumbing is not consistent across substrate
code paths. There are at least two LLM-routing layers in this
codebase (unified pool + per-task manual provider lists), and a
flag set at one layer doesn't necessarily propagate to the other.
Pending audit: find every call site that constructs an LLM provider
list manually and either route through the unified pool or
explicitly consult the local-primary flag.

### 22 · Byline extractor missing 95% of available bylines

**What:** Bylines were being extracted on only 14% of articles. A
visual audit of 50 articles showed bylines visibly present on the
page in 38 of them — meaning the extractor was missing ~62%
of the actually-available signal.
**Why:** Three compounding gaps in the extractor patterns. (a) The
HTML meta-tag matcher only checked `<meta name="author">` and not
the equally common `<meta property="article:author">`. (b) The
JSON-LD parser handled the singular `"author": {...}` shape but
crashed silently on the array shape `"author": [{...}, {...}]` used
by multi-byline articles. (c) The blacklist that rejected boilerplate
authors ("Staff Reporter", "PTI", etc.) was over-aggressive and
filtered out *source-level* bylines like "Hindu Bureau" which are
actually meaningful attribution at The Hindu.
**Fix:** Broadened the meta-tag patterns to include
`article:author`, `og:article:author`, and `dc.creator`. Added
array-handling to the JSON-LD parser with explicit join logic for
multi-author. Softened the blacklist to keep source-level bylines
("X Bureau", "X Desk") while still rejecting truly empty
boilerplate. Byline coverage went from **14% → 62%** on the
audit sample.
**Lesson:** "Coverage looks low" is *almost always* a multi-cause
problem — patterns missing, schema variants unhandled, over-eager
filters all contributing. Don't stop at the first culprit. When the
fix-then-measure cycle shows "still bad", keep looking — there are
usually 2-3 separate bugs converging on the same low number.

### 23 · Schema mismatch in audit queries

**What:** Wrote audit SQL referencing columns `speaker` and
`claimant` — Postgres immediately errored with `column does not
exist`. Spent 20 minutes assuming the table was missing data
before reading the schema.
**Why:** Assumed column names without checking. The actual schema
uses `speaker_name` and `subject_text` (Postgres convention favors
explicit name-suffixed columns to avoid clashes with keywords and
reserved tokens, and we'd standardised on that elsewhere). The
quick `SELECT` reflected the names the *prompt context* implied,
not what the DB actually had.
**Fix:** Trivial — corrected column names. The real fix is
procedural: always `\d <table>` (or equivalent) before writing
audit SQL.
**Lesson:** When writing audit / debugging SQL, the *schema check*
is step 0, not step 5. Especially in this codebase where similar
domain concepts get different column names across tables (`speaker`
on one, `speaker_name` on another, `author` on a third). The 30
seconds of `\d` is always cheaper than the 20 minutes of "why is
this empty."

### 24 · Drain stalls on local network errors without re-test

**What:** During a brief TRIJYA-7 connectivity blip, the drain
correctly cooled the Ollama slot ("slot[0] cooled 10s"). When the
TRIJYA-7 link came back online (within ~3 minutes), the drain
*continued* retrying Ollama and *continued* hitting transient
errors during the recovery window, marking the slot cooled again
and again. Eventually it gave up on Ollama for the rest of the
drain even though Ollama itself was healthy by minute 5.
**Why:** The cooldown timer was a fixed 10s with no awareness of
*duration of outage*. Each individual retry, hitting a still-warming
network path, looked like another failure. The exponential-cooldown
logic correctly grew the window — but it grew based on consecutive
failures, not based on how long the *outage* had lasted. Once the
slot was marked deeply cooled, the drain never explicitly
re-probed it; it just relied on the cooldown timer to expire, by
which point the drain had already routed all its remaining work
elsewhere.
**Fix:** Immediate workaround was to restart the drain — that
reinitialised pool state and Ollama re-engaged immediately. Pending
real fix: when a slot's cooldown exceeds N seconds (suggest 60s),
fire an explicit health-probe request on next access; if it
succeeds, reset the cooldown to zero and rejoin the rotation.
Otherwise the pool can be permanently in a degraded state from a
transient blip.
**Lesson:** Cooldown timers based on failure-count are right for
short-burst rate limits, wrong for outage recovery. Long-duration
outages need an explicit re-test path that proves recovery, not
just an absence of recent failure. Without it, a 90-second network
hiccup becomes a multi-hour pool degradation.

### 25 · Agent watchdog killed orchestrators while work continued

**What:** During the v3 drain, multiple orchestrating subagents
(eval F, eval G, byline patch, audit script) were killed by the
"no progress for 600s" watchdog. Each kill produced a flurry of
recovery actions ("relaunch", "diagnose", "investigate"). But the
*underlying scripts* — running inside `rig-backend` container,
detached from the agent — continued executing perfectly fine and
produced their expected output on schedule.
**Why:** The agent was polling synchronously for progress: every
loop it `ssh`'d to Hetzner, queried Postgres for row counts, and
slept. The 600s no-progress watchdog measured *agent-side
activity*, not *job-side activity*. Because the job took longer
than 600s per progress checkpoint, the agent appeared idle to the
watchdog even though the job was advancing.
**Fix:** Restructured the pattern. Instead of "agent runs the job
and polls", the new pattern is: agent kicks off the job in a
detached container process, the job *writes its own progress* to a
known table or file, and the agent returns immediately. Parent
agent (or a later session) checks the progress table when ready
for the result.
**Lesson:** When orchestrating long-running container work, don't
have the agent be the synchronous owner. Let the work file its own
progress and let any observer (agent, human, dashboard) read it
asynchronously. This makes the agent re-startable, lets multiple
sessions inspect the same job, and removes the watchdog timeout
as a failure mode entirely.

---

