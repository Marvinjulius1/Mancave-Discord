"""
Automatische News in drei Kanälen: #politik-news, #börsen-news, #krypto-news.

Der Bot liest RSS-Feeds (config.NEWS_FEEDS) und postet zu den Uhrzeiten aus config.NEWS_TIMES
ein Briefing mit den neuesten Schlagzeilen. Bereits gepostete Meldungen werden nie doppelt gepostet.

  /news-jetzt (Admin) -> Briefing sofort posten
"""

import asyncio
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
from email.utils import parsedate_to_datetime

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import db
from utils import TZ, get_text_channel, log, now

# Manche Nachrichtenseiten blocken User-Agents mit "Bot" – daher ein normales Browser-Kennzeichen
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
}
TITLES = {
    config.NEWS_POLITICS_CHANNEL: ("🏛️", "Politik", 0x3498DB),
    config.NEWS_MARKETS_CHANNEL: ("📈", "Börse & Wirtschaft", 0x2ECC71),
    config.NEWS_CRYPTO_CHANNEL: ("🪙", "Krypto", 0xF7931A),
}

db.execute("CREATE TABLE IF NOT EXISTS news_posted (link TEXT PRIMARY KEY, posted_at TEXT)")


def _text(el, *names) -> str:
    for name in names:
        found = el.find(name)
        if found is not None:
            if found.text:
                return found.text.strip()
            if found.get("href"):
                return found.get("href").strip()
    return ""


def _date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_feed(xml_text: str, source: str) -> list[dict]:
    """RSS 2.0 und Atom -> [{title, link, date, source}]"""
    root = ET.fromstring(xml_text)
    atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall(".//item") or root.findall(f".//{atom}entry")
    result = []
    for it in items:
        title = _text(it, "title", f"{atom}title")
        link = _text(it, "link", f"{atom}link")
        date = _date(_text(it, "pubDate", f"{atom}published", f"{atom}updated",
                           "{http://purl.org/dc/elements/1.1/}date"))
        title = html.unescape(re.sub(r"<[^>]+>", "", title)).strip()
        if title and link:
            result.append({"title": title, "link": link, "date": date, "source": source})
    return result


class News(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20), trust_env=True)

    async def cog_unload(self):
        self.briefing.cancel()
        if self.session:
            await self.session.close()

    @commands.Cog.listener()
    async def on_mancave_ready(self, guild: discord.Guild):
        if not self.briefing.is_running():
            self.briefing.start()
        # Beim allerersten Start sofort ein Briefing, damit die Kanäle nicht leer sind
        if db.kv_get("news_first_briefing") is None:
            db.kv_set("news_first_briefing", now().isoformat())
            result = await self.post_briefings(guild)
            log.info("Erstes News-Briefing gepostet: %s", result)

    async def fetch(self, source: str, url: str) -> list[dict]:
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    log.warning("News-Feed %s antwortet mit %s", source, resp.status)
                    return []
                return parse_feed(await resp.text(), source)
        except (aiohttp.ClientError, asyncio.TimeoutError, ET.ParseError) as e:
            log.warning("News-Feed %s nicht lesbar: %s", source, e)
            return []

    async def collect(self, channel_name: str) -> list[dict]:
        """Neue, noch nicht gepostete Meldungen – abwechselnd aus allen Quellen, neueste zuerst."""
        feeds = config.NEWS_FEEDS.get(channel_name, [])
        results = await asyncio.gather(*(self.fetch(name, url) for name, url in feeds))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=config.NEWS_MAX_AGE_HOURS)
        per_source = []
        for items in results:
            fresh = [i for i in items
                     if (i["date"] is None or i["date"] >= cutoff)
                     and not db.fetchone("SELECT 1 FROM news_posted WHERE link = ?", (i["link"],))]
            fresh.sort(key=lambda i: i["date"] or cutoff, reverse=True)
            per_source.append(fresh)
        # Reißverschluss: 1. von jeder Quelle, dann 2. von jeder ... -> Mischung statt nur einer Quelle
        mixed, seen_titles = [], set()
        for rank in range(max((len(p) for p in per_source), default=0)):
            for items in per_source:
                if rank < len(items) and items[rank]["title"].lower() not in seen_titles:
                    seen_titles.add(items[rank]["title"].lower())
                    mixed.append(items[rank])
        return mixed[:config.NEWS_ITEMS_PER_BRIEFING]

    def build_embed(self, channel_name: str, items: list[dict]) -> discord.Embed:
        emoji, label, color = TITLES.get(channel_name, ("📰", channel_name, 0x95A5A6))
        part = "Morgen-Briefing" if now().hour < 12 else "Abend-Briefing"
        lines = []
        for i in items:
            when = i["date"].astimezone(TZ).strftime("%H:%M") if i["date"] else ""
            title = i["title"].replace("[", "(").replace("]", ")")
            lines.append(f"**[{title}]({i['link']})**\n-# {i['source']}" + (f" · {when} Uhr" if when else ""))
        description = ""
        for line in lines:  # Discord-Limit: 4096 Zeichen
            if len(description) + len(line) + 2 > 4000:
                break
            description += line + "\n\n"
        embed = discord.Embed(
            title=f"{emoji} {label} – {part} · {now().strftime('%d.%m.%Y')}",
            description=description.strip(),
            color=color,
            timestamp=now(),
        )
        sources = ", ".join(name for name, _ in config.NEWS_FEEDS.get(channel_name, []))
        footer = f"Quellen: {sources}"
        if channel_name != config.NEWS_POLITICS_CHANNEL:
            footer += " · Keine Finanzberatung"
        embed.set_footer(text=footer)
        return embed

    async def post_briefings(self, guild: discord.Guild) -> dict[str, int]:
        posted = {}
        for channel_name in config.NEWS_FEEDS:
            channel = get_text_channel(guild, channel_name)
            if channel is None:
                continue
            items = await self.collect(channel_name)
            if not items:
                posted[channel_name] = 0
                continue
            try:
                await channel.send(embed=self.build_embed(channel_name, items))
            except discord.HTTPException as e:
                log.warning("News-Post in #%s fehlgeschlagen: %s", channel_name, e)
                continue
            stamp = now().isoformat()
            for i in items:
                db.execute("INSERT OR IGNORE INTO news_posted(link, posted_at) VALUES (?, ?)", (i["link"], stamp))
            posted[channel_name] = len(items)
        # Alte Einträge aufräumen
        db.execute("DELETE FROM news_posted WHERE posted_at < ?", ((now() - timedelta(days=14)).isoformat(),))
        return posted

    @tasks.loop(time=[dtime(h, m, tzinfo=TZ) for h, m in config.NEWS_TIMES])
    async def briefing(self):
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild:
            result = await self.post_briefings(guild)
            log.info("News-Briefing gepostet: %s", result)

    @briefing.error
    async def briefing_error(self, error):
        log.exception("News-Briefing fehlgeschlagen", exc_info=error)

    @app_commands.command(name="news-jetzt", description="(Admin) News-Briefing sofort posten")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def news_now(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self.post_briefings(interaction.guild)
        text = "\n".join(f"#{name}: {count} Meldung(en)" for name, count in result.items()) or "Keine News-Kanäle gefunden."
        await interaction.followup.send(f"📰 Gepostet:\n{text}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(News(bot))
