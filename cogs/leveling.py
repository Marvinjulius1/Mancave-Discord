"""
XP- & Level-System mit automatischen Rang-Rollen.

  - Nachrichten geben XP (mit Cooldown), Voice-Zeit gibt XP pro Minute
  - Check-ins, Workouts, Ideen, Hall of Fame und Challenges geben Bonus-XP (grant_xp)
  - Ab bestimmten Levels werden die Rang-Rollen aus config.LEVEL_ROLES vergeben
  - /rank, /leaderboard, /xp-geben (Admin)
"""

import random
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import db
from utils import get_role, get_text_channel, log, medal, member_name, progress_bar, send_log

RANK_NAMES = [name for _, name in config.LEVEL_ROLES]


# --------------------------------------------------------------------------- #
# Level-Mathematik
# --------------------------------------------------------------------------- #

def xp_needed(level: int) -> int:
    """XP, die man für den Schritt von `level` auf `level + 1` braucht."""
    return 5 * level * level + 50 * level + 100


def level_from_xp(xp: int) -> tuple[int, int]:
    """Gibt (Level, XP im aktuellen Level) zurück."""
    level = 0
    while xp >= xp_needed(level):
        xp -= xp_needed(level)
        level += 1
    return level, xp


def rank_for_level(level: int) -> str | None:
    rank = None
    for min_level, name in config.LEVEL_ROLES:
        if level >= min_level:
            rank = name
    return rank


def next_rank(level: int) -> tuple[int, str] | None:
    for min_level, name in config.LEVEL_ROLES:
        if level < min_level:
            return min_level, name
    return None


def get_level(user_id: int) -> int:
    return db.scalar("SELECT level FROM users WHERE user_id = ?", (user_id,))


# --------------------------------------------------------------------------- #
# XP vergeben (wird auch von anderen Modulen genutzt)
# --------------------------------------------------------------------------- #

async def grant_xp(member: discord.Member, amount: int) -> int:
    """Gibt einem Mitglied XP, vergibt Rang-Rollen und kündigt Level-Ups an. Gibt das neue Level zurück."""
    if member.bot or amount == 0:
        return get_level(member.id)
    db.ensure_user(member.id)
    row = db.fetchone("SELECT xp, level FROM users WHERE user_id = ?", (member.id,))
    new_xp = max(0, row["xp"] + amount)
    new_level, _ = level_from_xp(new_xp)
    db.execute("UPDATE users SET xp = ?, level = ? WHERE user_id = ?", (new_xp, new_level, member.id))

    if new_level != row["level"]:
        new_role = await apply_rank_role(member, new_level)
        if new_level > row["level"]:
            await announce_level_up(member, new_level, new_role)
    return new_level


async def apply_rank_role(member: discord.Member, level: int) -> discord.Role | None:
    """Vergibt die passende Rang-Rolle. Gibt die Rolle zurück, wenn sie NEU vergeben wurde."""
    target_name = rank_for_level(level)
    if target_name is None:
        return None
    idx = RANK_NAMES.index(target_name)
    current = [r for r in member.roles if r.name in RANK_NAMES]
    # Hat schon einen höheren Rang (z. B. manuell vergeben) -> nichts anfassen
    if any(RANK_NAMES.index(r.name) > idx for r in current):
        return None

    target = get_role(member.guild, target_name)
    if target is None:
        log.warning("Rang-Rolle '%s' fehlt – /setup ausführen.", target_name)
        return None
    lower = [r for r in current if RANK_NAMES.index(r.name) < idx]
    added = None
    try:
        if target not in member.roles:
            await member.add_roles(target, reason=f"Level {level} erreicht")
            added = target
        if lower:
            await member.remove_roles(*lower, reason="Neuer Rang erreicht")
    except discord.HTTPException as e:
        await send_log(member.guild, f"⚠️ Konnte Rang-Rolle für {member.mention} nicht setzen: {e}")
        return None
    if added:
        await send_log(member.guild, f"🏅 {member.mention} hat automatisch den Rang **{target.name}** bekommen (Level {level}).")
    return added


async def announce_level_up(member: discord.Member, level: int, new_role: discord.Role | None):
    channel = get_text_channel(member.guild, config.LEVELUP_CHANNEL)
    if channel is None:
        return
    text = f"🎉 {member.mention} ist jetzt **Level {level}**!"
    if new_role:
        text += f"\n🏅 Neuer Rang: {new_role.mention} – Respekt, weiter so! 🔥"
    upcoming = next_rank(level)
    if upcoming:
        text += f"\n-# Nächster Rang: **{upcoming[1]}** ab Level {upcoming[0]}"
    embed = discord.Embed(description=text, color=new_role.color if new_role else 0xF7931A)
    embed.set_thumbnail(url=member.display_avatar.url)
    try:
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
    except discord.HTTPException:
        pass


# --------------------------------------------------------------------------- #
# Cog
# --------------------------------------------------------------------------- #

class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_xp: dict[int, float] = {}

    async def cog_unload(self):
        self.voice_xp.cancel()

    @commands.Cog.listener()
    async def on_mancave_ready(self, guild: discord.Guild):
        if not self.voice_xp.is_running():
            self.voice_xp.start()
        await self.sync_ranks(guild)

    async def sync_ranks(self, guild: discord.Guild):
        """Vergibt fehlende Rang-Rollen passend zum Level (z. B. nach geänderten Level-Grenzen)."""
        for row in db.fetchall("SELECT user_id, xp FROM users WHERE xp > 0"):
            member = guild.get_member(row["user_id"])
            if member is None or member.bot:
                continue
            level, _ = level_from_xp(row["xp"])
            db.execute("UPDATE users SET level = ? WHERE user_id = ?", (level, member.id))
            if rank_for_level(level):
                await apply_rank_role(member, level)

    @commands.Cog.listener()
    async def on_mancave_message(self, message: discord.Message):
        member = message.author
        db.ensure_user(member.id)
        db.execute("UPDATE users SET messages = messages + 1 WHERE user_id = ?", (member.id,))

        if getattr(message.channel, "name", None) in config.XP_EXCLUDED_CHANNELS:
            return
        if len(message.content.strip()) < config.XP_MIN_MESSAGE_LENGTH and not message.attachments:
            return
        now = time.monotonic()
        if now - self.last_xp.get(member.id, 0) < config.XP_COOLDOWN_SECONDS:
            return
        self.last_xp[member.id] = now
        await grant_xp(member, random.randint(*config.XP_PER_MESSAGE))

    @tasks.loop(minutes=1)
    async def voice_xp(self):
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild is None:
            return
        for channel in guild.voice_channels:
            if guild.afk_channel and channel.id == guild.afk_channel.id:
                continue
            humans = [m for m in channel.members if not m.bot]
            if len(humans) < 2:
                continue
            for m in humans:
                if m.voice and (m.voice.self_deaf or m.voice.deaf):
                    continue
                db.ensure_user(m.id)
                db.execute("UPDATE users SET voice_minutes = voice_minutes + 1 WHERE user_id = ?", (m.id,))
                await grant_xp(m, config.XP_VOICE_PER_MINUTE)

    @voice_xp.error
    async def voice_xp_error(self, error):
        log.exception("Voice-XP-Fehler", exc_info=error)

    # ---------------------------------------------------------------- Commands

    @app_commands.command(name="rank", description="Zeigt Level, XP und Rang (deinen oder von jemand anderem)")
    @app_commands.describe(mitglied="Wessen Rang? (leer = deiner)")
    @app_commands.guild_only()
    async def rank(self, interaction: discord.Interaction, mitglied: discord.Member | None = None):
        member = mitglied or interaction.user
        db.ensure_user(member.id)
        row = db.fetchone("SELECT * FROM users WHERE user_id = ?", (member.id,))
        level, progress = level_from_xp(row["xp"])
        needed = xp_needed(level)
        position = db.scalar("SELECT COUNT(*) FROM users WHERE xp > ?", (row["xp"],)) + 1

        embed = discord.Embed(title=f"📈 {member.display_name}", color=member.color or 0xF7931A)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Level", value=f"**{level}**")
        embed.add_field(name="Platz", value=f"#{position}")
        embed.add_field(name="Gesamt-XP", value=f"{row['xp']:,}".replace(",", "."))
        embed.add_field(
            name=f"Fortschritt bis Level {level + 1}",
            value=f"{progress_bar(progress, needed)}  {progress:,}/{needed:,} XP".replace(",", "."),
            inline=False,
        )
        rank = rank_for_level(level)
        upcoming = next_rank(level)
        rank_text = f"Aktuell: **{rank or '–'}**"
        if upcoming:
            rank_text += f"\nNächster: **{upcoming[1]}** ab Level {upcoming[0]}"
        embed.add_field(name="Rang", value=rank_text, inline=False)
        embed.set_footer(text=f"💬 {row['messages']} Nachrichten · 🎙️ {row['voice_minutes']} Min. Voice")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Die Top 10 nach XP")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction):
        rows = db.fetchall("SELECT user_id, xp, level FROM users WHERE xp > 0 ORDER BY xp DESC LIMIT 10")
        if not rows:
            await interaction.response.send_message("Noch niemand hat XP gesammelt. Fang an zu schreiben! 💬")
            return
        lines = [
            f"{medal(i)} **{member_name(interaction.guild, r['user_id'])}** – Level {r['level']} · "
            f"{r['xp']:,} XP".replace(",", ".")
            for i, r in enumerate(rows)
        ]
        embed = discord.Embed(title="🏆 XP-Leaderboard", description="\n".join(lines), color=0xF7931A)
        own = db.fetchone("SELECT xp FROM users WHERE user_id = ?", (interaction.user.id,))
        if own:
            pos = db.scalar("SELECT COUNT(*) FROM users WHERE xp > ?", (own["xp"],)) + 1
            embed.set_footer(text=f"Dein Platz: #{pos}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="xp-geben", description="(Admin) XP geben oder abziehen")
    @app_commands.describe(mitglied="Wer?", menge="Menge (negativ = abziehen)")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def give_xp(self, interaction: discord.Interaction, mitglied: discord.Member, menge: int):
        level = await grant_xp(mitglied, menge)
        await interaction.response.send_message(
            f"✅ {mitglied.mention} {'+' if menge >= 0 else ''}{menge} XP → jetzt Level {level}.", ephemeral=True,
        )
        await send_log(interaction.guild, f"🛠️ {interaction.user.mention} hat {mitglied.mention} {menge} XP gegeben.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
