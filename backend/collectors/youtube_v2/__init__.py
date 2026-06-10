"""
youtube_v2 — entity-keyed YouTube clip pipeline (greenfield rebuild).

Replaces the monolithic ``youtube_collector.py``. One pipeline, one table,
entity-keyed. English-only + canonical-entity-only, with quality gates that
reject filler / empty / non-English / non-canonical output AT INSERT, never
silently. Every fallback path is observable (metric + WARNING).

Topology (see docs/sessions/youtube-rebuild-kickoff.md):
  - discovery.py   runs on Hetzner (RSS, cheap, safe)
  - transcript.py  runs on a RESIDENTIAL worker (YouTube blocks datacenter IPs)
  - extraction.py  runs on Hetzner (Groq), storage.py writes clips + embeddings

Small typed modules; immutable dataclasses; tests-first.
"""
