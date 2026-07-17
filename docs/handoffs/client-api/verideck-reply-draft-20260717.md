# VeriDeck reply — draft 2026-07-17

**Status:** DRAFT — not sent. Review, fill the names, send from your own client.

**Deliberately NOT in this draft** (per instruction: only what they need, nothing
about our internals):
- no column/table names, no mention of which field we changed internally
- no mention of the substrate/translation pipeline, GPUs, or the ingestion incident
- no mention of the HTML cleanup (invisible to them once it lands; if they ever
  ask why `summary_original` looks tidier, that's a one-line answer, not a
  disclosure)
- the entity dictionary is described as "we add it and tag it back" — not how
- weekend watch is deliberately non-committal (Pranav's call, not ours to promise)

**The one thing they MUST read:** the summary length change. They bulk-mirror our
payloads; if their store has a fixed-width column at 400, Monday breaks. That is
why it is called out under its own heading rather than buried.

---

**Subject:** Re: DIPR scope expansion — backfill, tonight's PATCH, and two heads-ups before Monday

Hi <name>,

Short answers to your three questions, plus two heads-ups worth reading before Monday.

**1. Backfill when you expand scope — none needed.**

When you add an entity or a keyword, history comes with it automatically. Scope
acts as a filter over coverage we already hold; it is not an instruction to start
collecting. So the moment your change lands, past coverage for the new terms is
queryable immediately — there's no job to run and no waiting period.

We verified this rather than assuming it: we added a new entity and a new keyword
to a test scope and immediately saw months of prior coverage returned for both.

**2. You never have to guess what we track — the PATCH response tells you.**

Worth reading, because it removes a question you'd otherwise have to ask us every
time you expand.

When you `PATCH /v1/scope` with `add_entities`, every name is resolved against our
full entity list, and **the response reports what happened to each one**:

- `resolved_entities` — the names we matched, each with its `entity_id`
- `added_as_keywords` — the names we did **not** recognise

A name in `added_as_keywords` is still accepted and still working — it's matched
as text rather than as a known entity. So nothing fails quietly: if a name lands
there and you expected an entity, **send it to us and we'll add it and tag it back
across the archive.** That's on us and it's usually quick.

**What an unrecognised name actually costs you — less than you'd think:**

- You keep the articles, **and you keep sentiment**: `/v1/analytics/keyword-sentiment`
  scores **any** term you pass it, with no dependency on our entity list at all.
- What you lose is the per-outlet breakdown (`/v1/analytics/outlets` is keyed by
  `entity_id`) and the `/v1/entities/{id}` views for that name.

**3. Confirming tonight's change.** You can now confirm it yourself in one step —
read `added_as_keywords` in the PATCH response. Send us the list too and we'll
cross-check the same night if you'd like a second pair of eyes.

**3. Weekend watch.** Coming back to you separately — that's a staffing call our
side and I'd rather confirm it than promise cover I haven't arranged.

**Sandbox key.** Issued and tested. Coming in a separate message.

---

**Heads-up 1: keyword language — this is the big one for DIPR**

Much of the Telangana press we carry publishes in Telugu. Keywords match against
the article's own text, so an English keyword will not match a Telugu article —
"irrigation" will not find "నీటిపారుదల".

Names usually survive, because they often appear in Latin script inside Telugu
copy. Ordinary nouns don't.

The practical effect: an English-only term list will make DIPR's feed look far
thinner than our actual coverage of them. **Send us your term list and we'll
supply native-script variants** — ideally before Monday, so day one looks like
the real picture.

Two smaller notes on keywords: they match the headline and opening text rather
than the full body, and they match as substrings — "musi" will also match
"music". Distinctive terms work best.

Native-script terms work normally for scope and for the article feed. One current
limitation to save you the debugging: on `/v1/analytics/keyword-sentiment`
specifically, some Telugu-script terms are timing out right now (Hindi and Latin
terms are fine). We're on it — if you plan to lean on that endpoint for
Telugu-script terms before Monday, tell us and we'll prioritise it.

Also, that endpoint's window parameter is `window` (days), not `days` — passing
`days` is ignored and you'll silently get the 7-day default.

**Heads-up 2: summary length increased today — check your field widths**

`summary` and `summary_original` now return up to 2000 characters. They were
previously capped at 400. Alongside that, English coverage of `summary` on
non-English sources is substantially higher as of today, which is a straight
improvement for the DIPR brief.

**If you're mirroring into fixed-width columns, please check the width before
Monday** — of everything in this mail, this is the one change that could affect
an existing integration.

Happy to get on a call before the 19th if that's easier.

Best,
<name>
