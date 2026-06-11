# 01 — Vision & Product

## What ROBIN-OSINT is
A **private, per-persona political-intelligence desk**. It ingests a flood of
open-source signals — news articles (national + regional, multilingual),
social signals (Reddit/Telegram), live YouTube news + transcripts, and
government PDFs — and turns them into one calm, personalized daily picture for a
single **principal** (a political figure / a government) and their **watchlist**.

It is part of the wider **RIG Surveillance** platform but is its own product
(its own SPA, its own FastAPI service, its own subdomain).

## The core promise
For one decision-maker, answer every morning:
- **What happened** (the day's defining stories, importance-ranked).
- **What it means / what's next** (a written executive brief).
- **Who is under pressure** (threats, attacks, momentum).
- **What the mood is** (supportive / neutral / hostile, by entity, topic, place).
- **Where it's happening** (a real map).
- …and deliver it as a **daily PDF emailed automatically**.

## Why it's different from a generic news app
- **Personalized, not global.** There is no shared feed. Every number and story
  is relative to the signed-in persona's principal, watchlist, region, topics.
  Two teammates legitimately see different screens.
- **Multilingual-first.** The corpus is heavily Telugu/Hindi/English. Everything
  shown in the UI must carry an English rendering (headlines and summaries are
  translated + cached).
- **Editorial integrity / anti-fabrication.** Outputs must be grounded; we do not
  invent stats, quotes, or cross-state developments. Anti-hallucination guards
  exist (e.g. an entity must actually appear in the article body to count).

## The pillars (data sources / sections)
- **Articles / Coverage** — RSS + HTML scraping.
- **Clips** — YouTube transcripts (the "Clip Room").
- **Threads / Signals** — Reddit + Telegram (Twitter/X ingested but hidden in UI).
- **Documents** — government PDFs ("the archive").
- **Brief** — the daily generated digest (Home + the PDF report).
- **Analyst** — per-user RAG over the corpus.

## The product surfaces (ROBIN-OSINT SPA pages)
Home (The Briefing) · War Room (Crisis Desk) · Analytics (Instrument Panel) ·
Dossier (Entity Files) · Map (The Theatre) · Dispatch (Daily Report).
See **04-PAGES-AND-FEATURES.md**.

## Design ethos
"Chrome is silence, data is light." A cinematic, restrained, newsroom-grade UI;
the system should be invisible until it's turned off. Personalisation and
editorial responsibility are treated as the central hard problem, not opposites.
