"""Slash commands. Admin commands require Manage Server (enforced server-side)."""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Delivery, GuildSettings, Subscription, utcnow
from app.reddit.client import RedditError, SubredditForbidden, SubredditNotFound
from app.reddit.media import RedditPost, normalize_subreddit
from app.services.delivery import build_embed, send_embed

if TYPE_CHECKING:
    from app.bot.client import RedditBridgeBot

REQUIRED = ("view_channel", "send_messages", "embed_links")
INTERVALS = [5, 10, 15, 30, 60]


def admin_only(func_):
    """Guild-only + server-side Manage Server check (default_permissions alone is overridable)."""
    func_ = app_commands.checks.has_permissions(manage_guild=True)(func_)
    func_ = app_commands.default_permissions(manage_guild=True)(func_)
    return app_commands.guild_only()(func_)


def missing_perms(channel: discord.abc.GuildChannel, me: discord.Member) -> list[str]:
    perms = channel.permissions_for(me)
    return [p for p in REQUIRED if not getattr(perms, p)]


class FeedCommands(commands.Cog):
    def __init__(self, bot: "RedditBridgeBot") -> None:
        self.bot = bot

    async def _guild(self, s: AsyncSession, guild_id: int) -> GuildSettings:
        g = await s.get(GuildSettings, guild_id)
        if g is None:
            g = GuildSettings(guild_id=guild_id)
            s.add(g)
            await s.flush()
        return g

    async def _check_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> bool:
        missing = missing_perms(channel, interaction.guild.me)  # type: ignore[union-attr]
        if missing:
            await interaction.response.send_message(
                f"I'm missing these permissions in {channel.mention}: `{', '.join(missing)}`.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="setup", description="Set up RedditBridge for this server")
    @app_commands.describe(channel="Channel where Reddit posts will be sent")
    @admin_only
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not await self._check_channel(interaction, channel):
            return
        async with self.bot.sessionmaker() as s:
            (await self._guild(s, interaction.guild_id)).channel_id = channel.id  # type: ignore[arg-type]
            await s.commit()
        await interaction.response.send_message(
            f"✅ Done! Posts will go to {channel.mention}. Add feeds with `/addsubreddit`, "
            f"or check delivery with `/testfeed`.", ephemeral=True)

    @app_commands.command(name="setchannel", description="Change the default notification channel")
    @app_commands.describe(channel="New default channel")
    @admin_only
    async def setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self.setup.callback(self, interaction, channel)  # type: ignore[attr-defined]

    @app_commands.command(name="addsubreddit", description="Subscribe to a subreddit")
    @app_commands.describe(subreddit="e.g. aww or r/aww", channel="Optional channel override")
    @admin_only
    async def addsubreddit(self, interaction: discord.Interaction, subreddit: str,
                           channel: discord.TextChannel | None = None) -> None:
        name = normalize_subreddit(subreddit)
        if not name:
            await interaction.response.send_message("That isn't a valid subreddit name.", ephemeral=True)
            return
        if channel and not await self._check_channel(interaction, channel):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            info = await self.bot.reddit.subreddit_info(name)
        except SubredditNotFound:
            await interaction.followup.send(f"r/{name} doesn't exist.", ephemeral=True); return
        except SubredditForbidden:
            await interaction.followup.send(f"r/{name} is private or unavailable.", ephemeral=True); return
        except RedditError:
            await interaction.followup.send("Reddit isn't responding right now. Try again soon.", ephemeral=True); return
        if info.get("over18"):
            await interaction.followup.send("NSFW subreddits are not supported.", ephemeral=True); return
        if info.get("subreddit_type") in ("private", "user"):
            await interaction.followup.send(f"r/{name} isn't a public subreddit.", ephemeral=True); return

        async with self.bot.sessionmaker() as s:
            g = await self._guild(s, interaction.guild_id)  # type: ignore[arg-type]
            count = await s.scalar(select(func.count()).select_from(Subscription)
                                   .where(Subscription.guild_id == g.guild_id))
            limit = self.bot.settings.max_subreddits_per_guild
            if (count or 0) >= limit:
                await interaction.followup.send(f"Plan limit reached ({limit} subreddits).", ephemeral=True); return
            exists = await s.scalar(select(Subscription.id).where(
                Subscription.guild_id == g.guild_id, func.lower(Subscription.subreddit) == name.lower()))
            if exists:
                await interaction.followup.send(f"Already subscribed to r/{name}.", ephemeral=True); return
            if not (channel or g.channel_id):
                await interaction.followup.send("Run `/setup` first to pick a channel.", ephemeral=True); return
            s.add(Subscription(guild_id=g.guild_id, subreddit=name, channel_id=channel.id if channel else None))
            await s.commit()
        await interaction.followup.send(
            f"✅ Subscribed to **r/{name}**. New posts from now on will appear in the channel.", ephemeral=True)

    @app_commands.command(name="removesubreddit", description="Remove a subreddit subscription")
    @app_commands.describe(subreddit="Subreddit to remove")
    @admin_only
    async def removesubreddit(self, interaction: discord.Interaction, subreddit: str) -> None:
        name = normalize_subreddit(subreddit)
        async with self.bot.sessionmaker() as s:
            sub = await s.scalar(select(Subscription).where(
                Subscription.guild_id == interaction.guild_id,
                func.lower(Subscription.subreddit) == (name or "").lower()))
            if not sub:
                await interaction.response.send_message("You aren't subscribed to that subreddit.", ephemeral=True)
                return
            await s.execute(delete(Delivery).where(Delivery.subscription_id == sub.id))
            await s.delete(sub)
            await s.commit()
        await interaction.response.send_message(f"Removed r/{name}.", ephemeral=True)

    @app_commands.command(name="listsubreddits", description="Show this server's subscriptions")
    @app_commands.guild_only()
    async def listsubreddits(self, interaction: discord.Interaction) -> None:
        async with self.bot.sessionmaker() as s:
            subs = (await s.scalars(select(Subscription).where(
                Subscription.guild_id == interaction.guild_id).order_by(Subscription.subreddit))).all()
            g = await s.get(GuildSettings, interaction.guild_id)
        if not subs:
            await interaction.response.send_message("No subscriptions yet. Use `/addsubreddit`.", ephemeral=True)
            return
        lines = []
        for sub in subs:
            ch = sub.channel_id or (g.channel_id if g else None)
            err = f" ⚠️ {sub.last_error}" if sub.last_error else ""
            lines.append(f"• **r/{sub.subreddit}** → <#{ch}>{err}")
        await interaction.response.send_message(embed=discord.Embed(
            title="Subscriptions", description="\n".join(lines), color=0xFF4500), ephemeral=True)

    @app_commands.command(name="setinterval", description="Set how often feeds are checked")
    @app_commands.describe(minutes="Polling interval")
    @app_commands.choices(minutes=[app_commands.Choice(name=f"{m} minutes", value=m) for m in INTERVALS])
    @admin_only
    async def setinterval(self, interaction: discord.Interaction, minutes: app_commands.Choice[int]) -> None:
        async with self.bot.sessionmaker() as s:
            (await self._guild(s, interaction.guild_id)).interval_minutes = minutes.value  # type: ignore[arg-type]
            await s.commit()
        await interaction.response.send_message(f"Checking every {minutes.value} minutes.", ephemeral=True)

    async def _set_paused(self, interaction: discord.Interaction, paused: bool) -> None:
        async with self.bot.sessionmaker() as s:
            (await self._guild(s, interaction.guild_id)).paused = paused  # type: ignore[arg-type]
            await s.commit()
        await interaction.response.send_message("⏸️ Paused." if paused else "▶️ Resumed.", ephemeral=True)

    @app_commands.command(name="pause", description="Pause automatic notifications")
    @admin_only
    async def pause(self, interaction: discord.Interaction) -> None:
        await self._set_paused(interaction, True)

    @app_commands.command(name="resume", description="Resume automatic notifications")
    @admin_only
    async def resume(self, interaction: discord.Interaction) -> None:
        await self._set_paused(interaction, False)

    @app_commands.command(name="testfeed", description="Send a test notification to the configured channel")
    @admin_only
    async def testfeed(self, interaction: discord.Interaction) -> None:
        async with self.bot.sessionmaker() as s:
            g = await s.get(GuildSettings, interaction.guild_id)
        if not g or not g.channel_id:
            await interaction.response.send_message("Run `/setup` first.", ephemeral=True); return
        post = RedditPost(id="test", subreddit="test", title="RedditBridge test notification",
                          author="redditbridge", permalink="https://www.reddit.com/", url="",
                          created_utc=utcnow(), media_type="text", over_18=False)
        try:
            await send_embed(self.bot, g.channel_id, build_embed(post))
        except discord.Forbidden:
            await interaction.response.send_message("I can't post in that channel (missing permissions).", ephemeral=True); return
        except discord.NotFound:
            await interaction.response.send_message("The configured channel no longer exists. Use `/setchannel`.", ephemeral=True); return
        await interaction.response.send_message("✅ Test notification sent.", ephemeral=True)

    @app_commands.command(name="status", description="Show bot status")
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction) -> None:
        sch = self.bot.scheduler
        e = discord.Embed(title="RedditBridge status", color=0xFF4500)
        e.add_field(name="Discord latency", value=f"{self.bot.latency * 1000:.0f} ms")
        e.add_field(name="Reddit API", value="⚠️ " + self.bot.reddit.last_error if self.bot.reddit.last_error
                    else ("✅ OK" if self.bot.reddit.last_ok else "No request yet"))
        e.add_field(name="Last poll", value=f"{sch.last_run:%H:%M:%S} UTC" if sch.last_run else "not yet")
        e.add_field(name="Delivered / failed (since start)", value=f"{sch.sent} / {sch.failed}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="settings", description="Show this server's configuration")
    @app_commands.guild_only()
    async def settings(self, interaction: discord.Interaction) -> None:
        async with self.bot.sessionmaker() as s:
            g = await s.get(GuildSettings, interaction.guild_id)
        if not g:
            await interaction.response.send_message("Not configured yet. Run `/setup`.", ephemeral=True); return
        e = discord.Embed(title="Server settings", color=0xFF4500)
        e.add_field(name="Channel", value=f"<#{g.channel_id}>" if g.channel_id else "not set")
        e.add_field(name="Interval", value=f"{g.interval_minutes} min")
        e.add_field(name="State", value="⏸️ paused" if g.paused else "▶️ active")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="subscription", description="Show plan and usage")
    @app_commands.guild_only()
    async def subscription(self, interaction: discord.Interaction) -> None:
        async with self.bot.sessionmaker() as s:
            g = await s.get(GuildSettings, interaction.guild_id)
            used = await s.scalar(select(func.count()).select_from(Subscription)
                                  .where(Subscription.guild_id == interaction.guild_id)) or 0
            sent = await s.scalar(select(func.count()).select_from(Delivery).where(
                Delivery.guild_id == interaction.guild_id, Delivery.status == "sent")) or 0
        e = discord.Embed(title="Subscription", color=0xFF4500)
        e.add_field(name="Plan", value=(g.plan if g else "free").title())
        e.add_field(name="Subreddits", value=f"{used} / {self.bot.settings.max_subreddits_per_guild}")
        e.add_field(name="Posts delivered", value=str(sent))
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="help", description="List all commands")
    async def help(self, interaction: discord.Interaction) -> None:
        cmds = [("/setup", "Pick the notification channel (admin)"), ("/addsubreddit", "Subscribe to a subreddit (admin)"),
                ("/removesubreddit", "Unsubscribe (admin)"), ("/listsubreddits", "Show subscriptions"),
                ("/setchannel", "Change channel (admin)"), ("/setinterval", "Polling interval (admin)"),
                ("/pause · /resume", "Stop/start notifications (admin)"), ("/testfeed", "Send a test message (admin)"),
                ("/status", "Bot health"), ("/settings", "Server configuration"), ("/subscription", "Plan & usage")]
        await interaction.response.send_message(embed=discord.Embed(
            title="RedditBridge commands", color=0xFF4500,
            description="\n".join(f"`{c}` — {d}" for c, d in cmds)), ephemeral=True)
