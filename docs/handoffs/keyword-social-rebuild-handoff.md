# Keyword Social Rebuild — Full Handoff (start-of-chat context)

**Written 2026-07-07.** Hand this + the kickoff prompt to a new chat so it picks up
exactly where we are, with no context loss. Read this top-to-bottom first.

---

## 0. The one-paragraph situation

We are rebuilding RIG Surveillance's **Keyword Intelligence** feature. The first
version shipped as "7 phases done" but was only ever tested on the keyword
**"Modi"** — which is saturated in our stored data, so every panel looked full.
Tested honestly on a fresh keyword (**"Tridel"**) it collapsed: it only *reads*
pre-stored data and never *collects* live. It has been **hidden from the UI for all
roles** (including admin) until rebuilt. **User's decision on rebuild order:** do
NOT start with the dossier UI / evidence-linking / cold-start. **First** build every
social platform we can, each with **keyword search**, and **prove it works
completely** on real keywords. Everything else comes after that foundation is proven.

## 1. Hard rules (do not violate)

- **VERIFY against the live system/DB — never trust docs, schema files, or old
  claims.** This whole rebuild exists because a past session trusted a checklist
  instead of testing. Run the query. Read the actual file. Test the real keyword.
- **No fabrication.** Never invent eval numbers or "it works" without proof. Report
  trusted / unverified / failed separately. Inspect the actual artifact.
- **Prove on TWO keywords** every time: one hot/common AND one fresh/niche picked at
  test time. The Modi-only test is what caused this mess.
- **`rig-backend` is core ingest** — a mistake there breaks ALL data collection, not
  just this feature. Touch it carefully, show diffs before applying, never add a
  second Celery scheduler/consumer (CLAUDE.md foot-gun).
- **Off-limits:** WeChat Moments / private personal accounts / DMs, data-broker
  people-search, breach dumps, dark-web crawling. Public data only.
- **Immutability / small files / error handling** per the user's global coding-style
  rules. Secrets via env vars only — never hardcode a token (e.g. VK/Twitter cookies).

## 2. Architecture you must know (verified, unusual)

- **Two backends.** `rig-backend` = core ingest (FastAPI + all Celery workers in ONE
  container via `/start.sh`, bind-mounts `/root/rig`; holds social scraper code +
  session secrets). `osint-backend` = the night-desk API (separate baked image,
  read-only `analytics_user` DB role, RW only to `analytics.*`). They are isolated on
  purpose. `products/osint/backend/social_live.py` comment: "httpx only — does NOT
  touch the live rig-backend social pipeline."
- **Frontend:** `products/osint/design/night-desk/` = Vite/React SPA, deployed to
  `desk.rig360media.com`. Build = `npm run build`; deploy = `scp dist/* ...
  /root/rig/night-desk-dist/` (Caddy serves it). No rsync on the box.
- **Celery broker is Postgres** (`sqla+postgresql://`), NOT Redis. Both services share
  the same `rig-postgres`.
- **DB:** `social_posts`, `social_authors`, `social_watchlist` live in schema `public`
  (migrations 118/119). `social_watchlist` cols: platform, target_type
  (handle|subreddit|channel|hashtag|keyword|location), target_value, client
  (multi-tenant, e.g. `india_govt`/`tridel`), priority, is_active, next_check_at.
  `social_posts` has NO `matched_keyword` column — post→query link is only in raw JSON.
- **Access:** Hetzner SSH `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`; DB `docker
  exec rig-postgres psql -U rig -d rig -c "..."`. curl_cffi 0.15.0 + Py3.11 on the box.

## 3. Ground truth: what social collectors ACTUALLY exist (verified by reading code)

Framework: `backend/collectors/cheap_stack/` — swap-able `Method` protocol +
normalized output + `Egress` proxy routing (`base.py`). `pipeline_adapter.py` emits the
`social_posts` dict shape. All three below verified emitting REAL rows on Hetzner's
datacenter IP in a prior session.

| Platform | Keyword search? | Status / method | File |
|---|---|---|---|
| **Reddit** | ✅ NATIVE | keyword + subreddit search works today | `backend/collectors/reddit_scraper.py` |
| **TikTok** | ✅ NATIVE | tikwm `/api/feed/search?keywords=` (used in social_live.py); `/api/user/posts` for handles + HTML fallback | `cheap_stack/tiktok.py`, `pipeline_adapter.py` |
| **Twitter/X** | ✅ REAL (cookies) | **NOT dead** — only official API is 402. twscrape (cookie `TWITTER_AUTH_TOKEN`+`TWITTER_CT0`, `.search(kw)`) fills the ~38k live rows; Nitter (`search_twitter`) + syndication = fallback | `twitter_scraper.py`, `social_scraper.py` |
| **YouTube** | ✅ NATIVE | keyword video search; an existing YouTube pipeline in-repo to reuse | (youtube pipeline) |
| **Instagram** | ⚠️ hashtag | Direct `web_profile_info`+`x-ig-app-id` works from datacenter, NO relay (403 fear proven FALSE). No free caption search → keyword via hashtag (`hashtag_medias_recent`, instagrapi relay). Relay = fallback only | `cheap_stack/pipeline_adapter.py::collect_instagram_posts`, `instagram_relay_instagrapi.py` |
| **Telegram** | ⚠️ NOT global | `t.me/s/{channel}` scrape, no bot token — but per-channel, not global. Plan: keyword-search within a curated **channel set** (user chose this), labeled honestly | `cheap_stack/pipeline_adapter.py::collect_telegram_web` |
| **WeChat** | ⚠️ title-level | Discovery via DDG site-dork (no China IP, title only); Sogou blocked from non-China IP. Content-fetch of a `mp.weixin.qq.com` URL via curl_cffi works FREE but the **fetcher is UNBUILT** — the one genuinely-new collector | `cheap_stack/wechat.py`, `social_live.py` |
| **VK** | ⚠️ needs token | `newsfeed.search`/`wall.search` real keyword search, needs a free VK API token (user is getting one) | (to build) |
| **Discord / forums / Tumblr** | ❌ | No real free global keyword search — do NOT fake. Exclude, label "not available" | — |

## 4. THE PLAN (authoritative)

Full plan file: `C:\Users\Dell\.claude\plans\rippling-singing-emerson.md`.

**Phase 1 (NOW) — all-platform keyword-search collectors, proven standalone.**
One keyword in → real keyword-matched posts out, per platform. NO database, NO UI, NO
rig-backend integration yet. Add a keyword-search method per platform on the cheap_stack
swap-able framework where missing (TikTok feed/search, IG hashtag, WeChat content-fetch,
VK wall.search, Telegram channel-set, Twitter twscrape/Nitter). **Deliverable = one
verifier** `verify_keyword_collectors.py` that takes a keyword and prints per platform:
method, # real results, 2-3 sample rows (text+url+engagement+timestamp). Run on dev AND
Hetzner. **Proof bar:** ≥2 keywords (hot + fresh); each platform returns REAL matched
rows OR shows its labeled honest limitation. Nothing silently empty = "done".

**Later passes (deferred, in order):** persist keyword-collected rows into `social_posts`
(`_land_posts` reuse) → on-demand trigger from a keyword search (rig-backend internal
endpoint — high blast-radius, eyes-on) → evidence-linking + `EvidenceModal` UI (every
number clickable to its underlying posts) → re-enable the dossier tab only once it holds
on a fresh keyword.

## 5. Decisions already made this session

- Keyword tab **hidden** from all roles (App.jsx routes + Sidebar nav) — deployed. Keep
  hidden until rebuilt.
- Collection-first ordering (user's call), not UI-first.
- **Telegram** = channel-set keyword search (free), labeled not-global (user chose).
- **VK** = include; user is getting a free token (how-to below).
- **Twitter** = alive, include via twscrape cookies (+Nitter). Corrected from a wrong
  "dead" claim.
- Instagram = direct `web_profile_info`, no relay on the critical path.

## 6. Pending inputs from user

- **VK token:** vk.com/apps?act=manage → Create Standalone app → get Application ID →
  `https://oauth.vk.com/authorize?client_id=APP_ID&scope=wall,groups&response_type=token&v=5.199`
  → token is in redirected URL after `access_token=`. Provide it → stored as env
  `VK_ACCESS_TOKEN`.
- **Twitter cookies** (if the live twscrape session needs refreshing): `auth_token` +
  `ct0` from a logged-in x.com browser session.

## 7. Memory files to read (in `~/.claude/projects/C--Users-Dell-Desktop-rig-surveillance/memory/`)

- `project_cheap_stack_collectors.md` — per-platform proven methods (the source of §3).
- `project_social_keyword_driven.md` — the HARD rule: store-everything ONLY for
  articles+newspapers; social + all OSINT = keyword/on-demand (Meltwater), persist-from-use.
- `project_instagram_relay_fix.md` — IG session/relay history.
- `project_social_platform_validation.md` — earlier social pipeline deploy state.
- `feedback_no_fabricated_results.md`, `feedback_no_clusters_in_askrig.md`.
- `MEMORY.md` — the index (one line per memory).

## 8. Definition of done for Phase 1

`verify_keyword_collectors.py` run on the box, on 2 keywords, output pasted back, showing
each platform either returning real keyword-matched posts OR its honest labeled limit.
No platform silently empty. Then — and only then — move to persistence + wiring.
