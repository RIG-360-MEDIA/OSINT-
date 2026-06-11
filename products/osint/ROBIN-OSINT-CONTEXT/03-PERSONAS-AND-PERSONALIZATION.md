# 03 — Personas & Personalization

## How personalization works
Every signed-in user has a row in **`analytics.user_brief_prefs`** (JSONB):
- `primary_subject_id` + `primary_subject_meta.name` — the **principal** (focal entity).
- `watchlist.entity_meta` / `entity_ids` — tracked entities, each with `tier`
  (`extended` = national/neighbour; otherwise core) and metadata.
- `regions.states` — the user's states; **states[0] is the PRIMARY state**.
- `topics.include` / `topics.exclude`, `languages`, `stance`, `personality`, `delivery`.

The backend builds each page's article **universe** from `article_entity_mentions`
where the entity is the principal or on the watchlist (entity merges resolved via
`entity_dictionary.redirected_to`). Stance everywhere uses **POL** (intensity →
supportive/neutral/hostile) gated by **`_BODY_PRESENT`** (the entity must appear
in the article body — anti-hallucination). Helper: `principal_of(prefs)`,
`_primary_state`.

## Known personas (live)
| Persona | Email | Principal | States (states[0] = primary) | user_id |
|---|---|---|---|---|
| **Andhra Pradesh** (primary demo) | `andhrarig360@gmail.com` | Chandrababu Naidu | Andhra Pradesh, Telangana, Karnataka | `7343cb2f-4f13-46f8-aea8-dbdedfa385b5` |
| **Telangana** | `maverick092005+telangana@gmail.com` | Revanth Reddy | Telangana, Andhra Pradesh, Karnataka | `03f93124-eec3-46ac-a41e-829cb663b615` |
| **Super admin** | `pranavsinghpuri09@gmail.com` | — | — | seeded super_admin |

> Passwords are hashed in Supabase and **not retrievable**. Do not attempt to
> read or print them.

## The AP persona in detail (our main working example)
- Principal: **Chandrababu Naidu (TDP)**. Rivals/context: Jagan/YSRCP, Pawan
  Kalyan/Jana Sena, Lokesh, BJP.
- Because **Karnataka** is in `states`, the user also tracks some Karnataka
  figures → off-state (e.g. Karnataka) stories can score high. We added an
  "Andhra-first" rule in Top Stories to keep the primary state on top (see 06).

## Personalization implications a new chat must remember
- "Why does my screen differ from a colleague's?" → persona scoping, by design.
- The RBAC model chosen: **global ingestion + per-user view filtering by entity +
  private personal artifacts** (decision "(a)+(c)").
- Dossier/district endpoints enforce RBAC (403 if outside your watchlist/region).
- Editorial correctness: never fabricate handles/pledges/quotes; LLM outputs need
  cite-ID guardrails; use `article_stances` (not `register_emotion`) for any
  negativity/bias measure — `register_emotion`'s "alarm" is event-emotion, not
  hostility, and skews everything negative.
