"""Background polling loop: fetch each due subreddit once, deliver to every subscribed server."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import discord
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import GuildSettings, Subscription, utcnow
from app.reddit.client import RedditClient, RedditError, SubredditForbidden, SubredditNotFound
from app.services.delivery import deliver

log = logging.getLogger(__name__)


@dataclass
class _Due:
    sub_id: int
    guild_id: int
    subreddit: str
    channel_id: int
    created_at: object


class Scheduler:
    def __init__(self, bot: discord.Client, sessionmaker: async_sessionmaker[AsyncSession],
                 reddit: RedditClient, tick_seconds: int = 30) -> None:
        self.bot, self.sm, self.reddit, self.tick = bot, sessionmaker, reddit, tick_seconds
        self._task: asyncio.Task[None] | None = None
        self.last_run = None
        self.sent = 0
        self.failed = 0

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="reddit-scheduler")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        await self.bot.wait_until_ready()
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("scheduler iteration failed")
            await asyncio.sleep(self.tick)

    async def _collect_due(self) -> dict[str, list[_Due]]:
        now = utcnow()
        async with self.sm() as s:
            rows = (await s.execute(
                select(Subscription, GuildSettings)
                .join(GuildSettings, GuildSettings.guild_id == Subscription.guild_id)
                .where(Subscription.enabled.is_(True), GuildSettings.paused.is_(False)))).all()
        by_name: dict[str, list[_Due]] = {}
        for sub, g in rows:
            channel = sub.channel_id or g.channel_id
            if not channel:
                continue
            gap = (now - sub.last_checked_at).total_seconds() if sub.last_checked_at else None
            if gap is None or gap >= g.interval_minutes * 60:
                by_name.setdefault(sub.subreddit.lower(), []).append(
                    _Due(sub.id, sub.guild_id, sub.subreddit, channel, sub.created_at))
        return by_name

    async def run_once(self) -> None:
        self.last_run = utcnow()
        for name, subs in (await self._collect_due()).items():
            try:
                posts = await self.reddit.fetch_new(name)
            except (SubredditNotFound, SubredditForbidden) as exc:
                await self._set_error(name, f"{type(exc).__name__}: subreddit unavailable")
                continue
            except RedditError as exc:
                log.warning("reddit fetch failed", extra={"subreddit": name, "error": str(exc)})
                continue
            for due in subs:
                # Only posts created after the subscription was added (no backfill flood).
                for post in sorted(posts, key=lambda p: p.created_utc):
                    if post.over_18 or post.created_utc < due.created_at:  # type: ignore[operator]
                        continue
                    status = await deliver(self.bot, self.sm, guild_id=due.guild_id,
                                           subscription_id=due.sub_id, channel_id=due.channel_id, post=post)
                    self.sent += status == "sent"
                    self.failed += status == "failed"
                async with self.sm() as s:
                    await s.execute(update(Subscription).where(Subscription.id == due.sub_id)
                                    .values(last_checked_at=utcnow(), last_error=None))
                    await s.commit()
            await asyncio.sleep(1)  # be gentle with the Reddit API

    async def _set_error(self, name: str, message: str) -> None:
        async with self.sm() as s:
            await s.execute(update(Subscription).where(Subscription.subreddit.ilike(name))
                            .values(last_checked_at=utcnow(), last_error=message[:255]))
            await s.commit()
