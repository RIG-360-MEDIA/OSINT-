"""
Tests for backend.routers.documents_router.

Covers:
  - GET /api/documents/feed     (filters, pagination, search, auth)
  - GET /api/documents/{id}     (200 / 404)
  - POST /api/documents/{id}/summary (cache, quota, error)

The xfail-marked tests document known P0/P1 bugs from
docs/qa/documents-defects.md. They MUST stay red until those defects
are fixed; once fixed, remove the xfail marker.

Run:
  pytest backend/tests/test_documents_router.py -q
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from backend.database import get_db
from backend.main import app


# ---------- Fixtures ---------------------------------------------------- #

@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers():
    """Override get_current_user to return a deterministic test user."""
    test_user = {"id": str(uuid.uuid4()), "email": "qa@test.local"}

    from backend.auth.auth_middleware import get_current_user

    async def _override():
        return test_user

    app.dependency_overrides[get_current_user] = _override
    yield {"Authorization": "Bearer test-token"}
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def seeded_docs():
    """Seed 50 govt_documents across 4 geographies and 5 doc_types."""
    inserted: list[str] = []
    geos = ["LOCAL", "CENTRAL", "NEIGHBOURING", "INTERNATIONAL"]
    types = ["government_order", "court_order", "audit_report",
             "press_release", "ministry_order"]
    base = datetime.now(timezone.utc) - timedelta(days=5)

    async with get_db() as db:
        for i in range(50):
            doc_id = uuid.uuid4()
            await db.execute(
                text("""
                INSERT INTO govt_documents
                  (id, title, document_url, source_name,
                   source_geography, document_type, full_text,
                   nlp_processed, collected_at, intrinsic_importance)
                VALUES
                  (:id, :title, :url, :src,
                   :geo, :dtype, :ft,
                   TRUE, :ts, :imp)
                """),
                {
                    "id": doc_id,
                    "title": f"QA Test Doc {i}",
                    "url": f"https://example.test/doc/{i}.pdf",
                    "src": f"src-{i % 5}",
                    "geo": geos[i % 4],
                    "dtype": types[i % 5],
                    "ft": f"body of doc {i} contains keyword RBI here",
                    "ts": base + timedelta(minutes=i),
                    "imp": 0.5 + (i % 10) / 20.0,
                },
            )
            inserted.append(str(doc_id))
        await db.commit()
    yield inserted
    async with get_db() as db:
        await db.execute(
            text("DELETE FROM govt_documents WHERE id = ANY(:ids)"),
            {"ids": inserted},
        )
        await db.commit()


# ---------- /feed ------------------------------------------------------- #

@pytest.mark.asyncio
async def test_feed_returns_shape(client, auth_headers, seeded_docs):
    r = await client.get("/api/documents/feed?limit=20", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert {"documents", "has_more", "next_cursor",
            "total", "geography_counts"} <= body.keys()
    assert isinstance(body["documents"], list)
    assert len(body["documents"]) <= 20


@pytest.mark.asyncio
async def test_feed_requires_auth(client):
    # No auth_headers fixture → no override → real dependency runs
    r = await client.get("/api/documents/feed")
    assert r.status_code in (401, 403)


@pytest.mark.parametrize(
    "geo", ["LOCAL", "CENTRAL", "NEIGHBOURING", "INTERNATIONAL"]
)
@pytest.mark.asyncio
async def test_feed_geography_filter(client, auth_headers, seeded_docs, geo):
    r = await client.get(
        f"/api/documents/feed?geography={geo}", headers=auth_headers
    )
    assert r.status_code == 200
    for d in r.json()["documents"]:
        assert d["source_geography"] == geo


@pytest.mark.parametrize(
    "dtype", ["government_order", "court_order", "audit_report",
              "press_release", "ministry_order"]
)
@pytest.mark.asyncio
async def test_feed_doc_type_filter(client, auth_headers, seeded_docs, dtype):
    r = await client.get(
        f"/api/documents/feed?doc_type={dtype}", headers=auth_headers
    )
    assert r.status_code == 200
    for d in r.json()["documents"]:
        assert d["document_type"] == dtype


@pytest.mark.parametrize("term", ["RBI", "rbi", "doc 7", "%", "_", "'"])
@pytest.mark.asyncio
async def test_feed_search_safe(client, auth_headers, seeded_docs, term):
    r = await client.get(
        f"/api/documents/feed?search={term}", headers=auth_headers
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_feed_pagination_no_dups_no_skips(
    client, auth_headers, seeded_docs
):
    seen: set[str] = set()
    cursor = ""
    page = 0
    while True:
        url = f"/api/documents/feed?limit=10&cursor={cursor}"
        r = await client.get(url, headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        for d in body["documents"]:
            assert d["doc_id"] not in seen, (
                f"duplicate {d['doc_id']} on page {page}"
            )
            seen.add(d["doc_id"])
        if not body["has_more"]:
            break
        cursor = body["next_cursor"]
        page += 1
        assert page < 20, "pagination did not terminate"
    # 50 docs were seeded + however many predate the run
    assert len(seen) >= 50


@pytest.mark.asyncio
async def test_feed_can_reach_old_docs_via_cursor(
    client, auth_headers
):
    async with get_db() as db:
        old_id = uuid.uuid4()
        await db.execute(
            text("""
            INSERT INTO govt_documents
              (id, title, document_url, source_name, source_geography,
               document_type, full_text, nlp_processed, collected_at,
               intrinsic_importance)
            VALUES
              (:id, 'ancient', 'https://x/x.pdf', 'src', 'LOCAL',
               'government_order', 'old', TRUE,
               NOW() - INTERVAL '120 days', 0.9)
            """),
            {"id": old_id},
        )
        await db.commit()
    try:
        seen: set[str] = set()
        cursor = ""
        for _ in range(20):
            r = await client.get(
                f"/api/documents/feed?limit=20&cursor={cursor}",
                headers=auth_headers,
            )
            body = r.json()
            for d in body["documents"]:
                seen.add(d["doc_id"])
            if not body["has_more"]:
                break
            cursor = body["next_cursor"]
        assert str(old_id) in seen
    finally:
        async with get_db() as db:
            await db.execute(
                text("DELETE FROM govt_documents WHERE id = :id"),
                {"id": old_id},
            )
            await db.commit()


@pytest.mark.asyncio
async def test_feed_total_matches_filter(client, auth_headers, seeded_docs):
    r = await client.get(
        "/api/documents/feed?geography=LOCAL", headers=auth_headers
    )
    body = r.json()
    # Of 50 seeded, 50/4 ≈ 12-13 are LOCAL
    assert body["total"] <= 20, (
        f"expected filter-aware total ≤20, got {body['total']}"
    )


# ---------- /{doc_id} --------------------------------------------------- #

@pytest.mark.asyncio
async def test_detail_404_on_missing(client, auth_headers):
    fake = str(uuid.uuid4())
    r = await client.get(f"/api/documents/{fake}", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_detail_returns_full_text(client, auth_headers, seeded_docs):
    doc_id = seeded_docs[0]
    r = await client.get(f"/api/documents/{doc_id}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["doc_id"] == doc_id
    assert body["full_text"]


# ---------- /{doc_id}/summary ------------------------------------------ #

@pytest.mark.asyncio
async def test_summary_first_call_writes_cache(
    client, auth_headers, seeded_docs
):
    doc_id = seeded_docs[0]
    with patch(
        "backend.routers.documents_router.call_groq",
        return_value="Cached summary text.",
    ) as m:
        r = await client.post(
            f"/api/documents/{doc_id}/summary", headers=auth_headers
        )
    assert r.status_code == 200
    assert "summary" in r.json()
    m.assert_called_once()


@pytest.mark.asyncio
async def test_summary_quota_exhausted_returns_503(
    client, auth_headers, seeded_docs
):
    from backend.nlp.groq_client import GroqQuotaExhausted

    doc_id = seeded_docs[1]
    with patch(
        "backend.routers.documents_router.call_groq",
        side_effect=GroqQuotaExhausted("rate limit"),
    ):
        r = await client.post(
            f"/api/documents/{doc_id}/summary", headers=auth_headers
        )
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_summary_call_failed_returns_500(
    client, auth_headers, seeded_docs
):
    from backend.nlp.groq_client import GroqCallFailed

    doc_id = seeded_docs[2]
    with patch(
        "backend.routers.documents_router.call_groq",
        side_effect=GroqCallFailed("upstream err"),
    ):
        r = await client.post(
            f"/api/documents/{doc_id}/summary", headers=auth_headers
        )
    assert r.status_code == 500
