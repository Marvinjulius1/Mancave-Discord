"""
Web-Dashboard (läuft im Bot-Prozess mit).

  http://<server>:<DASHBOARD_PORT>/        -> Dashboard
  http://<server>:<DASHBOARD_PORT>/api/data -> Rohdaten als JSON

.env:
  DASHBOARD_PORT=8080
  DASHBOARD_PASSWORD=geheim   -> Login im Browser (Benutzername egal)
Ohne Passwort ist das Dashboard nur lokal (127.0.0.1) erreichbar.
"""

import base64
import hmac
import os
from datetime import timedelta
from pathlib import Path

import discord
from aiohttp import web
from discord.ext import commands

import config
import db
from cogs.checkin import all_current_streaks
from utils import log, today, today_str, week_start

HTML_FILE = Path(__file__).resolve().parent.parent / "dashboard" / "index.html"


class Dashboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.runner: web.AppRunner | None = None
        self.password = os.getenv("DASHBOARD_PASSWORD", "")
        self.port = int(os.getenv("DASHBOARD_PORT", "8080"))

    async def cog_load(self):
        if not config.DASHBOARD_ENABLED:
            return
        app = web.Application(middlewares=[self.auth])
        app.router.add_get("/", self.index)
        app.router.add_get("/api/data", self.data)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        host = "0.0.0.0" if self.password else "127.0.0.1"
        try:
            await web.TCPSite(self.runner, host, self.port).start()
            log.info("Dashboard läuft auf http://%s:%s%s", host, self.port,
                     "" if self.password else " (nur lokal – DASHBOARD_PASSWORD setzen für Zugriff von außen)")
        except OSError as e:
            log.error("Dashboard konnte Port %s nicht öffnen: %s", self.port, e)

    async def cog_unload(self):
        if self.runner:
            await self.runner.cleanup()

    @web.middleware
    async def auth(self, request: web.Request, handler):
        if self.password:
            header = request.headers.get("Authorization", "")
            ok = False
            if header.startswith("Basic "):
                try:
                    _, _, pw = base64.b64decode(header[6:]).decode().partition(":")
                    ok = hmac.compare_digest(pw, self.password)
                except (ValueError, UnicodeDecodeError):
                    ok = False
            if not ok:
                return web.Response(status=401, text="Login erforderlich",
                                    headers={"WWW-Authenticate": 'Basic realm="Mancave Dashboard"'})
        return await handler(request)

    async def index(self, request: web.Request):
        return web.FileResponse(HTML_FILE, headers={"Cache-Control": "no-cache"})

    def _user(self, guild: discord.Guild | None, user_id: int) -> dict:
        member = guild.get_member(user_id) if guild else None
        return {
            "id": str(user_id),
            "name": member.display_name if member else f"User {user_id}",
            "avatar": member.display_avatar.url if member else None,
        }

    async def data(self, request: web.Request):
        guild = self.bot.get_guild(self.bot.guild_id)
        ws = week_start().isoformat()
        since30 = (today() - timedelta(days=29)).isoformat()

        leaderboard = [
            {**self._user(guild, r["user_id"]), "xp": r["xp"], "level": r["level"],
             "messages": r["messages"], "voice": r["voice_minutes"]}
            for r in db.fetchall("SELECT * FROM users WHERE xp > 0 ORDER BY xp DESC LIMIT 15")
        ]
        streaks = [{**self._user(guild, uid), "streak": s} for uid, s in all_current_streaks()[:10]]
        gym = [
            {**self._user(guild, r["user_id"]), "sessions": r["s"], "minutes": r["m"]}
            for r in db.fetchall(
                "SELECT user_id, COUNT(*) AS s, SUM(minutes) AS m FROM workouts WHERE day >= ? "
                "GROUP BY user_id ORDER BY m DESC LIMIT 10", (ws,))
        ]
        invites = [
            {**self._user(guild, r["inviter_id"]), "count": r["c"]}
            for r in db.fetchall(
                "SELECT inviter_id, COUNT(*) AS c FROM invites WHERE left_guild = 0 "
                "GROUP BY inviter_id ORDER BY c DESC LIMIT 10")
        ]
        ideas = [
            {"title": r["title"], "up": r["up"], "down": r["down"], "author": self._user(guild, r["author_id"])["name"]}
            for r in db.fetchall("SELECT * FROM ideas ORDER BY (up - down) DESC, up DESC LIMIT 5")
        ]
        hof = [
            {"content": r["content"], "reactions": r["reactions"], "day": (r["created_at"] or "")[:10],
             "author": self._user(guild, r["author_id"])["name"]}
            for r in db.fetchall("SELECT * FROM hall_of_fame ORDER BY created_at DESC LIMIT 5")
        ]
        challenges = [
            {"name": r["name"], "end": r["end_day"], "days": r["days"],
             "participants": db.scalar("SELECT COUNT(*) FROM challenge_participants WHERE challenge_id = ?", (r["id"],))}
            for r in db.fetchall("SELECT * FROM challenges WHERE active = 1")
        ]

        # Zeitreihen der letzten 30 Tage
        members_series = [dict(r) for r in db.fetchall(
            "SELECT day, members FROM member_stats WHERE day >= ? ORDER BY day", (since30,))]
        checkin_series = {r["day"]: r["c"] for r in db.fetchall(
            "SELECT day, COUNT(*) AS c FROM checkins WHERE day >= ? GROUP BY day", (since30,))}
        workout_series = {r["day"]: r["c"] for r in db.fetchall(
            "SELECT day, COUNT(*) AS c FROM workouts WHERE day >= ? GROUP BY day", (since30,))}
        days = [(today() - timedelta(days=29 - i)).isoformat() for i in range(30)]

        payload = {
            "server": {
                "name": guild.name if guild else config.SERVER_NAME,
                "icon": guild.icon.url if guild and guild.icon else None,
                "members": sum(1 for m in guild.members if not m.bot) if guild else 0,
                "online_voice": sum(len([m for m in c.members if not m.bot]) for c in guild.voice_channels) if guild else 0,
            },
            "totals": {
                "messages": db.scalar("SELECT SUM(messages) FROM users"),
                "voice_minutes": db.scalar("SELECT SUM(voice_minutes) FROM users"),
                "checkins_today": db.scalar("SELECT COUNT(*) FROM checkins WHERE day = ?", (today_str(),)),
                "checkins": db.scalar("SELECT COUNT(*) FROM checkins"),
                "workouts_week": db.scalar("SELECT COUNT(*) FROM workouts WHERE day >= ?", (ws,)),
                "workouts": db.scalar("SELECT COUNT(*) FROM workouts"),
                "ideas": db.scalar("SELECT COUNT(*) FROM ideas"),
                "hall_of_fame": db.scalar("SELECT COUNT(*) FROM hall_of_fame"),
                "open_tickets": db.scalar("SELECT COUNT(*) FROM tickets WHERE closed_at IS NULL"),
                "warnings": db.scalar("SELECT COUNT(*) FROM warnings"),
            },
            "leaderboard": leaderboard,
            "streaks": streaks,
            "gym": gym,
            "invites": invites,
            "ideas": ideas,
            "hall_of_fame": hof,
            "challenges": challenges,
            "series": {
                "days": days,
                "members": members_series,
                "checkins": [checkin_series.get(d, 0) for d in days],
                "workouts": [workout_series.get(d, 0) for d in days],
            },
        }
        return web.json_response(payload)


async def setup(bot: commands.Bot):
    await bot.add_cog(Dashboard(bot))
