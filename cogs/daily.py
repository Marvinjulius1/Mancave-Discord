"""
Tägliches Zitat & Lern-Impuls in #self-improvement (Uhrzeit: config.DAILY_QUOTE_TIME).

  /zitat -> zufälliges Zitat
"""

import random
from datetime import time as dtime

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import db
from quotes import IMPULSES, QUOTES
from utils import TZ, get_text_channel, log, today, today_str


def quote_embed(quote: tuple[str, str], impulse: str | None = None, title: str = "☀️ Guten Morgen, Mancave!"):
    text, author = quote
    embed = discord.Embed(title=title, description=f"> *„{text}“*\n> — **{author}**", color=0xF7931A)
    if impulse:
        embed.add_field(name="🎯 Impuls des Tages", value=impulse, inline=False)
        embed.set_footer(text="Vergiss deinen /checkin heute nicht 🔥")
    return embed


class Daily(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_unload(self):
        self.daily_post.cancel()

    @commands.Cog.listener()
    async def on_mancave_ready(self, guild: discord.Guild):
        if config.DAILY_QUOTE_ENABLED and not self.daily_post.is_running():
            self.daily_post.start()

    async def post_daily(self, guild: discord.Guild) -> bool:
        channel = get_text_channel(guild, config.SELF_IMPROVEMENT_CHANNEL)
        if channel is None:
            return False
        day_index = today().toordinal()
        embed = quote_embed(QUOTES[day_index % len(QUOTES)], IMPULSES[day_index % len(IMPULSES)])
        await channel.send(embed=embed)
        db.kv_set("daily_quote_last", today_str())
        return True

    @tasks.loop(time=dtime(*config.DAILY_QUOTE_TIME, tzinfo=TZ))
    async def daily_post(self):
        if db.kv_get("daily_quote_last") == today_str():
            return
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild:
            await self.post_daily(guild)

    @daily_post.error
    async def daily_post_error(self, error):
        log.exception("Tages-Zitat fehlgeschlagen", exc_info=error)

    @app_commands.command(name="zitat", description="Ein zufälliges Motivations-Zitat")
    async def zitat(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=quote_embed(random.choice(QUOTES), title="💬 Zitat"))


async def setup(bot: commands.Bot):
    await bot.add_cog(Daily(bot))
