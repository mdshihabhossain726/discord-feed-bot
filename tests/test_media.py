from datetime import datetime

from app.reddit.media import normalize_subreddit, parse_listing, parse_post

BASE = {"id": "abc", "subreddit": "aww", "title": "Cat &amp; dog", "author": "bob",
        "permalink": "/r/aww/comments/abc/x/", "created_utc": 1700000000.0, "url": "https://x.com/a"}


def test_normalize_subreddit():
    assert normalize_subreddit("r/aww") == "aww"
    assert normalize_subreddit("/r/Pics") == "Pics"
    assert normalize_subreddit("a") is None
    assert normalize_subreddit("bad name!") is None
    assert normalize_subreddit("x" * 22) is None


def test_image_post_and_title_unescaped():
    p = parse_post({**BASE, "url": "https://i.redd.it/a.JPG?x=1", "post_hint": "image"})
    assert p.media_type == "image" and p.image_url.startswith("https://i.redd.it")
    assert p.title == "Cat & dog"
    assert p.permalink == "https://www.reddit.com/r/aww/comments/abc/x/"
    assert isinstance(p.created_utc, datetime) and p.created_utc.tzinfo is None


def test_video_and_link_and_text():
    assert parse_post({**BASE, "is_video": True, "url": "https://v.redd.it/z"}).media_type == "video"
    assert parse_post({**BASE, "url": "https://youtu.be/q"}).media_type == "video"
    assert parse_post({**BASE}).media_type == "link"
    assert parse_post({**BASE, "is_self": True}).media_type == "text"


def test_nsfw_flag_preserved_and_bad_data_dropped():
    assert parse_post({**BASE, "over_18": True}).over_18 is True
    assert parse_post({"id": "x"}) is None
    assert parse_post({**BASE, "author": "[deleted]"}) is None
    assert parse_post({**BASE, "removed_by_category": "moderator"}) is None


def test_parse_listing_skips_garbage():
    payload = {"data": {"children": [{"data": BASE}, {"data": {"id": "bad"}}, "junk"]}}
    assert [p.id for p in parse_listing(payload)] == ["abc"]
