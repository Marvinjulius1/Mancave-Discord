"""
Daily Check-in & Streaks.

  /checkin              -> Was hast du heute für Körper, Business und Wissen getan?
  /streak [mitglied]    -> aktuelle und längste Serie
  /streak-leaderboard   -> die längsten aktuellen Serien
"""

import discord
from discord import app_commands
from discord.ext import commands

import config
import db
from cogs.leveling import grant_xp
from utils import (best_streak_from_days, get_role, get_text_channel, medal, member_name, now, send_log,
                   streak_from_days, today_str)


def checkin_days(user_id: int) -> list[str]:
    return [r["day"] for r in db.fetchall("SELECT day FROM checkins WHERE user_id = ?", (user_id,))]


def current_streak(user_id: int) -> int:
    return streak_from_days(checkin_days(user_id))


def all_current_streaks() -> list[tuple[int, int]]:
    """[(user_id, streak)] absteigend sortiert, nur Serien > 0."""
    users = [r["user_id"] for r in db.fetchall("SELECT DISTINCT user_id FROM checkins")]
    streaks = [(uid, current_streak(uid)) for uid in users]
    return sorted([s for s in streaks if s[1] > 0], key=lambda s: s[1], reverse=True)


def streak_emoji(streak: int) -> str:
    if streak >= 100:
        return "👑"
    if streak >= 30:
        return "💎"
    if streak >= 7:
        return "🔥"
    return "✨"


class Checkin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="checkin", description="Dein täglicher Check-in: Körper, Business, Wissen")
    @app_commands.describe(
        koerper="Was hast du heute für deinen Körper getan? (Training, Ernährung, Schlaf ...)",
        business="Woran hast du heute im Business gearbeitet?",
        wissen="Was hast du heute gelernt?",
    )
    @app_commands.guild_only()
    async def checkin(
        self,
        interaction: discord.Interaction,
        koerper: app_commands.Range[str, 2, 300],
        business: app_commands.Range[str, 2, 300],
        wissen: app_commands.Range[str, 2, 300],
    ):
        member = interaction.user
        day = today_str()
        if db.fetchone("SELECT 1 FROM checkins WHERE user_id = ? AND day = ?", (member.id, day)):
            await interaction.response.send_message(
                "✅ Du hast heute schon eingecheckt. Morgen geht's weiter – Serie nicht reißen lassen! 🔥",
                ephemeral=True,
            )
            return

        db.execute(
            "INSERT INTO checkins(user_id, day, koerper, business, wissen, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (member.id, day, koerper, business, wissen, now().isoformat()),
        )
        days = checkin_days(member.id)
        streak = streak_from_days(days)
        best = best_streak_from_days(days)

        xp = config.XP_CHECKIN
        bonus = config.XP_STREAK_BONUS.get(streak, 0)
        xp += bonus

        embed = discord.Embed(
            title=f"{streak_emoji(streak)} Check-in von {member.display_name}",
            color=0x2ECC71,
            timestamp=now(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="💪 Körper", value=koerper, inline=False)
        embed.add_field(name="💰 Business", value=business, inline=False)
        embed.add_field(name="🧠 Wissen", value=wissen, inline=False)
        embed.set_footer(text=f"Serie: {streak} Tag(e) · Rekord: {best} · +{xp} XP")

        channel = get_text_channel(interaction.guild, config.CHECKIN_CHANNEL)
        if channel and channel.id != interaction.channel_id:
            await channel.send(content=member.mention, embed=embed, allowed_mentions=discord.AllowedMentions.none())
            await interaction.response.send_message(
                f"✅ Eingecheckt! Serie: **{streak}** Tag(e). Gepostet in {channel.mention}.", ephemeral=True,
            )
        else:
            await interaction.response.send_message(embed=embed)

        if bonus:
            await interaction.followup.send(
                f"{streak_emoji(streak)} **{member.mention} hat eine {streak}-Tage-Serie!** +{bonus} Bonus-XP 🎉",
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        await grant_xp(member, xp)
        if streak >= config.STREAK_ROLE_DAYS:
            await self.give_streak_role(member, streak)

    async def give_streak_role(self, member: discord.Member, streak: int):
        role = get_role(member.guild, config.ROLE_STREAK)
        if role is None or role in member.roles:
            return
        try:
            await member.add_roles(role, reason=f"{streak} Tage Check-in-Serie")
        except discord.HTTPException:
            return
        await send_log(member.guild, f"🔥 {member.mention} ist jetzt **{role.name}** ({streak} Tage Serie).")

    @app_commands.command(name="streak", description="Zeigt deine Check-in-Serie")
    @app_commands.describe(mitglied="Wessen Serie? (leer = deine)")
    @app_commands.guild_only()
    async def streak(self, interaction: discord.Interaction, mitglied: discord.Member | None = None):
        member = mitglied or interaction.user
        days = checkin_days(member.id)
        streak = streak_from_days(days)
        done_today = today_str() in days
        embed = discord.Embed(title=f"{streak_emoji(streak)} Serie von {member.display_name}", color=0x2ECC71)
        embed.add_field(name="Aktuelle Serie", value=f"**{streak}** Tag(e)")
        embed.add_field(name="Rekord", value=f"{best_streak_from_days(days)} Tag(e)")
        embed.add_field(name="Check-ins gesamt", value=str(len(days)))
        embed.add_field(
            name="Heute",
            value="✅ erledigt" if done_today else "⏳ noch offen – `/checkin`",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="streak-leaderboard", description="Die längsten aktuellen Check-in-Serien")
    @app_commands.guild_only()
    async def streak_leaderboard(self, interaction: discord.Interaction):
        top = all_current_streaks()[:10]
        if not top:
            await interaction.response.send_message("Noch keine aktiven Serien. Starte mit `/checkin`! 🔥")
            return
        lines = [
            f"{medal(i)} **{member_name(interaction.guild, uid)}** – {streak} Tag(e) {streak_emoji(streak)}"
            for i, (uid, streak) in enumerate(top)
        ]
        embed = discord.Embed(title="🔥 Streak-Leaderboard", description="\n".join(lines), color=0x2ECC71)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Checkin(bot))
