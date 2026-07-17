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

One exception worth knowing: if you name an entity we don't already track, we add
it and tag it back across the archive for you. That's on us and it's usually
quick — just send the name.

**2. Confirming tonight's change — yes, and we'll check it term by term.**

We'll confirm each term individually rather than just checking that the request
succeeded. It's worth knowing why: if an entity name isn't one we recognise, the
request still succeeds — the name is accepted and treated as a plain text match
instead. You'd still receive articles, but you'd quietly lose entity-level
analytics (sentiment and outlet breakdowns) for that name.

So we'll confirm that every entity you intended resolved as an entity, and that
each term actually returns coverage. Send the list when you make the change and
we'll turn the check around the same night.

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
