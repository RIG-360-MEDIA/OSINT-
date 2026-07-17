# VeriDeck reply — draft 2026-07-17 (v2, written against their actual mail)

**Status:** DRAFT — not sent. Fill the names, send from your own client.

## What changed from v1 and why

v1 answered the 07-16 handoff's version of their question. Their real mail asks
something narrower and more dangerous: *"when we add the new **keywords** tonight,
does that history come through automatically?"*

**Verified answers:**
- **Entities: yes, automatic, no job.** Proven live — entities added 2026-06-03
  carry mentions on articles from 2026-04-22 (Malta 223 mentions, Mauritius 125,
  Solomon Islands 108; oldest tagged article predates the entity in every case).
- **Keywords: they deliver nothing.** Not history, not new coverage. Scope keywords
  are stored and echoed back but never filter the article feed (no keyword clause
  exists in the query). Measured on their live org: 321 articles mention
  "kaleshwaram" in 30d; they receive 226 — every one of those because the article
  also names a scoped politician. Their keyword contributes zero.

So the single most useful thing we can tell them is **put the terms in as entities,
not keywords** — that is where history and analytics actually come from, and it is
the honest answer to "is there a controlled backfill you can run".

**Deliberately NOT in the mail:** no column/table names, no architecture, no
mention of the ingestion incident or the HTML cleanup. The keyword limitation IS
disclosed — they are about to push keywords tonight expecting coverage, and
letting them discover that on Monday would be worse than saying it now.

**Traps flagged for tonight (both verified in code):**
- `languages` is **replace-when-provided**, not additive → a language list
  overwrites theirs. This is literally their "half-applies silently" fear.
- Caps: 500 entities, 200 keywords, 20 languages.
- `summary` / `summary_original` now return up to 2000 chars (was 400) — they
  bulk-mirror, so fixed-width columns break.

---

**Subject:** Re: DIPR Monday — backfill answer, and two things to get right tonight

Hi <name>,

Answers below, and two things worth getting right before you push tonight.

**1. Backfill — yes for entities, and no job needed.**

When you add an **entity**, its history comes with it automatically. Scope is a
filter over coverage we already hold, not an instruction to start collecting, and
entity mentions are tagged across the archive — including articles published long
before the entity was added. We checked this again today rather than tell you from
memory: entities added on 3 June carry tagged articles going back to 22 April.

So for entities: nothing to run, and DIPR's first report has the full press
picture, not three days of it.

**If you name an entity we don't already track**, we add it and tag it back across
the archive for you. That is the controlled backfill you're asking about — it's on
us, it's usually quick, and it's the reason to send us the list.

**One important caveat, and it's the reason I'm writing at length.**

**Keywords are not the way to get this.** Today a keyword is a much weaker
instrument than the name suggests — it does not widen the set of articles you
receive. Your entities are doing that work. Concretely: over the last 30 days there
are 321 articles mentioning Kaleshwaram; you're receiving 226 of them, and you're
receiving them because those articles also name one of your six politicians — not
because "kaleshwaram" is in your keyword list. The other 95 don't reach you.

We're fixing that, and I'd rather tell you now than have you find it next week.

**What this means for tonight:** send the analyst team's list through as
**entities** wherever the term is a person, party, organisation, scheme or place.
Anything we already know resolves immediately with its history; anything we don't,
we add and tag back. Keep keywords for genuinely peripheral terms. If you'd rather
just send us the whole list, we'll tell you which are which before you push.

**2. Your name-format question — you're right, and here are the exact answers.**

I ran your list against our dictionary rather than answer from memory.

**Send plain names, no titles.** We match on the exact name, so the titles would
indeed cost you three entities you already have — including the Chief Minister:

| what you'd send | result |
|---|---|
| `Chief Minister A. Revanth Reddy` | ✗ falls through |
| `Revanth Reddy` | ✓ |
| `Deputy Chief Minister Mallu Bhatti Vikramarka` | ✗ falls through |
| `Mallu Bhatti Vikramarka` | ✓ |

**Initials are fine — keep them.** `T. Harish Rao`, `N. Ramchander Rao` and
`G. Kishan Reddy` all resolve as written.

**On the dashes: the dash isn't the problem — the ` – Telangana` suffix is.**
Both the long dash and a plain hyphen fail. Send `Indian National Congress` and
`Bharatiya Janata Party` on their own and they resolve.

**Your 19, checked:**

- **Resolve exactly as written (6):** Government of Telangana, N. Ramchander Rao,
  G. Kishan Reddy, All India Majlis-e-Ittehadul Muslimeen, Asaduddin Owaisi,
  Kalvakuntla Kavitha — plus your existing six.
- **Resolve once the ` – Telangana` suffix comes off (2):** INC, BJP.
- **We need to add these five (we'll do it):** Telangana Council of Ministers;
  Department of Information and Public Relations (Telangana); Telangana Jagruthi;
  Telangana Rajyadhikara Party; Teenmaar Mallanna.

So **14 of your 19 land tonight with their archive attached**, and we already know
the five to add — no need to wait for the patch response and send them back to us.
We'll have them in and retro-tagged; tell us if the naming should differ.

**One note on the keyword and language half of the list.** Right now those two are
much weaker instruments than they sound — your entities are what actually drive the
articles you receive. Concretely: over the last 30 days there are 321 articles
mentioning Kaleshwaram and you're receiving 226 — because those name one of your
politicians, not because "kaleshwaram" is in your keyword list. So please put
anything you genuinely want tracked through as an **entity**, not a keyword. We're
improving the keyword side and I'd rather tell you now than have you find it later.

**3. Confirming the patch — you can see it yourself, and we'll check it too.**

The PATCH response already tells you exactly what happened to each name:

- `resolved_entities` — the names we matched, each with its `entity_id`
- `added_as_keywords` — the names we did **not** recognise

Anything landing in `added_as_keywords` is a name to send us. Given the point
above, that list is the one to read carefully tonight — send it over and we'll add
and retro-tag them.

Two things that will bite silently if you don't know them:

- **`languages` replaces your list, it doesn't add to it.** If you send a language
  list, whatever you send becomes the whole list. This is exactly the kind of
  half-apply you're worried about.
- Ceilings are 500 entities, 200 keywords, 20 languages.

We'll verify the whole thing term by term the same night you push. Send a note when
it's in.

**3. Weekend watch.** Coming back to you separately today — I'd rather confirm the
cover than promise it.

**4. Sandbox key.** Sending it in a separate message now.

**One heads-up on the data itself:** `summary` and `summary_original` now return up
to 2000 characters, where they were previously capped at 400 — and English coverage
on non-English sources is significantly better as of today, which should show up
directly in the DIPR brief. **If you're mirroring into fixed-width columns, check
the width before Monday** — of everything here, that's the one that could break an
existing integration.

Happy to get on a call before the 19th if it's easier.

Best,
<name>
