"""Reddit API client: official OAuth (app-only), rate-limit aware, with retry/backoff."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.reddit.media import RedditPost, parse_listing

log = logging.getLogger(__name__)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"


class RedditError(Exception):
    """Transient or unexpected Reddit API failure."""


class SubredditNotFound(RedditError):
    pass


class SubredditForbidden(RedditError):
    """Private, banned or quarantined subreddit."""


class RedditClient:
    def __init__(self, client_id: str, client_secret: str, user_agent: str,
                 http: httpx.AsyncClient | None = None, max_retries: int = 3) -> None:
        self._id, self._secret, self._ua = client_id, client_secret, user_agent
        self._http = http or httpx.AsyncClient(timeout=20.0)
        self._max_retries = max_retries
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()
        self.last_ok: float | None = None  # for /status
        self.last_error: str | None = None

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _refresh_token(self) -> None:
        async with self._lock:
            if self._token and time.monotonic() < self._expires_at - 60:
                return
            resp = await self._http.post(
                TOKEN_URL, auth=(self._id, self._secret),
                data={"grant_type": "client_credentials"}, headers={"User-Agent": self._ua},
            )
            if resp.status_code != 200:
                raise RedditError(f"token request failed (HTTP {resp.status_code})")
            body = resp.json()
            self._token = body["access_token"]
            self._expires_at = time.monotonic() + float(body.get("expires_in", 3600))

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        delay = 2.0
        for attempt in range(1, self._max_retries + 1):
            try:
                await self._refresh_token()
                resp = await self._http.get(
                    API_BASE + path, params=params,
                    headers={"Authorization": f"Bearer {self._token}", "User-Agent": self._ua},
                )
            except (httpx.TransportError, RedditError) as exc:
                self.last_error = type(exc).__name__
                if attempt == self._max_retries:
                    raise RedditError(f"request failed: {type(exc).__name__}") from exc
                await asyncio.sleep(delay); delay *= 2
                continue

            if resp.status_code == 200:
                self.last_ok, self.last_error = time.time(), None
                return resp.json()
            if resp.status_code == 401:
                self._token = None  # force refresh and retry
            elif resp.status_code == 404:
                raise SubredditNotFound(path)
            elif resp.status_code in (403, 451):
                raise SubredditForbidden(path)
            elif resp.status_code == 429:
                wait = min(float(resp.headers.get("Retry-After", delay)), 60.0)
                log.warning("reddit rate limited", extra={"retry_after": wait})
                await asyncio.sleep(wait)
                continue
            if attempt == self._max_retries:
                self.last_error = f"HTTP {resp.status_code}"
                raise RedditError(f"HTTP {resp.status_code}")
            await asyncio.sleep(delay); delay *= 2
        raise RedditError("retries exhausted")

    async def subreddit_info(self, name: str) -> dict[str, Any]:
        """Return the subreddit's ``data`` block (over18, subreddit_type, ...)."""
        return (await self._get(f"/r/{name}/about")).get("data", {})

    async def fetch_new(self, name: str, limit: int = 25) -> list[RedditPost]:
        """Newest posts for a subreddit."""
        return parse_listing(await self._get(f"/r/{name}/new", {"limit": limit, "raw_json": 1}))
