# 07 — Known Issues (open, with precise causes)

## 1. YouTube audio transcription is bot-blocked
- yt-dlp audio download fails with "Sign in to confirm you're not a bot" even
  WITH valid logged-in cookies — YouTube BotGuard rejects the Hetzner
  **datacenter IP**. Captions work; caption-less videos get no transcript.
- **Needs:** a residential/rotating-residential proxy (paid) — on HOLD.
- **Do NOT** run raw `yt-dlp` from Hetzner to "test" — it degrades IP reputation
  (recovery 24–72h). Always go through the production task path.

## 2. Cross-language same-event duplicates in Top Stories
- Text-based de-dup can't match a Telugu and an English version of the SAME story
  (no shared words). e.g. "TDP RS seats" appeared once in Telugu and once in
  English in the validated top-6.
- The clean fix needs the event-cluster id, but **`thread_id` is 0% populated**
  (event clustering isn't running on this corpus).
- **Workaround option (not yet done):** translate each candidate headline to
  English first, then de-dup on the English text. Costs a little speed on first
  load. (User was asked; decision pending.)

## 3. Off-state relevance leak (mitigated, not eliminated)
- The AP persona has Karnataka in `states` + tracks some Karnataka figures, so
  off-state stories can score as high as the principal. The "Andhra-first" rule
  in `_diversify` pushes them below AP stories, but the underlying *scoring*
  still ranks them high. A deeper fix would weight the **primary** state above
  secondary states in `relevance.py` (kept out of that SQL for plan-safety).

## 4. `summary_executive` coverage is only ~60–72%
- Not all articles get an LLM exec summary; we fall back to lead text + translate.
  Improving upstream coverage is a pipeline task (rig-backend NLP), out of
  osint-backend scope.

## 5. `now_sim()` dependency
- All time windows use `analytics.now_sim()`. It's currently real-time. If
  "nothing updates" is ever reported again, **check `now_sim()` vs `now()` first**
  before assuming a bug.

## 6. Repo divergence (host vs local)
- `/root/rig/` on Hetzner can differ from a local clone (e.g. `celery_app.py`,
  files only present on the host like `youtube_task.py`). **Always `diff` before
  overwriting whole files**, or patch in place.

## 7. Twitter/X hidden; clips lag
- Twitter/X is ingested but hidden in the UI. Clip volume can lag due to issue #1.
