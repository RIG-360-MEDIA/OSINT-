"""Unit tests for drill-down prompt building (DB-backed get_article is integration)."""
from __future__ import annotations

from datetime import datetime

from app.drilldown import ArticleDetail, build_drilldown_prompt


def _art(**over):
    base = dict(
        id="a1", title="Metro phase II approved", url="https://x.com/a",
        published_at=datetime(2026, 6, 24, 10, 0), language="en", source_id="thehindu",
        body="The cabinet approved phase II at a cost of 38595 crore.", summary="Phase II cleared.",
        quotes=[("Revanth Reddy", "This is a milestone for Hyderabad.")],
    )
    base.update(over)
    return ArticleDetail(**base)


def test_prompt_includes_core_fields():
    p = build_drilldown_prompt(_art())
    assert "Metro phase II approved" in p
    assert "38595 crore" in p           # body present
    assert "Phase II cleared." in p     # summary present
    assert "Revanth Reddy" in p and "milestone" in p  # quote present


def test_prompt_handles_missing_body_and_quotes():
    p = build_drilldown_prompt(_art(body=None, summary=None, quotes=[]))
    assert "Metro phase II approved" in p
    assert "ARTICLE TEXT" not in p and "QUOTES" not in p  # sections omitted cleanly
    assert "Explain this article" in p
