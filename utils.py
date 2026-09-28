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
    return perms.administrator or perms.manage_messages or any(r.name == config.ROLE_ADMIN for r in member.roles)


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
