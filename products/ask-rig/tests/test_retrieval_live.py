"""Live integration test — skipped unless ASKRIG_DB_URL is set AND LaBSE installed.

Requires an SSH tunnel to the read-only corpus DB (scripts/tunnel.ps1).
Run: pytest -m integration
"""
import os

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.skipif(not os.environ.get("ASKRIG_DB_URL"), reason="no ASKRIG_DB_URL / tunnel")
async def test_hybrid_search_returns_ranked_docs():
    from app.config import load_settings
    from app.db import connect
    from app.embedding import LabseEmbedder
    from app.retrieval import hybrid_search

    settings = load_settings()
    query = "Telangana farmer loan waiver"
    qvec = LabseEmbedder(settings.embed_model).embed(query)
    async with connect(settings) as conn:
        docs = await hybrid_search(conn, settings, query, qvec, None, 8)

    assert len(docs) > 0
    scores = [d.score for d in docs]
    assert scores == sorted(scores, reverse=True)  # ranked
