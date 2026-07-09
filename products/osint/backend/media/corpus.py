"""Corpus image cross-check — does this image already live in our article corpus?

Match is by image IDENTITY (perceptual dHash + Hamming distance), NOT by URL: corpus
thumbnails are unique per-article CDN assets, so URL matching finds nothing — the same
wire photo reused across outlets only shows up as a near-duplicate hash. So a recycled
image links straight to the corpus stories that used it.

The hash index (analytics.article_image_hash) grows from use — seed with index_recent().
Read-only on public.articles; writes only its own table in the analytics schema.
"""
from __future__ import annotations

import os
import urllib.request
from typing import Any

import psycopg2

import verify_image as vi

_DB = os.environ.get("MEDIA_DB_URL", "")


def _conn():
    return psycopg2.connect(_DB, connect_timeout=8)


def ensure_schema() -> None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS analytics.article_image_hash(
                   article_id  uuid PRIMARY KEY,
                   dhash       bit(64) NOT NULL,
                   computed_at timestamptz NOT NULL DEFAULT now())"""
        )
        c.commit()


def count() -> int:
    with _conn() as c, c.cursor() as cur:
        cur.execute("SELECT count(*) FROM analytics.article_image_hash")
        return int(cur.fetchone()[0])


def index_recent(limit: int = 500, timeout: int = 8) -> dict[str, Any]:
    """Download + hash the most-recent un-indexed thumbnails. Bounded, best-effort."""
    conn = _conn()
    got = err = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT a.id, a.thumbnail_url
                     FROM public.articles a
                     LEFT JOIN analytics.article_image_hash h ON h.article_id = a.id
                    WHERE h.article_id IS NULL
                      AND a.thumbnail_url IS NOT NULL AND a.thumbnail_url <> ''
                    ORDER BY a.collected_at DESC
                    LIMIT %s""",
                (limit,),
            )
            rows = cur.fetchall()
        for aid, url in rows:
            try:
                req = urllib.request.Request(url, headers=vi._UA)
                data = urllib.request.urlopen(req, timeout=timeout).read()
                dh = vi.dhash_bytes(data)
            except Exception:
                err += 1
                continue
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO analytics.article_image_hash(article_id, dhash) "
                        "VALUES(%s, %s::bit(64)) ON CONFLICT (article_id) DO NOTHING",
                        (aid, dh),
                    )
                conn.commit()
                got += 1
            except Exception:
                conn.rollback()
                err += 1
    finally:
        conn.close()
    return {"candidates": len(rows), "indexed": got, "errors": err}


def match(dhash_str: str, max_dist: int = 6, limit: int = 8) -> list[dict[str, Any]]:
    """Corpus articles whose thumbnail is within `max_dist` bits of the query image."""
    sql = """SELECT a.id, a.title, a.url, a.thumbnail_url, a.published_at,
                    bit_count(h.dhash # %s::bit(64)) AS dist
               FROM analytics.article_image_hash h
               JOIN public.articles a ON a.id = h.article_id
              WHERE bit_count(h.dhash # %s::bit(64)) <= %s
              ORDER BY dist ASC, a.published_at DESC NULLS LAST
              LIMIT %s"""
    with _conn() as c, c.cursor() as cur:
        cur.execute(sql, (dhash_str, dhash_str, max_dist, limit))
        rows = cur.fetchall()
    return [
        {
            "article_id": str(r[0]),
            "title": r[1],
            "url": r[2],
            "thumbnail": r[3],
            "published_at": r[4].isoformat() if r[4] else None,
            "distance": int(r[5]),
        }
        for r in rows
    ]
