"""Unit tests for the keyword-search verifier's judgment logic.

The verifier decides PASS/FAIL/SUSPECT for live collector output. Those metrics
and verdicts are pure functions (no network), so we pin them down here — a live
"PASS" is only trustworthy if the assessment logic is itself correct. Also
covers the Reddit -> social_posts normalizer.

    pytest backend/tests/test_keyword_verifier.py -v
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.collectors.cheap_stack.keyword_search import (
    KeywordSearchResult,
    _ddg_ig_to_post,
    _parse_telegram,
    _wechat_parse,
    _wx_post_id,
    _reddit_row_to_social_post,
    _tg_views_to_int,
    _tiktok_vid_to_social_post,
    _twitter_row_to_social_post,
    _yt_int,
    _yt_relative_to_iso,
    _yt_renderer_to_social_post,
)
from backend.collectors.cheap_stack.verify_keyword_collectors import (
    assess,
    verdict,
)


def _post(**over):
    """A well-formed normalized social post; override fields per test."""
    base = {
        "platform": "reddit",
        "platform_post_id": "abc123",
        "author_username": "someone",
        "post_text": "Rafale jets arrive in India",
        "post_url": "https://reddit.com/r/india/comments/abc123/x",
        "upvotes": 10,
        "comment_count": 3,
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "subreddit": "india",
        "has_media": False,
    }
    base.update(over)
    return base


# ── normalizer ─────────────────────────────────────────────────────────────

def test_normalizer_renames_comments_and_stamps_keyword():
    raw = {
        "platform_post_id": "p1", "author_username": "u", "post_text": "hi",
        "post_url": "https://reddit.com/x", "upvotes": 5, "comments": 7,
        "posted_at": "2026-07-01T00:00:00+00:00", "has_media": True,
        "raw": {"subreddit": "worldnews"},
    }
    out = _reddit_row_to_social_post(raw, "Modi")
    assert out["comment_count"] == 7          # renamed from `comments`
    assert "comments" not in out
    assert out["matched_keyword"] == "Modi"   # provenance stamped
    assert out["subreddit"] == "worldnews"
    assert out["platform"] == "reddit"


def test_normalizer_coerces_missing_numbers_to_zero():
    out = _reddit_row_to_social_post({"platform_post_id": "p"}, "q")
    assert out["upvotes"] == 0 and out["comment_count"] == 0
    assert isinstance(out["upvotes"], int)


def test_reddit_normalizer_surfaces_enriched_fields():
    raw = {
        "platform_post_id": "p1", "post_url": "https://reddit.com/r/x/comments/p1/",
        "comments": 2, "media_urls": ["https://v.redd.it/abc/DASH_720.mp4"],
        "raw": {
            "subreddit": "x", "external_url": "https://news.example.com/story",
            "domain": "news.example.com", "over_18": True,
            "subreddit_subscribers": 14568, "author_fullname": "t2_abc",
            "upvote_ratio": 0.91, "is_video": True,
        },
    }
    out = _reddit_row_to_social_post(raw, "q")
    assert out["external_url"] == "https://news.example.com/story"
    assert out["domain"] == "news.example.com"
    assert out["over_18"] is True
    assert out["subreddit_subscribers"] == 14568
    assert out["author_fullname"] == "t2_abc"
    assert out["media_urls"] == ["https://v.redd.it/abc/DASH_720.mp4"]


def test_reddit_normalizer_hides_selfpost_url_as_external():
    # self-posts report domain "self.<sub>" and url == permalink but WITH a www.
    # our permalink lacks — equality alone misses it, so domain must gate it out.
    raw = {"platform_post_id": "p1",
           "post_url": "https://reddit.com/r/x/comments/p1/",
           "raw": {"external_url": "https://www.reddit.com/r/x/comments/p1/",
                   "domain": "self.x"}}
    out = _reddit_row_to_social_post(raw, "q")
    assert out["external_url"] == ""


def test_reddit_normalizer_keeps_genuine_outbound_link():
    raw = {"platform_post_id": "p1", "post_url": "https://reddit.com/r/x/comments/p1/",
           "raw": {"external_url": "https://bbc.com/news/story", "domain": "bbc.com"}}
    out = _reddit_row_to_social_post(raw, "q")
    assert out["external_url"] == "https://bbc.com/news/story"


def test_tiktok_normalizer_keeps_video_media():
    v = {
        "video_id": "777", "author": {"unique_id": "creator"},
        "title": "Rafale low pass", "digg_count": 100, "comment_count": 5,
        "play_count": 9000, "create_time": 1777199729, "duration": 50,
        "play": "https://cdn.tiktok/play.mp4", "cover": "https://cdn.tiktok/cover.jpg",
        "region": "FR", "share_count": 12,
    }
    out = _tiktok_vid_to_social_post(v, "Rafale")
    assert out["media_url"] == "https://cdn.tiktok/play.mp4"
    assert out["thumbnail"] == "https://cdn.tiktok/cover.jpg"
    assert out["duration"] == 50 and out["region"] == "FR"
    assert out["upvotes"] == 100 and out["views"] == 9000
    assert out["post_url"] == "https://www.tiktok.com/@creator/video/777"


def test_tiktok_normalizer_skips_video_without_id():
    assert _tiktok_vid_to_social_post({"title": "no id"}, "q") is None


# ── YouTube parsers ─────────────────────────────────────────────────────────

def test_yt_int_parses_view_count():
    assert _yt_int("5,002,904 views") == 5002904
    assert _yt_int(None) == 0
    assert _yt_int("No views") == 0


def test_yt_relative_time_is_approximate_iso_and_recent_for_recent():
    from datetime import datetime, timezone
    iso = _yt_relative_to_iso("3 days ago")
    dt = datetime.fromisoformat(iso)
    delta_days = (datetime.now(timezone.utc) - dt).days
    assert 2 <= delta_days <= 4          # ~3 days back
    assert _yt_relative_to_iso("") == ""
    assert _yt_relative_to_iso("just now") == ""   # unparseable -> empty, not faked


def test_yt_renderer_normalizes_and_keeps_snippet():
    vr = {
        "videoId": "abc123",
        "title": {"runs": [{"text": "Dassault Rafale in Action"}]},
        "detailedMetadataSnippets": [
            {"snippetText": {"runs": [{"text": "French fighter jet Rafale demo"}]}}],
        "ownerText": {"runs": [{"text": "Haci Productions"}]},
        "viewCountText": {"simpleText": "5,002,904 views"},
        "publishedTimeText": {"simpleText": "7 years ago"},
        "lengthText": {"simpleText": "4:16"},
        "thumbnail": {"thumbnails": [{"url": "https://i.ytimg.com/vi/abc123/hq.jpg"}]},
    }
    out = _yt_renderer_to_social_post(vr, "Rafale")
    assert out["platform_post_id"] == "abc123"
    assert out["post_url"] == "https://www.youtube.com/watch?v=abc123"
    assert out["author_username"] == "Haci Productions"
    assert out["views"] == 5002904
    assert out["duration"] == "4:16"
    assert "Rafale" in out["post_text"]
    assert out["published_text"] == "7 years ago"   # raw label preserved
    assert out["upvotes"] == 0 and out["comment_count"] == 0   # not available from search


def test_yt_renderer_skips_without_video_id():
    assert _yt_renderer_to_social_post({"title": {"runs": [{"text": "x"}]}}, "q") is None


def test_yt_channel_id_and_verified_extracted():
    vr = {
        "videoId": "v", "title": {"runs": [{"text": "t"}]},
        "ownerText": {"runs": [{"text": "Zee News", "navigationEndpoint":
                     {"browseEndpoint": {"browseId": "UCzee123"}}}]},
        "ownerBadges": [{"metadataBadgeRenderer":
                        {"style": "BADGE_STYLE_TYPE_VERIFIED", "tooltip": "Verified"}}],
    }
    out = _yt_renderer_to_social_post(vr, "q")
    assert out["channel_id"] == "UCzee123"     # bridges into RSS discovery
    assert out["verified"] is True


def test_yt_missing_channel_id_and_badge_safe():
    vr = {"videoId": "v", "title": {"runs": [{"text": "t"}]},
          "ownerText": {"runs": [{"text": "no-nav"}]}}
    out = _yt_renderer_to_social_post(vr, "q")
    assert out["channel_id"] == "" and out["verified"] is False


# ── Twitter normalizer ──────────────────────────────────────────────────────

def test_twitter_normalizer_maps_engagement_and_enrichment():
    row = {
        "platform_post_id": "1234", "author_username": "etvtelangana",
        "post_text": "Telangana phone tapping case update",
        "post_url": "https://x.com/etvtelangana/status/1234",
        "posted_at": "2026-07-07T07:44:23+00:00",
        "likes": 12, "comments": 3, "shares": 7,
        "media_urls": ["https://pbs.twimg.com/x.jpg"],
        "raw": {"view_count": 9000, "lang": "te", "is_retweet": False, "is_reply": True},
    }
    out = _twitter_row_to_social_post(row, "Telangana")
    assert out["platform"] == "twitter"
    assert out["upvotes"] == 12 and out["comment_count"] == 3   # likes/replies
    assert out["shares"] == 7 and out["views"] == 9000
    assert out["lang"] == "te" and out["is_reply"] is True
    assert out["matched_keyword"] == "Telangana"


def test_twitter_normalizer_coerces_missing_counts():
    out = _twitter_row_to_social_post({"platform_post_id": "1"}, "q")
    assert out["upvotes"] == 0 and out["comment_count"] == 0 and out["views"] == 0
    assert isinstance(out["shares"], int)


# ── Telegram parser ─────────────────────────────────────────────────────────

def test_tg_views_to_int():
    assert _tg_views_to_int("12.3K") == 12300
    assert _tg_views_to_int("3.4M") == 3_400_000
    assert _tg_views_to_int("512") == 512
    assert _tg_views_to_int(None) == 0 and _tg_views_to_int("n/a") == 0


_TG_HTML = (
    'data-post="rybar/12345" class="x">'
    '<div class="tgme_widget_message_text js-message_text">'
    'PLA Navy conducted a drill near <b>Taiwan</b></div>'
    '<a class="tgme_widget_message_date"><time datetime="2026-07-08T10:00:00+00:00">'
    '</time></a><span class="tgme_widget_message_views">12.3K</span>'
    'data-post="rybar/12346" class="x">'
    '<div class="tgme_widget_message_text js-message_text">unrelated football post</div>'
    '<time datetime="2026-07-08T09:00:00+00:00"></time>'
)


def test_parse_telegram_filters_and_extracts():
    posts = _parse_telegram(_TG_HTML, "rybar", "PLA Navy")
    assert len(posts) == 1                       # football post filtered out
    p = posts[0]
    assert p["platform_post_id"] == "rybar/12345"
    assert p["post_url"] == "https://t.me/rybar/12345"
    assert "Taiwan" in p["post_text"] and "<b>" not in p["post_text"]
    assert p["views"] == 12300
    assert p["channel"] == "rybar" and p["platform"] == "telegram"


def test_parse_telegram_empty_when_no_match():
    assert _parse_telegram(_TG_HTML, "rybar", "Zimbabwe") == []


_TG_LINK_HTML = (
    'data-post="theprintindia/26382" class="x">'
    '<div class="tgme_widget_message_text js-message_text">'
    'New promo video by PLA Navy teaser '
    '<a href="https://youtu.be/CWkY9fk2gbM">Watch</a> also http://example.com/report'
    ' and internal <a href="https://t.me/theprintindia/1">link</a>'
    ' <a href="?q=%23EyeOnChina">#EyeOnChina</a>'          # relative -> drop
    ' <a href="https://ko-fi.com/ddgeo">donate</a></div>'  # promo -> drop
    '<a class="tgme_widget_message_photo_wrap" '
    "style=\"background-image:url('https://cdn.tg/photo123.jpg')\"></a>"
    '<time datetime="2026-05-01T08:32:41+00:00"></time>'
)


# ── Instagram (DDG search-index) parser ──────────────────────────────────────

def test_ig_parses_meta_snippet():
    # Instagram's indexed og:description carries author/likes/comments/date
    post = _ddg_ig_to_post(
        "https://www.instagram.com/p/DaeaZDwj3PB/",
        '4 likes, 2 comments - cctv on July 6, 2026: "The Chinese PLA Navy drill"',
        "PLA Navy",
    )
    assert post["platform"] == "instagram"
    assert post["platform_post_id"] == "DaeaZDwj3PB"
    assert post["author_username"] == "cctv"
    assert post["upvotes"] == 4 and post["comment_count"] == 2
    assert post["posted_at"].startswith("2026-07-06")
    assert post["post_text"] == "The Chinese PLA Navy drill"   # prefix stripped


def test_ig_meta_with_km_suffix_counts():
    post = _ddg_ig_to_post(
        "https://www.instagram.com/p/ABC123/",
        '64K likes, 1.2M comments - indiannavy on November 30, 2025: "Fleet review"',
        "Indian Navy",
    )
    assert post["upvotes"] == 64000 and post["comment_count"] == 1_200_000
    assert post["author_username"] == "indiannavy"
    assert post["post_text"] == "Fleet review"


def test_ig_plain_snippet_without_meta():
    post = _ddg_ig_to_post(
        "https://www.instagram.com/reel/DP6HFT2jM6I/",
        "The Chinese PLA Navy's 83rd taskforce arrived in Thailand",
        "PLA Navy",
    )
    assert post["platform_post_id"] == "DP6HFT2jM6I"
    assert post["upvotes"] == 0 and post["comment_count"] == 0   # unknown
    assert "83rd taskforce" in post["post_text"]
    assert post["post_url"] == "https://www.instagram.com/p/DP6HFT2jM6I/"


def test_ig_non_ig_url_is_none():
    assert _ddg_ig_to_post("https://example.com/x", "snippet", "q") is None


# ── WeChat parser ────────────────────────────────────────────────────────────

_WX_HTML = (
    '<meta property="og:title" content="India Navy commissions new frigate" />'
    '<a id="js_name">DefenseObserver</a>'
    '<script>var ct = "1766394466";</script>'
    '<div class="rich_media_content" id="js_content" style="visibility:hidden">'
    '<p>The Indian Navy commissioned INS Mahendragiri today.</p>'
    '<section>A Project 17A stealth frigate.</section></div>'
    '<script>more</script>'
)


def test_wechat_parse_extracts_fields():
    p = _wechat_parse("https://mp.weixin.qq.com/s/AbC123", _WX_HTML, "India Navy")
    assert p["platform"] == "wechat"
    assert p["platform_post_id"] == "wx_AbC123"
    assert p["title"] == "India Navy commissions new frigate"
    assert p["account"] == "DefenseObserver"
    assert p["posted_at"].startswith("2025-12-")           # from var ct
    assert "Mahendragiri" in p["content"] and "stealth frigate" in p["content"]
    assert "<" not in p["content"]                          # tags stripped


def test_wx_post_id_from_biz_url():
    pid = _wx_post_id("https://mp.weixin.qq.com/s?__biz=MzI3&mid=224761&idx=2")
    assert pid == "wx_224761_2"


def test_wechat_parse_empty_html_is_none():
    assert _wechat_parse("https://mp.weixin.qq.com/s/x", "<html></html>", "q") is None


def test_parse_telegram_extracts_links_and_media():
    posts = _parse_telegram(_TG_LINK_HTML, "theprintindia", "PLA Navy")
    assert len(posts) == 1
    p = posts[0]
    # outbound links captured, telegram-internal link excluded
    assert "https://youtu.be/CWkY9fk2gbM" in p["external_urls"]
    assert "http://example.com/report" in p["external_urls"]
    assert all("t.me/" not in u for u in p["external_urls"])
    assert all("ko-fi" not in u for u in p["external_urls"])       # promo dropped
    assert all(u.startswith("http") for u in p["external_urls"])   # no relative ?q=
    assert p["external_url"] == "https://youtu.be/CWkY9fk2gbM"     # first real link
    # photo media captured
    assert p["media_urls"] == ["https://cdn.tg/photo123.jpg"]
    assert p["has_media"] is True


# ── quality metrics ────────────────────────────────────────────────────────

def test_assess_perfect_batch():
    posts = tuple(_post(platform_post_id=f"id{i}") for i in range(5))
    q = assess("Rafale", posts)
    assert q.total == 5
    assert q.shape_ok == 5
    assert q.dup_ids == 0
    assert q.kw_any == 5 and q.kw_any_rate == 1.0
    assert q.ts_ok == 5 and q.url_ok == 5


def test_assess_detects_duplicate_ids():
    posts = (_post(platform_post_id="dup"), _post(platform_post_id="dup"),
             _post(platform_post_id="uniq"))
    q = assess("Rafale", posts)
    assert q.dup_ids == 1        # 3 rows, 2 distinct -> 1 duplicate


def test_assess_keyword_match_rate_partial():
    posts = (_post(post_text="Rafale deal signed", subreddit="news"),
             _post(post_text="unrelated football chatter", subreddit="soccer"))
    q = assess("Rafale", posts)
    assert q.kw_any == 1
    assert q.kw_any_rate == 0.5


def test_assess_keyword_matches_via_subreddit():
    # token absent from text but present in subreddit name still counts
    posts = (_post(post_text="no mention here", subreddit="Tridel"),)
    q = assess("Tridel", posts)
    assert q.kw_any == 1


def test_assess_all_tokens_multiword():
    posts = (_post(post_text="India signed the Rafale deal"),
             _post(post_text="India only, no jet"))
    q = assess("India Rafale", posts)
    assert q.kw_all == 1        # only first row has BOTH tokens
    assert q.kw_any == 2        # both have >=1


def test_assess_flags_bad_shape_and_types():
    bad = _post(platform_post_id="")           # empty id -> invalid shape
    bad2 = _post(upvotes="10")                  # str not int -> invalid shape
    q = assess("Rafale", (bad, bad2, _post()))
    assert q.shape_ok == 1


def test_assess_rejects_epoch_and_future_timestamps():
    posts = (_post(posted_at="1970-01-01T00:00:00+00:00"),
             _post(posted_at="2099-01-01T00:00:00+00:00"),
             _post(posted_at="not-a-date"),
             _post())  # valid
    q = assess("Rafale", posts)
    assert q.ts_ok == 1


def test_assess_counts_empty_text():
    q = assess("Rafale", (_post(post_text="   "), _post()))
    assert q.empty_text == 1


# ── verdict ────────────────────────────────────────────────────────────────

def _ok_result(posts):
    return KeywordSearchResult(platform="reddit", method="m", query="Rafale",
                               ok=True, posts=posts)


def test_verdict_fail_when_not_ok():
    r = KeywordSearchResult(platform="reddit", method="m", query="q", ok=False,
                            error="no cookie")
    tag, reason = verdict(r, assess("q", ()))
    assert tag == "FAIL" and "no cookie" in reason


def test_verdict_suspect_on_zero_rows_healthy_session():
    r = _ok_result(())
    tag, _ = verdict(r, assess("Rafale", ()))
    assert tag == "SUSPECT"


def test_verdict_limit_on_zero_with_declared_note():
    r = KeywordSearchResult(platform="telegram", method="m", query="q", ok=True,
                            posts=(), note="within 12-channel set only")
    tag, reason = verdict(r, assess("q", ()))
    assert tag == "LIMIT" and "channel" in reason


def test_verdict_pass_on_clean_batch():
    posts = tuple(_post(platform_post_id=f"id{i}") for i in range(4))
    tag, _ = verdict(_ok_result(posts), assess("Rafale", posts))
    assert tag == "PASS"


def test_verdict_suspect_on_duplicates():
    posts = (_post(platform_post_id="d"), _post(platform_post_id="d"))
    tag, reason = verdict(_ok_result(posts), assess("Rafale", posts))
    assert tag == "SUSPECT" and "dup" in reason


def test_verdict_suspect_on_low_keyword_match():
    posts = tuple(_post(platform_post_id=f"id{i}", post_text="off topic",
                        subreddit="random") for i in range(4))
    tag, reason = verdict(_ok_result(posts), assess("Rafale", posts))
    assert tag == "SUSPECT" and "kw-match" in reason


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
