"""Pure parsing of Reddit listing JSON into RedditPost objects (no network, no Discord)."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9_]{2,21}$")
_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp")
_VIDEO_HOSTS = ("v.redd.it", "youtube.com", "youtu.be", "streamable.com", "gfycat.com")


@dataclass(frozen=True)
class RedditPost:
    id: str
    subreddit: str
    title: str
    author: str
    permalink: str
    url: str
    created_utc: datetime  # naive UTC
    media_type: str  # image | video | link | text
    over_18: bool
    image_url: str | None = None
    video_url: str | None = None


def normalize_subreddit(raw: str) -> str | None:
    """Return a clean subreddit name or None if invalid. Accepts 'r/name' and '/r/name'."""
    name = raw.strip().lstrip("/")
    if name.lower().startswith("r/"):
        name = name[2:]
    return name if SUBREDDIT_RE.match(name) else None


def parse_post(data: dict[str, Any]) -> RedditPost | None:
    """Convert one listing child's ``data`` dict. Returns None for unusable/removed posts."""
    try:
        post_id = str(data["id"])
        if data.get("removed_by_category") or data.get("author") in (None, "[deleted]"):
            return None
        url = str(data.get("url_overridden_by_dest") or data.get("url") or "")
        lowered = url.lower().split("?")[0]
        host = re.sub(r"^https?://(www\.)?", "", url.lower()).split("/")[0]

        image_url = video_url = None
        if data.get("is_self"):
            media_type = "text"
        elif data.get("post_hint") == "image" or lowered.endswith(_IMAGE_EXT):
            media_type, image_url = "image", url
        elif data.get("is_video") or any(host == h or host.endswith("." + h) for h in _VIDEO_HOSTS):
            media_type, video_url = "video", url
        else:
            media_type = "link"

        return RedditPost(
            id=post_id,
            subreddit=str(data["subreddit"]),
            title=html.unescape(str(data["title"])),
            author=str(data["author"]),
            permalink="https://www.reddit.com" + str(data["permalink"]),
            url=url,
            created_utc=datetime.fromtimestamp(float(data["created_utc"]), tz=timezone.utc).replace(tzinfo=None),
            media_type=media_type,
            over_18=bool(data.get("over_18")),
            image_url=image_url,
            video_url=video_url,
        )
    except (KeyError, TypeError, ValueError):
        return None


def parse_listing(payload: dict[str, Any]) -> list[RedditPost]:
    """Parse a full /r/<sub>/new response, dropping anything unparsable."""
    children = payload.get("data", {}).get("children", [])
    posts = (parse_post(c.get("data", {})) for c in children if isinstance(c, dict))
    return [p for p in posts if p is not None]
