"""Discord client: wires commands, scheduler and cleanup on guild removal."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.database.models import Delivery, GuildSettings, Subscription
from app.reddit.client import RedditClient
from app.services.scheduler import Scheduler

log = logging.getLogger(__name__)
INVITE_PERMISSIONS = 19456  # View Channel + Send Messages + Embed Links


class RedditBridgeBot(commands.Bot):
    def __init__(self, settings: Settings, sessionmaker: async_sessionmaker[AsyncSession],
                 reddit: RedditClient) -> None:
        intents = discord.Intents.none()
        intents.guilds = True  # no privileged intents required
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings, self.sessionmaker, self.reddit = settings, sessionmaker, reddit
        self.scheduler = Scheduler(self, sessionmaker, reddit)
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self) -> None:
        from app.bot.commands.feeds import FeedCommands
        await self.add_cog(FeedCommands(self))
        await self.tree.sync()
        self.scheduler.start()

    async def on_ready(self) -> None:
        log.info("bot ready", extra={"guilds": len(self.guilds)})
        cid = self.settings.discord_client_id
        if cid:
            print(f"Invite URL: https://discord.com/oauth2/authorize?client_id={cid}"
                  f"&scope=bot+applications.commands&permissions={INVITE_PERMISSIONS}")

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Delete all of a server's data when the bot is removed."""
        async with self.sessionmaker() as s:
            await s.execute(delete(Delivery).where(Delivery.guild_id == guild.id))
            await s.execute(delete(Subscription).where(Subscription.guild_id == guild.id))
            await s.execute(delete(GuildSettings).where(GuildSettings.guild_id == guild.id))
            await s.commit()
        log.info("guild data removed", extra={"guild_id": guild.id})

    async def on_app_command_error(self, interaction: discord.Interaction,
                                   error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            msg = "You need the **Manage Server** permission to use this command."
        elif isinstance(error, app_commands.NoPrivateMessage):
            msg = "This command only works inside a server."
        else:
            log.exception("command error", exc_info=error)
            msg = "Something went wrong. Please try again later."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    async def close(self) -> None:
        await self.scheduler.stop()
        await self.reddit.aclose()
        await super().close()
