"""
Wochen-Challenges.

  /challenge-erstellen (Admin)  -> Challenge in #challenges mit "Mitmachen"-Button
  /challenge-checkin            -> heutigen Tag abhaken
  /challenge-status             -> aktive Challenges & dein Fortschritt
  /challenge-beenden (Admin)    -> Challenge vorzeitig beenden

Wer JEDEN Tag der Challenge abhakt, bekommt die Rolle config.ROLE_CHAMPION + Bonus-XP.
Abgelaufene Challenges werden automatisch abgeschlossen und ausgewertet.
"""

from datetime import date, timedelta
from datetime import time as dtime

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import db
from cogs.leveling import grant_xp
from utils import TZ, get_role, get_text_channel, log, now, progress_bar, send_log, today, today_str

JOIN_ID = "mancave:challenge_join"


def challenge_embed(ch) -> discord.Embed:
    participants = db.scalar("SELECT COUNT(*) FROM challenge_participants WHERE challenge_id = ?", (ch["id"],))
    start = date.fromisoformat(ch["start_day"])
    end = date.fromisoformat(ch["end_day"])
    status = "🟢 läuft" if ch["active"] else "🏁 beendet"
    embed = discord.Embed(
        title=f"🎯 Challenge: {ch['name']}",
        description=(ch["description"] or "")
        + f"\n\n📅 **{start.strftime('%d.%m.')} – {end.strftime('%d.%m.%Y')}** ({ch['days']} Tage)\n"
        f"✅ Jeden Tag `/challenge-checkin` – wer alle {ch['days']} Tage schafft, wird **{config.ROLE_CHAMPION}**!",
        color=0xF1C40F if ch["active"] else 0x95A5A6,
    )
    embed.add_field(name="Teilnehmer", value=str(participants))
    embed.add_field(name="Status", value=status)
    embed.set_footer(text=f"Challenge #{ch['id']}")
    return embed


def active_challenges():
    return db.fetchall("SELECT * FROM challenges WHERE active = 1 ORDER BY id")


class JoinView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Mitmachen", emoji="🎯", style=discord.ButtonStyle.success, custom_id=JOIN_ID)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        ch = db.fetchone("SELECT * FROM challenges WHERE message_id = ?", (interaction.message.id,))
        if ch is None or not ch["active"] or ch["end_day"] < today_str():
            await interaction.response.send_message("Diese Challenge ist schon vorbei.", ephemeral=True)
            return
        if db.fetchone("SELECT 1 FROM challenge_participants WHERE challenge_id = ? AND user_id = ?",
                       (ch["id"], interaction.user.id)):
            await interaction.response.send_message("Du bist schon dabei! Täglich `/challenge-checkin` 💪", ephemeral=True)
            return
        if ch["start_day"] < today_str():
            # Wer später einsteigt, kann nicht mehr alle Tage schaffen – trotzdem mitmachen lassen, aber Hinweis
            note = "\n⚠️ Die Challenge läuft schon – für den Champion-Titel zählen alle Tage, aber mitmachen lohnt sich trotzdem!"
        else:
            note = ""
        db.execute("INSERT INTO challenge_participants(challenge_id, user_id, joined_at) VALUES (?, ?, ?)",
                   (ch["id"], interaction.user.id, now().isoformat()))
        await interaction.response.send_message(
            f"🎯 Du bist bei **{ch['name']}** dabei! Hake jeden Tag mit `/challenge-checkin` ab.{note}", ephemeral=True,
        )
        try:
            await interaction.message.edit(embed=challenge_embed(ch))
        except discord.HTTPException:
            pass


class Challenges(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(JoinView())

    async def cog_unload(self):
        self.close_expired.cancel()

    @commands.Cog.listener()
    async def on_mancave_ready(self, guild: discord.Guild):
        if not self.close_expired.is_running():
            self.close_expired.start()
        await self.close_expired_now(guild)

    # ------------------------------------------------------------ Admin

    @app_commands.command(name="challenge-erstellen", description="(Admin) Neue Challenge starten")
    @app_commands.describe(name="z. B. '7 Tage kein Zucker'", beschreibung="Regeln / Details",
                           tage="Dauer in Tagen", start_morgen="Erst morgen starten (sonst heute)")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def create(self, interaction: discord.Interaction, name: app_commands.Range[str, 3, 80],
                     beschreibung: app_commands.Range[str, 3, 1000], tage: app_commands.Range[int, 1, 90] = 7,
                     start_morgen: bool = False):
        channel = get_text_channel(interaction.guild, config.CHALLENGE_CHANNEL)
        if channel is None:
            await interaction.response.send_message("⚠️ #challenges fehlt – /setup ausführen.", ephemeral=True)
            return
        start = today() + timedelta(days=1 if start_morgen else 0)
        end = start + timedelta(days=tage - 1)
        cur = db.execute(
            "INSERT INTO challenges(name, description, days, start_day, end_day, channel_id, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, beschreibung, tage, start.isoformat(), end.isoformat(), channel.id, interaction.user.id),
        )
        ch = db.fetchone("SELECT * FROM challenges WHERE id = ?", (cur.lastrowid,))
        message = await channel.send(content="🎯 **Neue Challenge!**", embed=challenge_embed(ch), view=JoinView())
        db.execute("UPDATE challenges SET message_id = ? WHERE id = ?", (message.id, ch["id"]))
        await interaction.response.send_message(f"✅ Challenge erstellt: {message.jump_url}", ephemeral=True)
        await send_log(interaction.guild, f"🎯 {interaction.user.mention} hat die Challenge **{name}** gestartet.")

    @app_commands.command(name="challenge-beenden", description="(Admin) Challenge jetzt beenden und auswerten")
    @app_commands.describe(challenge="Welche Challenge?")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def end(self, interaction: discord.Interaction, challenge: int):
        ch = db.fetchone("SELECT * FROM challenges WHERE id = ? AND active = 1", (challenge,))
        if ch is None:
            await interaction.response.send_message("Keine aktive Challenge mit dieser Nummer.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.finish(interaction.guild, ch)
        await interaction.followup.send(f"🏁 **{ch['name']}** beendet.", ephemeral=True)

    # ------------------------------------------------------------ Mitglieder

    async def _joined_autocomplete(self, interaction: discord.Interaction, current: str):
        rows = db.fetchall(
            "SELECT c.id, c.name FROM challenges c JOIN challenge_participants p ON p.challenge_id = c.id "
            "WHERE c.active = 1 AND p.user_id = ?", (interaction.user.id,),
        ) if interaction.command.name == "challenge-checkin" else active_challenges()
        return [app_commands.Choice(name=f"#{r['id']} {r['name']}"[:100], value=r["id"])
                for r in rows if current.lower() in r["name"].lower()][:25]

    @end.autocomplete("challenge")
    async def end_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._joined_autocomplete(interaction, current)

    @app_commands.command(name="challenge-checkin", description="Heutigen Challenge-Tag abhaken ✅")
    @app_commands.describe(challenge="Welche Challenge? (leer = alle, bei denen du mitmachst)")
    @app_commands.guild_only()
    async def checkin(self, interaction: discord.Interaction, challenge: int | None = None):
        day = today_str()
        query = ("SELECT c.* FROM challenges c JOIN challenge_participants p ON p.challenge_id = c.id "
                 "WHERE c.active = 1 AND p.user_id = ? AND c.start_day <= ? AND c.end_day >= ?")
        params = [interaction.user.id, day, day]
        if challenge is not None:
            query += " AND c.id = ?"
            params.append(challenge)
        rows = db.fetchall(query, tuple(params))
        if not rows:
            await interaction.response.send_message(
                "Du bist in keiner laufenden Challenge. Schau in #challenges und klick auf **Mitmachen**! 🎯",
                ephemeral=True,
            )
            return

        lines, xp, completed = [], 0, []
        for ch in rows:
            done = db.execute(
                "INSERT OR IGNORE INTO challenge_checkins(challenge_id, user_id, day) VALUES (?, ?, ?)",
                (ch["id"], interaction.user.id, day),
            ).rowcount
            count = db.scalar("SELECT COUNT(*) FROM challenge_checkins WHERE challenge_id = ? AND user_id = ?",
                              (ch["id"], interaction.user.id))
            bar = progress_bar(count, ch["days"], 10)
            if not done:
                lines.append(f"☑️ **{ch['name']}** – heute schon abgehakt ({count}/{ch['days']})")
                continue
            xp += config.XP_CHALLENGE_CHECKIN
            lines.append(f"✅ **{ch['name']}** {bar} {count}/{ch['days']}")
            already = db.scalar("SELECT completed FROM challenge_participants WHERE challenge_id = ? AND user_id = ?",
                                (ch["id"], interaction.user.id))
            if count >= ch["days"] and not already:
                completed.append(ch)

        await interaction.response.send_message("\n".join(lines), ephemeral=True)
        for ch in completed:
            await self.complete(interaction.user, ch)
        if xp:
            await grant_xp(interaction.user, xp)

    @checkin.autocomplete("challenge")
    async def checkin_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._joined_autocomplete(interaction, current)

    @app_commands.command(name="challenge-status", description="Aktive Challenges und dein Fortschritt")
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction):
        rows = active_challenges()
        if not rows:
            await interaction.response.send_message("Gerade läuft keine Challenge. 👀")
            return
        embed = discord.Embed(title="🎯 Laufende Challenges", color=0xF1C40F)
        for ch in rows:
            joined = db.fetchone("SELECT completed FROM challenge_participants WHERE challenge_id = ? AND user_id = ?",
                                 (ch["id"], interaction.user.id))
            count = db.scalar("SELECT COUNT(*) FROM challenge_checkins WHERE challenge_id = ? AND user_id = ?",
                              (ch["id"], interaction.user.id))
            people = db.scalar("SELECT COUNT(*) FROM challenge_participants WHERE challenge_id = ?", (ch["id"],))
            mine = ("🏆 geschafft!" if joined["completed"] else f"{progress_bar(count, ch['days'], 10)} {count}/{ch['days']}"
                    ) if joined else "nicht dabei – Button in #challenges"
            end = date.fromisoformat(ch["end_day"]).strftime("%d.%m.")
            embed.add_field(name=f"#{ch['id']} {ch['name']} (bis {end}, {people} dabei)", value=f"Du: {mine}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------ Auswertung

    async def complete(self, member: discord.Member, ch):
        db.execute("UPDATE challenge_participants SET completed = 1 WHERE challenge_id = ? AND user_id = ?",
                   (ch["id"], member.id))
        role = get_role(member.guild, config.ROLE_CHAMPION)
        if role and role not in member.roles:
            try:
                await member.add_roles(role, reason=f"Challenge '{ch['name']}' geschafft")
            except discord.HTTPException:
                pass
        channel = get_text_channel(member.guild, config.CHALLENGE_CHANNEL)
        if channel:
            await channel.send(
                f"🏆 {member.mention} hat die Challenge **{ch['name']}** komplett durchgezogen! "
                f"{ch['days']}/{ch['days']} Tage – absolute Disziplin. 🔥",
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        await grant_xp(member, config.XP_CHALLENGE_COMPLETE)

    async def finish(self, guild: discord.Guild, ch):
        db.execute("UPDATE challenges SET active = 0 WHERE id = ?", (ch["id"],))
        ch = db.fetchone("SELECT * FROM challenges WHERE id = ?", (ch["id"],))
        champions = db.fetchall("SELECT user_id FROM challenge_participants WHERE challenge_id = ? AND completed = 1",
                                (ch["id"],))
        total = db.scalar("SELECT COUNT(*) FROM challenge_participants WHERE challenge_id = ?", (ch["id"],))
        channel = guild.get_channel(ch["channel_id"]) or get_text_channel(guild, config.CHALLENGE_CHANNEL)
        if channel is None:
            return
        if ch["message_id"]:
            try:
                msg = await channel.fetch_message(ch["message_id"])
                await msg.edit(embed=challenge_embed(ch), view=None)
            except discord.HTTPException:
                pass
        names = ", ".join(f"<@{r['user_id']}>" for r in champions) or "diesmal leider niemand"
        embed = discord.Embed(
            title=f"🏁 Challenge beendet: {ch['name']}",
            description=f"**{len(champions)} von {total}** haben alle {ch['days']} Tage geschafft.\n\n🏆 {names}",
            color=0xF1C40F,
        )
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))

    async def close_expired_now(self, guild: discord.Guild):
        for ch in db.fetchall("SELECT * FROM challenges WHERE active = 1 AND end_day < ?", (today_str(),)):
            await self.finish(guild, ch)

    @tasks.loop(time=dtime(0, 5, tzinfo=TZ))
    async def close_expired(self):
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild:
            await self.close_expired_now(guild)

    @close_expired.error
    async def close_expired_error(self, error):
        log.exception("Challenge-Auswertung fehlgeschlagen", exc_info=error)


async def setup(bot: commands.Bot):
    await bot.add_cog(Challenges(bot))
