"""
THE NEWSROOM Celery task package.

Tasks live on three queues:
  whisper    — CPU/network-heavy ASR + live HLS pulls (concurrency=1)
  nlp        — Cerebras/Groq LLM reconcile / quote / breaking calls
  brief      — daily digest generation

The `ping` task is a Phase-0 smoke test: it proves the whisper worker
boots and routes correctly. Safe to leave in place permanently — it has
no side effects and is useful as an ongoing health probe.
"""
from __future__ import annotations

from backend.celery_app import app


@app.task(name="tasks.newsroom.ping", queue="whisper")
def ping(payload: str = "pong") -> str:
    """No-op smoke test for the whisper queue. Returns whatever it was given."""
    return payload
