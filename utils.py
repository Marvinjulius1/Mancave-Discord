"""Gemeinsame Hilfsfunktionen für bot.py und alle Cogs."""

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import discord

import config

log = logging.getLogger("mancave")
TZ = ZoneInfo(config.TIMEZONE)


# --------------------------------------------------------------------------- #
# Zeit (alles in deutscher Zeit, damit "heute" um Mitternacht wechselt)
# --------------------------------------------------------------------------- #

def now() -> datetime:
    return datetime.now(TZ)


def today() -> date:
    return now().date()


def today_str() -> str:
    return today().isoformat()


def week_start(day: date | None = None) -> date:
    """Montag der aktuellen (oder angegebenen) Woche."""
    day = day or today()
    return day - timedelta(days=day.weekday())


def streak_from_days(days: list[str]) -> int:
    """Aktuelle Serie aus einer Liste von ISO-Daten (heute oder gestern muss dabei sein)."""
    have = set(days)
    day = today()
    if day.isoformat() not in have:
        day -= timedelta(days=1)
        if day.isoformat() not in have:
            return 0
    streak = 0
    while day.isoformat() in have:
        streak += 1
        day -= timedelta(days=1)
    return streak


def best_streak_from_days(days: list[str]) -> int:
    best = cur = 0
    prev = None
    for d in sorted(date.fromisoformat(x) for x in set(days)):
        cur = cur + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, cur)
        prev = d
    return best


# --------------------------------------------------------------------------- #
# Discord
# --------------------------------------------------------------------------- #

def get_role(guild: discord.Guild, name: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=name)


def get_text_channel(guild: discord.Guild, name: str) -> discord.TextChannel | None:
    return discord.utils.get(guild.text_channels, name=name)


def is_mod(member: discord.Member) -> bool:
    perms = member.guild_permissions
    return perms.administrator or perms.manage_messages or any(r.name in config.TEAM_ROLES for r in member.roles)


async def send_log(guild: discord.Guild, text: str, **kwargs):
    """Schreibt eine Zeile in #bot-logs (falls vorhanden)."""
    log.info(text)
    channel = get_text_channel(guild, config.LOG_CHANNEL)
    if channel:
        try:
            await channel.send(text, allowed_mentions=discord.AllowedMentions.none(), **kwargs)
        except discord.HTTPException:
            pass


def progress_bar(value: float, total: float, length: int = 12) -> str:
    filled = 0 if total <= 0 else min(length, int(round(length * value / total)))
    return "▰" * filled + "▱" * (length - filled)


def member_name(guild: discord.Guild | None, user_id: int) -> str:
    member = guild.get_member(user_id) if guild else None
    return member.display_name if member else f"User {user_id}"


def medal(index: int) -> str:
    return ["🥇", "🥈", "🥉"][index] if index < 3 else f"`#{index + 1}`"


class SafeDict(dict):
    """Unbekannte {platzhalter} bleiben einfach stehen statt einen Fehler zu werfen."""

    def __missing__(self, key):
        return "{" + key + "}"


def bot_can_manage() -> discord.PermissionOverwrite:
    """Kanal-Rechte für den Bot in Kanälen, die er selbst verwaltet (z. B. Tickets)."""
    return discord.PermissionOverwrite(
        view_channel=True, send_messages=True, embed_links=True, attach_files=True,
        read_message_history=True, manage_messages=True, manage_channels=True, connect=True,
    )


# --------------------------------------------------------------------------- #
# Banner-Grafiken für Bot-Nachrichten (config.BANNERS)
# --------------------------------------------------------------------------- #

def _banner_path(key: str) -> str | None:
    import os
    rel = config.BANNERS.get(key)
    if not rel:
        return None
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)
    return path if os.path.isfile(path) else None


def banner_file(key: str) -> discord.File | None:
    """Banner als Datei-Anhang (im Embed per attachment://banner.png eingebunden)."""
    path = _banner_path(key)
    return discord.File(path, filename="banner.png") if path else None


def banner_hash(key: str) -> str:
    import hashlib
    path = _banner_path(key)
    if not path:
        return ""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def embeds_equal(a: discord.Embed, b: discord.Embed) -> bool:
    """Vergleicht zwei Embeds ohne Bild und Zeitstempel (die ändern sich beim Hochladen)."""
    da, db_ = a.to_dict(), b.to_dict()
    for d in (da, db_):
        d.pop("image", None)
        d.pop("timestamp", None)
    return da == db_


async def post_or_update(channel: discord.abc.Messageable, existing: discord.Message | None, embed: discord.Embed,
                         banner_key: str | None = None, view=discord.utils.MISSING,
                         force: bool = False) -> discord.Message:
    """Postet eine Bot-Nachricht mit Banner oder aktualisiert die vorhandene – nur wenn sich etwas geändert hat.
    Das Banner wird nur neu hochgeladen, wenn sich die Bilddatei geändert hat."""
    import db  # hier importiert, damit utils ohne Datenbank nutzbar bleibt

    file = banner_file(banner_key) if banner_key else None
    if file:
        embed.set_image(url="attachment://banner.png")
    current = banner_hash(banner_key) if banner_key else ""

    if existing is None:
        kwargs = {"embed": embed}
        if file:
            kwargs["file"] = file
        if view is not discord.utils.MISSING:
            kwargs["view"] = view
        message = await channel.send(**kwargs)
        db.kv_set(f"banner:{message.id}", current)
        return message

    banner_changed = db.kv_get(f"banner:{existing.id}", "") != current
    if force or banner_changed or not existing.embeds or not embeds_equal(existing.embeds[0], embed):
        kwargs = {"embed": embed}
        if view is not discord.utils.MISSING:
            kwargs["view"] = view
        if banner_changed:
            kwargs["attachments"] = [file] if file else []
        await existing.edit(**kwargs)
        db.kv_set(f"banner:{existing.id}", current)
    return existing
