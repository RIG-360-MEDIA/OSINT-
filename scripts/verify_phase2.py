"""
Phase 2 end-to-end verification:
  1. /api/documents/feed returns docs ordered by relevance with new fields
  2. /debug/govt-collection-health returns recent runs + source health
  3. analyst RAG includes govt docs in context
"""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user
from backend.database import get_db
from backend.main import app


async def get_demo_user_id() -> str:
    async with get_db() as db:
        row = (
            await db.execute(
                text("SELECT id::text AS id FROM users WHERE email = 'pranavpuri03@gmail.com' LIMIT 1")
            )
        ).fetchone()
        return row.id


def run() -> None:
    user_id = asyncio.run(get_demo_user_id())
    print(f"demo user_id = {user_id}\n")

    app.dependency_overrides[get_current_user] = lambda: {"id": user_id, "email": "pranavpuri03@gmail.com"}
    client = TestClient(app)

    # 1. FEED
    print("=== /api/documents/feed?limit=5 ===")
    r = client.get("/api/documents/feed?limit=5")
    print(f"status: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        print(f"total docs: {d['total']} | returned: {len(d['documents'])}")
        for doc in d["documents"]:
            score = doc.get("score_final")
            tier = doc.get("relevance_tier")
            urg = doc.get("urgency")
            why = (doc.get("why_it_matters") or "—")[:60]
            print(f"  T{tier} {score if score is not None else 'NULL':<5} {urg or '-':<6} {doc['title'][:35]:<35} | why: {why}")
    print()

    # 2. DEBUG ENDPOINT
    print("=== /debug/govt-collection-health ===")
    r = client.get("/debug/govt-collection-health")
    print(f"status: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        print(f"sources: {len(d['sources'])}")
        for s in d["sources"]:
            print(f"  · {s['name']:<28} health={s['health_score']} fails={s['consecutive_failures']} active={s['is_active']}")
        print(f"recent_runs: {len(d['recent_runs'])}")
        for run in d["recent_runs"][:3]:
            dur = run.get("duration_seconds")
            print(f"  · {run['source']:<28} {run['status']:<10} ud={run.get('urls_discovered')} di={run.get('docs_inserted')} dur={dur}")
    print()

    # 3. ANALYST endpoint with a govt-docs-leaning query
    print("=== /api/analyst/query (Telangana govt order) ===")
    r = client.post("/api/analyst/query", json={"question": "What recent Telangana government orders are there?", "mode": "SITUATION"})
    print(f"status: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        # Various schemas — print known keys
        keys = list(d.keys())
        print(f"response keys: {keys}")
        govt_count = d.get("govt_doc_count", 0)
        article_count = d.get("article_count", 0)
        print(f"  articles: {article_count} | govt_docs: {govt_count}")
        if "answer" in d:
            print(f"  answer (first 250 chars): {d['answer'][:250]}")
        elif "response" in d:
            print(f"  response (first 250 chars): {str(d['response'])[:250]}")
    elif r.status_code in (404, 405):
        print("  (analyst endpoint path may differ — check analyst_router.py)")
    else:
        print(f"  body: {r.text[:300]}")


if __name__ == "__main__":
    run()
