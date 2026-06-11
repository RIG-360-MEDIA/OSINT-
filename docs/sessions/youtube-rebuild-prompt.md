# New-chat kickoff prompt — paste this into a fresh session

---

I want to **rebuild our YouTube scraping & data-extraction module from scratch**.
The existing one works but the output quality is bad and the IP-block handling is
fragile — treat it as **reference only, not something to extend**. We're building new.

**Read first:** `docs/sessions/youtube-rebuild-kickoff.md` — it has the full reference
map, the concrete failure modes of the old module (from the clips audits), the data
model, env vars, deploy topology, and the IP-block problem statement. Also skim the
old collector `backend/collectors/youtube_collector.py` and the audits in
`docs/qa/clips-*.md`.

**What the module must do:** per monitored YouTube channel → discover new videos →
get a usable transcript → extract segments mentioning our monitored political
entities → produce clean **English** summaries + precise timestamps + embeddings →
store clickable clips for the `/clips` pillar and the corpus.

**Hard requirements (these are the old module's sins — don't repeat them):**
- ONE entity-keyed pipeline + table. No free-text keyword path. No second pipeline.
- English-only, canonical-entity-only output; reject filler/empty/non-English summaries
  at insert time.
- Real timestamp XOR full-video link — never disagreeing columns/URL.
- No silent fallbacks: every fallback path emits a metric + WARNING with a reason.
- Many small files (discovery / transcript / extract / store), type-hinted, tested.

**The core problem to solve creatively — IP blocks.** YouTube blocks our Hetzner
datacenter IP from anonymous transcript/RSS/audio fetches. Current mitigations (single
static proxy + one cookie file + a crude circuit breaker) are brittle, and **we must
never burn the prod IP** (a raw CLI probe cost us 24–72h of downtime once — all access
goes through a throttle). I want us to explore options properly: residential/rotating
proxy pools, official Data API captions, audio-first via proxy → Groq Whisper as the
*primary* path, paid transcript APIs for tier-1 channels, cookie rotation/health, and a
real rate-limiter with per-IP reputation tracking.

**How I want to start:** before building anything, **spike the proxy + transcript path**
and measure the actual block rate on ~20 real Telangana channels, so we can pick a proxy
strategy and budget. That decision gates the rest. Then plan the phases with me.

**Before deploying anything to Hetzner**, confirm the deploy method with me (baked
`rig-backend` container — `docker cp` + restart, no bind mount) and never probe YouTube
raw from the prod shell.

First: read the kickoff doc, ask me the open questions in its §8 (proxy budget, channel
list source, main-corpus vs OSINT, migrate vs new table), then propose the spike plan.
