"""
Gym-Log.

  /workout            -> Training eintragen (+XP)
  /gym-stats          -> Wochen- & Gesamtstatistik
  /gym-leaderboard    -> wer hat diese Woche am meisten trainiert?
  Montags             -> automatischer Wochen-Rückblick in #gym-log
"""

from datetime import time as dtime
from typing import Optional
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import db
from cogs.leveling import grant_xp
from utils import TZ, get_text_channel, log, medal, member_name, now, streak_from_days, today, today_str, week_start

KIND_EMOJI = {
    "Kraft": "🏋️", "Cardio": "🏃", "Kampfsport": "🥊", "Sport / Spiel": "⚽",
    "Mobility / Yoga": "🧘", "Sonstiges": "💪",
}


def week_leaderboard(start: str, end: str, limit: int = 10):
    return db.fetchall(
        "SELECT user_id, COUNT(*) AS sessions, SUM(minutes) AS minutes FROM workouts "
        "WHERE day >= ? AND day <= ? GROUP BY user_id ORDER BY minutes DESC, sessions DESC LIMIT ?",
        (start, end, limit),
    )


def fmt_minutes(minutes: int) -> str:
    h, m = divmod(int(minutes or 0), 60)
    return f"{h} Std. {m} Min." if h else f"{m} Min."


class Fitness(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_unload(self):
        self.weekly_recap.cancel()

    @commands.Cog.listener()
    async def on_mancave_ready(self, guild: discord.Guild):
        if not self.weekly_recap.is_running():
            self.weekly_recap.start()

    @app_commands.command(name="workout", description="Trag dein Training ein 💪")
    @app_commands.describe(art="Art des Trainings", dauer="Dauer in Minuten", notiz="z. B. 'Push Day, Bankdrücken 100 kg PR'")
    @app_commands.choices(art=[app_commands.Choice(name=f"{KIND_EMOJI.get(k, '💪')} {k}", value=k) for k in config.WORKOUT_TYPES])
    @app_commands.guild_only()
    async def workout(
        self,
        interaction: discord.Interaction,
        art: app_commands.Choice[str],
        dauer: app_commands.Range[int, 5, 600],
        notiz: Optional[app_commands.Range[str, 1, 300]] = None,
    ):
        member = interaction.user
        day = today_str()
        today_count = db.scalar("SELECT COUNT(*) FROM workouts WHERE user_id = ? AND day = ?", (member.id, day))
        db.execute(
            "INSERT INTO workouts(user_id, day, kind, minutes, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (member.id, day, art.value, dauer, notiz, now().isoformat()),
        )
        ws = week_start().isoformat()
        week = db.fetchone(
            "SELECT COUNT(*) AS s, COALESCE(SUM(minutes), 0) AS m FROM workouts WHERE user_id = ? AND day >= ?",
            (member.id, ws),
        )
        days = [r["day"] for r in db.fetchall("SELECT DISTINCT day FROM workouts WHERE user_id = ?", (member.id,))]
        xp = config.XP_WORKOUT if today_count < config.XP_WORKOUT_MAX_PER_DAY else 0

        embed = discord.Embed(
            title=f"{KIND_EMOJI.get(art.value, '💪')} {member.display_name} hat trainiert!",
            description=f"**{art.value}** · {dauer} Min." + (f"\n> {notiz}" if notiz else ""),
            color=0xE74C3C,
            timestamp=now(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(
            text=f"Diese Woche: {week['s']}× · {fmt_minutes(week['m'])} · Trainingstage am Stück: "
                 f"{streak_from_days(days)}" + (f" · +{xp} XP" if xp else "")
        )

        channel = get_text_channel(interaction.guild, config.GYM_CHANNEL)
        if channel and channel.id != interaction.channel_id:
            await channel.send(embed=embed)
            await interaction.response.send_message(f"💪 Eingetragen! Gepostet in {channel.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed)
        if xp:
            await grant_xp(member, xp)

    @app_commands.command(name="gym-stats", description="Deine Trainings-Statistik")
    @app_commands.describe(mitglied="Wessen Statistik? (leer = deine)")
    @app_commands.guild_only()
    async def gym_stats(self, interaction: discord.Interaction, mitglied: discord.Member | None = None):
        member = mitglied or interaction.user
        ws = week_start().isoformat()
        week = db.fetchone(
            "SELECT COUNT(*) AS s, COALESCE(SUM(minutes), 0) AS m FROM workouts WHERE user_id = ? AND day >= ?",
            (member.id, ws),
        )
        total = db.fetchone(
            "SELECT COUNT(*) AS s, COALESCE(SUM(minutes), 0) AS m FROM workouts WHERE user_id = ?", (member.id,),
        )
        kinds = db.fetchall(
            "SELECT kind, COUNT(*) AS c FROM workouts WHERE user_id = ? GROUP BY kind ORDER BY c DESC", (member.id,),
        )
        # Letzte 7 Tage als Kalender-Leiste
        trained = {r["day"] for r in db.fetchall(
            "SELECT DISTINCT day FROM workouts WHERE user_id = ? AND day >= ?",
            (member.id, (today() - timedelta(days=6)).isoformat()),
        )}
        bar = " ".join(
            "🟩" if (today() - timedelta(days=6 - i)).isoformat() in trained else "⬛" for i in range(7)
        )
        embed = discord.Embed(title=f"🏋️ Gym-Stats von {member.display_name}", color=0xE74C3C)
        embed.add_field(name="Diese Woche", value=f"{week['s']} Trainings\n{fmt_minutes(week['m'])}")
        embed.add_field(name="Gesamt", value=f"{total['s']} Trainings\n{fmt_minutes(total['m'])}")
        embed.add_field(name="Letzte 7 Tage", value=bar, inline=False)
        if kinds:
            embed.add_field(
                name="Lieblings-Training",
                value=" · ".join(f"{KIND_EMOJI.get(k['kind'], '💪')} {k['kind']} ({k['c']})" for k in kinds[:4]),
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="gym-leaderboard", description="Wer hat diese Woche am meisten trainiert?")
    @app_commands.guild_only()
    async def gym_leaderboard(self, interaction: discord.Interaction):
        ws = week_start()
        rows = week_leaderboard(ws.isoformat(), today_str())
        if not rows:
            await interaction.response.send_message("Diese Woche hat noch niemand trainiert. Sei der Erste! `/workout` 💪")
            return
        lines = [
            f"{medal(i)} **{member_name(interaction.guild, r['user_id'])}** – {fmt_minutes(r['minutes'])} "
            f"({r['sessions']}×)"
            for i, r in enumerate(rows)
        ]
        embed = discord.Embed(
            title="🏋️ Gym-Leaderboard dieser Woche",
            description="\n".join(lines),
            color=0xE74C3C,
        )
        embed.set_footer(text=f"Woche ab {ws.strftime('%d.%m.%Y')}")
        await interaction.response.send_message(embed=embed)

    @tasks.loop(time=dtime(*config.GYM_WEEKLY_RECAP_TIME, tzinfo=TZ))
    async def weekly_recap(self):
        if today().weekday() != 0:  # nur montags
            return
        guild = self.bot.get_guild(self.bot.guild_id)
        channel = get_text_channel(guild, config.GYM_CHANNEL) if guild else None
        if channel is None:
            return
        start = week_start() - timedelta(days=7)
        end = start + timedelta(days=6)
        rows = week_leaderboard(start.isoformat(), end.isoformat(), limit=5)
        totals = db.fetchone(
            "SELECT COUNT(*) AS s, COALESCE(SUM(minutes), 0) AS m, COUNT(DISTINCT user_id) AS u "
            "FROM workouts WHERE day >= ? AND day <= ?",
            (start.isoformat(), end.isoformat()),
        )
        if not rows:
            return
        lines = [
            f"{medal(i)} <@{r['user_id']}> – {fmt_minutes(r['minutes'])} ({r['sessions']}×)" for i, r in enumerate(rows)
        ]
        embed = discord.Embed(
            title=f"📊 Gym-Wochenrückblick {start.strftime('%d.%m.')}–{end.strftime('%d.%m.')}",
            description="\n".join(lines)
            + f"\n\nZusammen: **{totals['s']} Trainings**, **{fmt_minutes(totals['m'])}** von {totals['u']} Leuten. 💪\n"
            "Neue Woche, neue Chance – ab ins Gym!",
            color=0xE74C3C,
        )
        await channel.send(embed=embed)

    @weekly_recap.error
    async def weekly_recap_error(self, error):
        log.exception("Gym-Wochenrückblick fehlgeschlagen", exc_info=error)


async def setup(bot: commands.Bot):
    await bot.add_cog(Fitness(bot))
