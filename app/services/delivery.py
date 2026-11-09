"""Idempotent delivery of Reddit posts to Discord channels."""
from __future__ import annotations

import logging
from datetime import timedelta, timezone

import discord
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import Delivery, utcnow
from app.reddit.media import RedditPost

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
PENDING_STALE = timedelta(minutes=5)


def build_embed(post: RedditPost) -> discord.Embed:
    """Format a post as a Discord embed."""
    embed = discord.Embed(
        title=post.title[:256], url=post.permalink, color=0xFF4500,
        timestamp=post.created_utc.replace(tzinfo=timezone.utc),
    )
    embed.set_author(name=f"u/{post.author}")
    embed.add_field(name="Subreddit", value=f"r/{post.subreddit}", inline=True)
    embed.add_field(name="Reddit", value=f"[Original post]({post.permalink})", inline=True)
    if post.media_type == "image" and post.image_url:
        embed.set_image(url=post.image_url)
    elif post.media_type == "video" and post.video_url:
        embed.add_field(name="Video", value=post.video_url[:1000], inline=False)
    elif post.media_type == "link" and post.url:
        embed.add_field(name="Link", value=post.url[:1000], inline=False)
    embed.set_footer(text="RedditBridge")
    return embed


async def send_embed(bot: discord.Client, channel_id: int, embed: discord.Embed) -> None:
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    await channel.send(embed=embed)  # type: ignore[union-attr]


async def deliver(bot: discord.Client, sessionmaker: async_sessionmaker[AsyncSession], *,
                  guild_id: int, subscription_id: int, channel_id: int, post: RedditPost) -> str:
    """Claim then send. Returns sent | failed | duplicate | skipped."""
    async with sessionmaker() as s:
        rec = (await s.execute(select(Delivery).where(
            Delivery.subscription_id == subscription_id, Delivery.post_id == post.id))).scalar_one_or_none()
        if rec is None:
            rec = Delivery(guild_id=guild_id, subscription_id=subscription_id, post_id=post.id,
                           status="pending", attempts=0)
            s.add(rec)
            try:
                await s.commit()  # the unique constraint is the duplicate guard
            except IntegrityError:
                await s.rollback()
                return "duplicate"
        else:
            stale = rec.status == "pending" and utcnow() - rec.updated_at > PENDING_STALE
            if not (rec.status == "failed" or stale) or rec.attempts >= MAX_ATTEMPTS:
                return "skipped"

        rec.attempts += 1
        try:
            await send_embed(bot, channel_id, build_embed(post))
            rec.status, rec.error = "sent", None
        except discord.Forbidden:
            rec.status, rec.error = "failed", "Missing permission in channel"
        except discord.NotFound:
            rec.status, rec.error = "failed", "Channel not found (deleted?)"
        except discord.HTTPException as exc:
            rec.status, rec.error = "failed", f"Discord HTTP {exc.status}"
        await s.commit()
        if rec.status == "failed":
            log.warning("delivery failed", extra={"guild_id": guild_id, "post_id": post.id, "error": rec.error})
        return rec.status
