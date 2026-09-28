"""
Business-Ideen-Voting.

  /idee titel beschreibung -> Eintrag in #business-ideen mit 👍/👎 und eigenem Diskussions-Thread
  /ideen-top               -> die am besten bewerteten Ideen
"""

import discord
from discord import app_commands
from discord.ext import commands

import config
import db
from cogs.leveling import grant_xp
from utils import get_text_channel, medal, member_name, now

UP, DOWN = "👍", "👎"


class Ideas(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="idee", description="Business-Idee pitchen – die Community stimmt ab")
    @app_commands.describe(titel="Kurzer Titel", beschreibung="Worum geht's? Zielgruppe, Geldquelle, erster Schritt ...")
    @app_commands.guild_only()
    async def idee(self, interaction: discord.Interaction, titel: app_commands.Range[str, 3, 100],
                   beschreibung: app_commands.Range[str, 10, 1500]):
        channel = get_text_channel(interaction.guild, config.IDEAS_CHANNEL)
        if channel is None:
            await interaction.response.send_message("⚠️ Kanal für Ideen fehlt – Admin muss /setup ausführen.", ephemeral=True)
            return
        number = db.scalar("SELECT COUNT(*) FROM ideas") + 1
        embed = discord.Embed(title=f"💡 Idee #{number}: {titel}", description=beschreibung, color=0x9B59B6,
                              timestamp=now())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"Abstimmen mit {UP} / {DOWN} · Diskussion im Thread")
        message = await channel.send(embed=embed)
        await message.add_reaction(UP)
        await message.add_reaction(DOWN)
        try:
            await message.create_thread(name=f"💬 {titel}"[:100], auto_archive_duration=10080)
        except discord.HTTPException:
            pass
        db.execute(
            "INSERT INTO ideas(message_id, channel_id, author_id, title, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (message.id, channel.id, interaction.user.id, titel, beschreibung, now().isoformat()),
        )
        await interaction.response.send_message(f"✅ Deine Idee ist online: {message.jump_url}", ephemeral=True)
        await grant_xp(interaction.user, config.XP_IDEA)

    @app_commands.command(name="ideen-top", description="Die am besten bewerteten Business-Ideen")
    @app_commands.guild_only()
    async def ideen_top(self, interaction: discord.Interaction):
        rows = db.fetchall(
            "SELECT *, (up - down) AS score FROM ideas ORDER BY score DESC, up DESC, id DESC LIMIT 10"
        )
        if not rows:
            await interaction.response.send_message("Noch keine Ideen. Starte mit `/idee`! 💡")
            return
        lines = []
        for i, r in enumerate(rows):
            url = f"https://discord.com/channels/{interaction.guild_id}/{r['channel_id']}/{r['message_id']}"
            lines.append(
                f"{medal(i)} [{r['title']}]({url}) – {UP} {r['up']} · {DOWN} {r['down']} "
                f"· von {member_name(interaction.guild, r['author_id'])}"
            )
        embed = discord.Embed(title="💡 Top Business-Ideen", description="\n".join(lines), color=0x9B59B6)
        await interaction.response.send_message(embed=embed)

    # Stimmen live mitzählen
    async def _vote(self, payload: discord.RawReactionActionEvent, delta: int):
        if payload.guild_id != self.bot.guild_id or payload.user_id == self.bot.user.id:
            return
        emoji = str(payload.emoji)
        if emoji not in (UP, DOWN):
            return
        column = "up" if emoji == UP else "down"
        db.execute(f"UPDATE ideas SET {column} = MAX(0, {column} + ?) WHERE message_id = ?", (delta, payload.message_id))

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._vote(payload, 1)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._vote(payload, -1)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ideas(bot))
