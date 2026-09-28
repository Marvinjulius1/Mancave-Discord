"""
Server-Statistik.

  - Kategorie "📊 SERVER-STATS" ganz oben mit einem Voice-Kanal "👥 Mitglieder: 123" (nicht betretbar)
  - wird alle 10 Minuten aktualisiert (Discord erlaubt nur 2 Umbenennungen pro 10 Min.)
  - speichert täglich die Mitgliederzahl für das Dashboard
  - /serverinfo
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import db
from utils import bot_can_manage, log, today_str

PREFIX = config.STATS_MEMBER_FORMAT.split("{")[0]


def human_count(guild: discord.Guild) -> int:
    return sum(1 for m in guild.members if not m.bot)


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_unload(self):
        self.update_loop.cancel()

    @commands.Cog.listener()
    async def on_mancave_ready(self, guild: discord.Guild):
        await self.update(guild)
        if not self.update_loop.is_running():
            self.update_loop.start()

    async def ensure_channel(self, guild: discord.Guild) -> discord.VoiceChannel | None:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=False),
            guild.me: bot_can_manage(),
        }
        category = discord.utils.get(guild.categories, name=config.STATS_CATEGORY)
        if category is None:
            category = await guild.create_category(config.STATS_CATEGORY, overwrites=overwrites, position=0,
                                                   reason="Server-Statistik")
            log.info("Kategorie erstellt: %s", config.STATS_CATEGORY)
        channel = next((c for c in category.voice_channels if c.name.startswith(PREFIX)), None)
        if channel is None:
            channel = await category.create_voice_channel(
                config.STATS_MEMBER_FORMAT.format(count=human_count(guild)), overwrites=overwrites,
                reason="Server-Statistik",
            )
        return channel

    async def update(self, guild: discord.Guild):
        count = human_count(guild)
        db.execute("INSERT INTO member_stats(day, members) VALUES (?, ?) "
                   "ON CONFLICT(day) DO UPDATE SET members = excluded.members", (today_str(), count))
        try:
            channel = await self.ensure_channel(guild)
            name = config.STATS_MEMBER_FORMAT.format(count=count)
            if channel and channel.name != name:
                await channel.edit(name=name, reason="Mitgliederzahl aktualisiert")
        except discord.HTTPException as e:
            log.warning("Server-Statistik konnte nicht aktualisiert werden: %s", e)

    @tasks.loop(minutes=10)
    async def update_loop(self):
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild:
            await self.update(guild)

    @update_loop.error
    async def update_loop_error(self, error):
        log.exception("Stats-Update fehlgeschlagen", exc_info=error)

    @app_commands.command(name="serverinfo", description="Zahlen & Fakten zur Mancave")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title=f"📊 {guild.name}", color=0xF7931A)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="👥 Mitglieder", value=str(human_count(guild)))
        embed.add_field(name="💬 Nachrichten (seit Bot-Start)", value=f"{db.scalar('SELECT SUM(messages) FROM users'):,}".replace(",", "."))
        embed.add_field(name="🎙️ Voice-Minuten", value=f"{db.scalar('SELECT SUM(voice_minutes) FROM users'):,}".replace(",", "."))
        embed.add_field(name="✅ Check-ins", value=str(db.scalar("SELECT COUNT(*) FROM checkins")))
        embed.add_field(name="🏋️ Workouts", value=str(db.scalar("SELECT COUNT(*) FROM workouts")))
        embed.add_field(name="💡 Ideen", value=str(db.scalar("SELECT COUNT(*) FROM ideas")))
        embed.add_field(name="🏆 Hall of Fame", value=str(db.scalar("SELECT COUNT(*) FROM hall_of_fame")))
        embed.add_field(name="📅 Gegründet", value=discord.utils.format_dt(guild.created_at, "D"))
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
