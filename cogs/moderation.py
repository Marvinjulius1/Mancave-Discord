"""
Auto-Moderation & Mod-Befehle.

Automatisch (Admin / Mod und alle mit "Nachrichten verwalten" sind ausgenommen):
  - Spam (zu viele Nachrichten in kurzer Zeit / gleiche Nachricht mehrfach) -> löschen + Timeout
  - Fremde Discord-Einladungen, verbotene Wörter, Massen-Erwähnungen      -> löschen
  - Links erst ab Level config.LINK_MIN_LEVEL (stoppt Spam-Bots)

Befehle: /warn, /warnings, /warn-entfernen, /timeout, /untimeout, /clear
Alles wird in #bot-logs protokolliert.
"""

import re
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

import config
import db
from utils import is_mod, now, send_log

INVITE_RE = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/[\w-]+", re.I)
LINK_RE = re.compile(r"https?://([^\s/]+)", re.I)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.recent: dict[int, deque[float]] = defaultdict(deque)
        self.recent_content: dict[int, deque[tuple[float, str]]] = defaultdict(deque)

    # ------------------------------------------------------------ Auto-Mod

    async def check_message(self, message: discord.Message) -> bool:
        """Gibt True zurück, wenn die Nachricht entfernt wurde."""
        if not config.AUTOMOD_ENABLED or is_mod(message.author):
            return False
        reason = self._violation(message)
        if reason is None:
            return False
        action, text = reason
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        try:
            await message.channel.send(f"⚠️ {message.author.mention} {text}", delete_after=8,
                                       allowed_mentions=discord.AllowedMentions(users=True))
        except discord.HTTPException:
            pass
        if action == "timeout":
            try:
                await message.author.timeout(timedelta(minutes=config.SPAM_TIMEOUT_MINUTES), reason="Auto-Mod: Spam")
            except discord.HTTPException:
                pass
            self.recent[message.author.id].clear()
            self.recent_content[message.author.id].clear()
        await send_log(
            message.guild,
            f"🛡️ Auto-Mod ({action}): {message.author.mention} in {message.channel.mention} – {text}\n"
            f"> {discord.utils.escape_markdown(message.content[:300])}",
        )
        return True

    def _violation(self, message: discord.Message) -> tuple[str, str] | None:
        content = message.content
        lower = content.lower()
        author = message.author

        # Spam: zu viele Nachrichten in kurzer Zeit
        t = time.monotonic()
        stamps = self.recent[author.id]
        stamps.append(t)
        while stamps and t - stamps[0] > config.SPAM_INTERVAL_SECONDS:
            stamps.popleft()
        if len(stamps) > config.SPAM_MAX_MESSAGES:
            return "timeout", f"bitte nicht spammen. Timeout für {config.SPAM_TIMEOUT_MINUTES} Min."

        # Spam: gleiche Nachricht mehrfach
        if content:
            history = self.recent_content[author.id]
            history.append((t, lower))
            while history and t - history[0][0] > 60:
                history.popleft()
            if sum(1 for _, c in history if c == lower) > config.DUPLICATE_MAX:
                return "timeout", f"bitte nicht dieselbe Nachricht wiederholen. Timeout für {config.SPAM_TIMEOUT_MINUTES} Min."

        if config.BLOCK_INVITE_LINKS and INVITE_RE.search(content):
            return "delete", "Einladungen zu anderen Servern sind hier nicht erlaubt."

        if any(word in lower for word in config.BAD_WORDS):
            return "delete", "deine Nachricht enthielt ein nicht erlaubtes Wort."

        if len(message.mentions) + len(message.role_mentions) > config.MAX_MENTIONS:
            return "delete", "zu viele Erwähnungen in einer Nachricht."

        if config.LINK_MIN_LEVEL > 0:
            domains = [d.lower().removeprefix("www.") for d in LINK_RE.findall(content)]
            foreign = [d for d in domains
                       if not any(d == ok or d.endswith("." + ok) for ok in config.LINK_ALLOWED_DOMAINS)]
            if foreign:
                level = db.scalar("SELECT level FROM users WHERE user_id = ?", (author.id,))
                if level < config.LINK_MIN_LEVEL:
                    return "delete", (f"Links sind ab **Level {config.LINK_MIN_LEVEL}** freigeschaltet "
                                      f"(du bist Level {level}). Schreib mit, dann geht's schnell! 💬")
        return None

    # ------------------------------------------------------------ Befehle

    @app_commands.command(name="warn", description="(Mod) Mitglied verwarnen")
    @app_commands.describe(mitglied="Wer?", grund="Warum?")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warn(self, interaction: discord.Interaction, mitglied: discord.Member, grund: app_commands.Range[str, 3, 300]):
        db.execute("INSERT INTO warnings(user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?)",
                   (mitglied.id, interaction.user.id, grund, now().isoformat()))
        count = db.scalar("SELECT COUNT(*) FROM warnings WHERE user_id = ?", (mitglied.id,))
        text = f"⚠️ {mitglied.mention} wurde verwarnt ({count}. Verwarnung): {grund}"
        extra = ""
        if config.WARN_AUTO_TIMEOUT_AT and count >= config.WARN_AUTO_TIMEOUT_AT and count % config.WARN_AUTO_TIMEOUT_AT == 0:
            try:
                await mitglied.timeout(timedelta(minutes=config.WARN_AUTO_TIMEOUT_MINUTES),
                                       reason=f"{count} Verwarnungen")
                extra = f"\n⏱️ Automatischer Timeout: {config.WARN_AUTO_TIMEOUT_MINUTES} Min."
            except discord.HTTPException:
                extra = "\n⚠️ Timeout konnte nicht gesetzt werden (Rolle zu hoch?)."
        try:
            await mitglied.send(f"⚠️ Du wurdest in **{interaction.guild.name}** verwarnt: {grund}{extra}")
        except discord.HTTPException:
            pass
        await interaction.response.send_message(text + extra, ephemeral=True)
        await send_log(interaction.guild, f"{text} – von {interaction.user.mention}{extra}")

    @app_commands.command(name="warnings", description="(Mod) Verwarnungen eines Mitglieds anzeigen")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warnings(self, interaction: discord.Interaction, mitglied: discord.Member):
        rows = db.fetchall("SELECT * FROM warnings WHERE user_id = ? ORDER BY id DESC LIMIT 15", (mitglied.id,))
        if not rows:
            await interaction.response.send_message(f"✅ {mitglied.mention} hat keine Verwarnungen.", ephemeral=True)
            return
        lines = [f"`#{r['id']}` {r['created_at'][:10]} – {r['reason']} (von <@{r['moderator_id']}>)" for r in rows]
        embed = discord.Embed(title=f"⚠️ Verwarnungen: {mitglied.display_name}", description="\n".join(lines),
                              color=0xE67E22)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="warn-entfernen", description="(Mod) Verwarnung löschen")
    @app_commands.describe(nummer="Nummer aus /warnings")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def unwarn(self, interaction: discord.Interaction, nummer: int):
        row = db.fetchone("SELECT * FROM warnings WHERE id = ?", (nummer,))
        if row is None:
            await interaction.response.send_message("Diese Verwarnung gibt es nicht.", ephemeral=True)
            return
        db.execute("DELETE FROM warnings WHERE id = ?", (nummer,))
        await interaction.response.send_message(f"🗑️ Verwarnung #{nummer} entfernt.", ephemeral=True)
        await send_log(interaction.guild, f"🗑️ {interaction.user.mention} hat Verwarnung #{nummer} von <@{row['user_id']}> entfernt.")

    @app_commands.command(name="timeout", description="(Mod) Mitglied stummschalten")
    @app_commands.describe(mitglied="Wer?", minuten="Wie lange?", grund="Warum?")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def timeout(self, interaction: discord.Interaction, mitglied: discord.Member,
                      minuten: app_commands.Range[int, 1, 40320], grund: str = "Kein Grund angegeben"):
        try:
            await mitglied.timeout(timedelta(minutes=minuten), reason=f"{grund} (von {interaction.user})")
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Geht nicht: {e}", ephemeral=True)
            return
        await interaction.response.send_message(f"⏱️ {mitglied.mention} ist für {minuten} Min. stumm.", ephemeral=True)
        await send_log(interaction.guild, f"⏱️ {interaction.user.mention} → Timeout für {mitglied.mention} ({minuten} Min.): {grund}")

    @app_commands.command(name="untimeout", description="(Mod) Timeout aufheben")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def untimeout(self, interaction: discord.Interaction, mitglied: discord.Member):
        try:
            await mitglied.timeout(None, reason=f"Aufgehoben von {interaction.user}")
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Geht nicht: {e}", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ Timeout von {mitglied.mention} aufgehoben.", ephemeral=True)
        await send_log(interaction.guild, f"✅ {interaction.user.mention} hat den Timeout von {mitglied.mention} aufgehoben.")

    @app_commands.command(name="clear", description="(Mod) Nachrichten in diesem Kanal löschen")
    @app_commands.describe(anzahl="Wie viele (max. 100)?", mitglied="Nur Nachrichten von diesem Mitglied")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def clear(self, interaction: discord.Interaction, anzahl: app_commands.Range[int, 1, 100],
                    mitglied: discord.Member | None = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        remaining = [anzahl]

        def check(m: discord.Message) -> bool:
            if mitglied is None:
                return True
            if m.author.id == mitglied.id and remaining[0] > 0:
                remaining[0] -= 1
                return True
            return False

        try:
            deleted = await interaction.channel.purge(limit=anzahl if mitglied is None else 500, check=check,
                                                      bulk=True, reason=f"/clear von {interaction.user}")
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Fehler: {e}", ephemeral=True)
            return
        await interaction.followup.send(f"🧹 {len(deleted)} Nachrichten gelöscht.", ephemeral=True)
        await send_log(interaction.guild,
                       f"🧹 {interaction.user.mention} hat {len(deleted)} Nachrichten in {interaction.channel.mention} gelöscht"
                       + (f" (nur von {mitglied.mention})" if mitglied else "") + ".")


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
