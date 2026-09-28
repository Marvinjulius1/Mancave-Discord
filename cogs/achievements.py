"""
Abzeichen (Achievements) & Profil.

Abzeichen werden automatisch aus den gespeicherten Daten berechnet (Nachrichten, Check-ins, Workouts, Schach,
Trading, ...). Geprüft wird nach jeder XP-Vergabe, nach Trades und regelmäßig für alle.
Neue Abzeichen werden in #level-ups angekündigt und geben Bonus-XP (config.XP_ACHIEVEMENT).

  /profil [mitglied]    -> Übersichtskarte: Rang, Serie, Gym, Schach, Trading, Abzeichen
  /abzeichen [mitglied] -> alle Abzeichen, freigeschaltet und gesperrt
"""

import sqlite3
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import db
from utils import best_streak_from_days, get_text_channel, log, now, streak_from_days

db.execute("""CREATE TABLE IF NOT EXISTS achievements (
    user_id     INTEGER NOT NULL,
    key         TEXT NOT NULL,
    unlocked_at TEXT,
    PRIMARY KEY (user_id, key)
)""")

# (Schlüssel, Emoji, Name, Beschreibung, Gruppe)
ACHIEVEMENTS = [
    # Aktivität
    ("first_message", "👋", "Hallo Welt", "Erste Nachricht geschrieben", "Aktivität"),
    ("messages_100", "💬", "Quasselstrippe", "100 Nachrichten geschrieben", "Aktivität"),
    ("messages_1000", "🗣️", "Stimme der Mancave", "1.000 Nachrichten geschrieben", "Aktivität"),
    ("voice_60", "🎙️", "Stammgast", "1 Stunde im Voice verbracht", "Aktivität"),
    ("voice_600", "🎧", "Voice-Veteran", "10 Stunden im Voice verbracht", "Aktivität"),
    ("level_10", "⭐", "Aufsteiger", "Level 10 erreicht", "Aktivität"),
    ("level_30", "🌟", "Elite", "Level 30 erreicht", "Aktivität"),
    # Check-ins
    ("first_checkin", "✅", "Der erste Schritt", "Ersten /checkin gemacht", "Disziplin"),
    ("streak_7", "🔥", "Eine Woche Disziplin", "7 Tage Check-in-Serie", "Disziplin"),
    ("streak_30", "💎", "Unaufhaltsam", "30 Tage Check-in-Serie", "Disziplin"),
    ("streak_100", "👑", "Legendäre Disziplin", "100 Tage Check-in-Serie", "Disziplin"),
    ("night_owl", "🦉", "Nachteule", "Check-in zwischen Mitternacht und 4 Uhr", "Disziplin"),
    ("early_bird", "🌅", "Frühaufsteher", "Check-in zwischen 4 und 6 Uhr morgens", "Disziplin"),
    # Gym
    ("first_workout", "🏋️", "Erstes Training", "Erstes Workout eingetragen", "Gym"),
    ("workouts_50", "💪", "Gym-Ratte", "50 Workouts eingetragen", "Gym"),
    ("workouts_100", "🦾", "100 Workouts", "100 Workouts eingetragen", "Gym"),
    ("workout_marathon", "⏱️", "Marathon-Einheit", "Ein Workout mit mind. 2 Stunden", "Gym"),
    # Community
    ("hall_of_fame", "🏆", "Hall of Fame", "Ein Win hat es in die Hall of Fame geschafft", "Community"),
    ("first_idea", "💡", "Ideengeber", "Erste Business-Idee gepitcht", "Community"),
    ("idea_hit", "🚀", "Volltreffer", "Eine Idee mit mind. 10 👍", "Community"),
    ("first_invite", "🤝", "Botschafter", "Jemanden in die Mancave eingeladen", "Community"),
    ("challenge_won", "🎯", "Challenge-Sieger", "Eine Challenge komplett durchgezogen", "Community"),
    # Schach
    ("chess_first_win", "♟️", "Erster Sieg", "Erste Schachpartie gewonnen", "Schach"),
    ("chess_quick_mate", "⚡", "Blitz-Matt", "Schachmatt in unter 20 Zügen", "Schach"),
    ("chess_wins_10", "♛", "Schach-Kenner", "10 Schachpartien gewonnen", "Schach"),
    # Trading-Spiel
    ("trade_first", "📈", "Erster Trade", "Ersten Trade im Trading-Spiel gemacht", "Trading"),
    ("trade_plus_10", "💰", "Im Plus", "Depot mit mind. +10 %", "Trading"),
    ("trade_double", "🤑", "Depot verdoppelt", "Depot mit mind. +100 %", "Trading"),
]
BY_KEY = {a[0]: a for a in ACHIEVEMENTS}
GROUP_ORDER = ["Aktivität", "Disziplin", "Gym", "Community", "Schach", "Trading"]

_last_check: dict[int, float] = {}
CHECK_INTERVAL = 30  # Sekunden – nicht bei jeder einzelnen XP-Vergabe alles neu berechnen


def _q(sql: str, params: tuple = (), default=0):
    """Abfrage, die 0 liefert, falls eine Tabelle (noch) nicht existiert."""
    try:
        return db.scalar(sql, params, default)
    except sqlite3.OperationalError:
        return default


def earned(user_id: int) -> set[str]:
    """Berechnet alle Abzeichen, die ein Mitglied laut Daten verdient hat."""
    got = set()
    u = db.fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
    msgs = u["messages"] if u else 0
    voice = u["voice_minutes"] if u else 0
    level = u["level"] if u else 0
    for key, cond in (("first_message", msgs >= 1), ("messages_100", msgs >= 100), ("messages_1000", msgs >= 1000),
                      ("voice_60", voice >= 60), ("voice_600", voice >= 600),
                      ("level_10", level >= 10), ("level_30", level >= 30)):
        if cond:
            got.add(key)

    rows = db.fetchall("SELECT day, created_at FROM checkins WHERE user_id = ?", (user_id,))
    if rows:
        got.add("first_checkin")
        best = max(best_streak_from_days([r["day"] for r in rows]), streak_from_days([r["day"] for r in rows]))
        for n in (7, 30, 100):
            if best >= n:
                got.add(f"streak_{n}")
        hours = [int(r["created_at"][11:13]) for r in rows if r["created_at"] and len(r["created_at"]) > 13]
        if any(0 <= h < 4 for h in hours):
            got.add("night_owl")
        if any(4 <= h < 6 for h in hours):
            got.add("early_bird")

    workouts = _q("SELECT COUNT(*) FROM workouts WHERE user_id = ?", (user_id,))
    if workouts >= 1:
        got.add("first_workout")
    if workouts >= 50:
        got.add("workouts_50")
    if workouts >= 100:
        got.add("workouts_100")
    if _q("SELECT MAX(minutes) FROM workouts WHERE user_id = ?", (user_id,)) >= 120:
        got.add("workout_marathon")

    if _q("SELECT COUNT(*) FROM hall_of_fame WHERE author_id = ?", (user_id,)):
        got.add("hall_of_fame")
    if _q("SELECT COUNT(*) FROM ideas WHERE author_id = ?", (user_id,)):
        got.add("first_idea")
    if _q("SELECT MAX(up) FROM ideas WHERE author_id = ?", (user_id,)) >= 10:
        got.add("idea_hit")
    if _q("SELECT COUNT(*) FROM invites WHERE inviter_id = ? AND left_guild = 0", (user_id,)):
        got.add("first_invite")
    if _q("SELECT COUNT(*) FROM challenge_participants WHERE user_id = ? AND completed = 1", (user_id,)):
        got.add("challenge_won")

    wins = _q("SELECT wins FROM chess_ratings WHERE user_id = ?", (user_id,))
    if wins >= 1:
        got.add("chess_first_win")
    if wins >= 10:
        got.add("chess_wins_10")
    try:
        mates = db.fetchall(
            "SELECT moves FROM chess_games WHERE status = 'finished' AND reason = 'checkmate' AND "
            "((result = '1-0' AND white_id = ?) OR (result = '0-1' AND black_id = ?))", (user_id, user_id))
        # "unter 20 Zügen" = der Gewinner hat weniger als 20 eigene Züge gebraucht (< 40 Halbzüge)
        if any(len(m["moves"].split()) < 40 for m in mates):
            got.add("chess_quick_mate")
    except sqlite3.OperationalError:
        pass

    if _q("SELECT COUNT(*) FROM trade_history WHERE user_id = ?", (user_id,)):
        got.add("trade_first")
    last_value = _q("SELECT last_value FROM trade_accounts WHERE user_id = ?", (user_id,), default=None)
    if last_value:
        start = config.TRADING_START_CASH
        if last_value >= start * 1.10:
            got.add("trade_plus_10")
        if last_value >= start * 2:
            got.add("trade_double")
    return got


def unlocked(user_id: int) -> dict[str, str]:
    return {r["key"]: r["unlocked_at"] for r in
            db.fetchall("SELECT key, unlocked_at FROM achievements WHERE user_id = ?", (user_id,))}


async def check_achievements(member: discord.Member, force: bool = False, announce: bool = True) -> list[str]:
    """Schaltet neu verdiente Abzeichen frei, kündigt sie an und gibt Bonus-XP. Gibt die neuen Schlüssel zurück."""
    if member.bot:
        return []
    t = time.monotonic()
    if not force and t - _last_check.get(member.id, 0) < CHECK_INTERVAL:
        return []
    _last_check[member.id] = t

    have = unlocked(member.id)
    new = [k for k in earned(member.id) if k not in have]
    if not new:
        return []
    stamp = now().isoformat()
    for key in new:
        db.execute("INSERT OR IGNORE INTO achievements(user_id, key, unlocked_at) VALUES (?, ?, ?)",
                   (member.id, key, stamp))

    if announce:
        channel = get_text_channel(member.guild, config.LEVELUP_CHANNEL)
        if channel:
            lines = [f"{BY_KEY[k][1]} **{BY_KEY[k][2]}** – {BY_KEY[k][3]}" for k in new]
            embed = discord.Embed(
                title="🏅 Neues Abzeichen!" if len(new) == 1 else f"🏅 {len(new)} neue Abzeichen!",
                description=f"{member.mention} hat freigeschaltet:\n" + "\n".join(lines),
                color=0xF1C40F)
            embed.set_thumbnail(url=member.display_avatar.url)
            total = len(have) + len(new)
            embed.set_footer(text=f"{total}/{len(ACHIEVEMENTS)} Abzeichen · /profil · /abzeichen")
            try:
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
            except discord.HTTPException:
                pass
        # Bonus-XP (grant_xp prüft danach erneut – der Zeitstempel oben verhindert eine Schleife)
        from cogs.leveling import grant_xp
        await grant_xp(member, config.XP_ACHIEVEMENT * len(new))
    return new


class Achievements(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_unload(self):
        self.sweep.cancel()

    @commands.Cog.listener()
    async def on_mancave_ready(self, guild: discord.Guild):
        if not self.sweep.is_running():
            self.sweep.start()

    @tasks.loop(minutes=15)
    async def sweep(self):
        """Regelmäßig alle prüfen (z. B. Einladungen, Hall of Fame, Ideen-Votes)."""
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild is None:
            return
        first_run = db.kv_get("achievements_initialized") is None
        for member in guild.members:
            if not member.bot:
                # Beim allerersten Durchlauf still nachtragen, damit #level-ups nicht zugespammt wird
                await check_achievements(member, force=True, announce=not first_run)
        if first_run:
            db.kv_set("achievements_initialized", now().isoformat())

    @sweep.error
    async def sweep_error(self, error):
        log.exception("Abzeichen-Prüfung fehlgeschlagen", exc_info=error)

    # ---------------------------------------------------------------- Befehle

    @app_commands.command(name="profil", description="Dein Mancave-Profil: Rang, Serie, Gym, Schach, Trading, Abzeichen")
    @app_commands.describe(mitglied="Wessen Profil? (leer = deins)")
    @app_commands.guild_only()
    async def profil(self, interaction: discord.Interaction, mitglied: discord.Member | None = None):
        from cogs.checkin import current_streak
        from cogs.leveling import level_from_xp, rank_for_level

        member = mitglied or interaction.user
        await check_achievements(member, force=True)
        db.ensure_user(member.id)
        u = db.fetchone("SELECT * FROM users WHERE user_id = ?", (member.id,))
        level, _ = level_from_xp(u["xp"])
        pos = db.scalar("SELECT COUNT(*) FROM users WHERE xp > ?", (u["xp"],)) + 1
        have = unlocked(member.id)

        embed = discord.Embed(title=f"🪪 {member.display_name}", color=member.color if member.color.value else 0xF7931A)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="📈 Level & Rang",
                        value=f"Level **{level}** · {rank_for_level(level) or config.ROLE_MEMBER}\n"
                              f"{u['xp']:,} XP · Platz #{pos}".replace(",", "."))
        best = best_streak_from_days([r["day"] for r in db.fetchall(
            "SELECT day FROM checkins WHERE user_id = ?", (member.id,))])
        embed.add_field(name="🔥 Disziplin", value=f"Serie: **{current_streak(member.id)}** Tage\nRekord: {best} Tage")
        workouts = _q("SELECT COUNT(*) FROM workouts WHERE user_id = ?", (member.id,))
        minutes = _q("SELECT SUM(minutes) FROM workouts WHERE user_id = ?", (member.id,))
        embed.add_field(name="🏋️ Gym", value=f"{workouts} Workouts\n{minutes // 60} Std. Training")
        elo = _q("SELECT elo FROM chess_ratings WHERE user_id = ?", (member.id,), default=None)
        wins = _q("SELECT wins FROM chess_ratings WHERE user_id = ?", (member.id,))
        embed.add_field(name="♟️ Schach", value=f"Elo {elo if elo else config.CHESS_START_ELO}\n{wins} Siege")
        value = _q("SELECT last_value FROM trade_accounts WHERE user_id = ?", (member.id,), default=None)
        if value:
            pct = (value - config.TRADING_START_CASH) / config.TRADING_START_CASH * 100
            trading = f"{value:,.0f} €\n{pct:+.1f} %".replace(",", ".")
        else:
            trading = "noch kein Depot"
        embed.add_field(name="📊 Trading-Spiel", value=trading)
        invites = _q("SELECT COUNT(*) FROM invites WHERE inviter_id = ? AND left_guild = 0", (member.id,))
        embed.add_field(name="🔗 Einladungen", value=str(invites))

        badges = " ".join(BY_KEY[k][1] for k in [a[0] for a in ACHIEVEMENTS] if k in have)
        embed.add_field(name=f"🏅 Abzeichen ({len(have)}/{len(ACHIEVEMENTS)})",
                        value=badges or "Noch keine – `/abzeichen` zeigt, was es gibt.", inline=False)
        if member.joined_at:
            embed.set_footer(text=f"Dabei seit {member.joined_at.strftime('%d.%m.%Y')}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="abzeichen", description="Alle Abzeichen – freigeschaltete und noch gesperrte")
    @app_commands.describe(mitglied="Wessen Abzeichen? (leer = deine)")
    @app_commands.guild_only()
    async def abzeichen(self, interaction: discord.Interaction, mitglied: discord.Member | None = None):
        member = mitglied or interaction.user
        await check_achievements(member, force=True)
        have = unlocked(member.id)
        embed = discord.Embed(title=f"🏅 Abzeichen von {member.display_name} ({len(have)}/{len(ACHIEVEMENTS)})",
                              color=0xF1C40F)
        for group in GROUP_ORDER:
            lines = []
            for key, emoji, name, desc, g in ACHIEVEMENTS:
                if g != group:
                    continue
                lines.append(f"{emoji} **{name}** – {desc}" if key in have else f"🔒 ~~{name}~~ – {desc}")
            embed.add_field(name=group, value="\n".join(lines), inline=False)
        embed.set_footer(text=f"Jedes Abzeichen gibt +{config.XP_ACHIEVEMENT} XP")
        await interaction.response.send_message(embed=embed, ephemeral=mitglied is None)


async def setup(bot: commands.Bot):
    await bot.add_cog(Achievements(bot))
