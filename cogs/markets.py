"""
Krypto- & Aktienkurse.

  /kurs BTC | /kurs AAPL | /kurs Apple  -> aktueller Kurs
  Jeden Morgen                           -> Markt-Report in #krypto (täglich) und #aktien (Mo–Fr)
  /marktbericht (Admin)                  -> Report sofort posten

Datenquellen ohne API-Key: CoinGecko (Krypto) und Yahoo Finance (Aktien, Indizes, ETFs).
"""

from datetime import time as dtime

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils import TZ, get_text_channel, log, now, today

COINGECKO = "https://api.coingecko.com/api/v3"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (MancaveBot)"}
DISCLAIMER = "Keine Finanzberatung · Daten: {source}"


class MarketError(Exception):
    pass


def fmt_price(value: float | None, currency: str = "EUR") -> str:
    if value is None:
        return "–"
    symbol = {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency.upper(), currency.upper())
    if value >= 1000:
        text = f"{value:,.2f}"
    elif value >= 1:
        text = f"{value:,.2f}"
    elif value >= 0.01:
        text = f"{value:,.4f}"
    else:
        text = f"{value:,.8f}".rstrip("0")
    # deutsches Format: 1.234,56
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} {symbol}"


def fmt_change(pct: float | None) -> str:
    if pct is None:
        return "–"
    arrow = "🟢 ▲" if pct >= 0 else "🔴 ▼"
    return f"{arrow} {pct:+.2f} %".replace(".", ",")


def fmt_big(value: float | None, currency: str = "EUR") -> str:
    if not value:
        return "–"
    for div, unit in ((1e12, "Bio."), (1e9, "Mrd."), (1e6, "Mio.")):
        if value >= div:
            return f"{value / div:.2f} {unit} {currency.upper()}".replace(".", ",", 1)
    return fmt_price(value, currency)


class Markets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15), trust_env=True)

    async def cog_unload(self):
        self.daily_report.cancel()
        if self.session:
            await self.session.close()

    @commands.Cog.listener()
    async def on_mancave_ready(self, guild: discord.Guild):
        if config.MARKET_REPORT_ENABLED and not self.daily_report.is_running():
            self.daily_report.start()

    # ------------------------------------------------------------ Datenabruf

    async def _get_json(self, url: str, params: dict | None = None):
        async with self.session.get(url, params=params) as resp:
            if resp.status == 429:
                raise MarketError("Die Kurs-API ist gerade überlastet. Versuch es in einer Minute nochmal.")
            if resp.status != 200:
                raise MarketError(f"Kurs-API antwortet mit Fehler {resp.status}.")
            return await resp.json(content_type=None)

    async def crypto_markets(self, ids: list[str]) -> list[dict]:
        data = await self._get_json(f"{COINGECKO}/coins/markets", {
            "vs_currency": config.CRYPTO_CURRENCY,
            "ids": ",".join(ids),
            "price_change_percentage": "24h,7d",
        })
        order = {cid: i for i, cid in enumerate(ids)}
        return sorted(data, key=lambda c: order.get(c["id"], 99))

    async def resolve_crypto(self, query: str) -> str | None:
        symbol = query.upper()
        if symbol in config.CRYPTO_SYMBOLS:
            return config.CRYPTO_SYMBOLS[symbol]
        data = await self._get_json(f"{COINGECKO}/search", {"query": query})
        coins = data.get("coins", [])
        exact = [c for c in coins if c.get("symbol", "").upper() == symbol or c.get("name", "").lower() == query.lower()]
        pick = (exact or coins or [None])[0]
        return pick["id"] if pick else None

    async def stock_quote(self, symbol: str) -> dict | None:
        try:
            data = await self._get_json(YAHOO_CHART.format(symbol=symbol), {"range": "1d", "interval": "1d"})
        except MarketError:
            return None
        result = (data.get("chart") or {}).get("result")
        if not result:
            return None
        meta = result[0]["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is None:
            return None
        return {
            "symbol": meta.get("symbol", symbol),
            "name": (meta.get("longName") or meta.get("shortName") or symbol).strip(),
            "price": price,
            "prev": prev,
            "change": (price - prev) / prev * 100 if prev else None,
            "currency": meta.get("currency") or "USD",
            "high": meta.get("regularMarketDayHigh"),
            "low": meta.get("regularMarketDayLow"),
            "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
        }

    async def search_stock(self, query: str) -> str | None:
        try:
            data = await self._get_json(YAHOO_SEARCH, {"q": query, "quotesCount": 5, "newsCount": 0})
        except MarketError:
            return None
        quotes = [q for q in data.get("quotes", []) if q.get("quoteType") in ("EQUITY", "ETF", "INDEX", "MUTUALFUND")]
        return quotes[0]["symbol"] if quotes else None

    # ------------------------------------------------------------ Embeds

    def crypto_embed(self, coin: dict) -> discord.Embed:
        cur = config.CRYPTO_CURRENCY.upper()
        embed = discord.Embed(
            title=f"🪙 {coin['name']} ({coin['symbol'].upper()})",
            description=f"## {fmt_price(coin['current_price'], cur)}",
            color=0xF7931A,
            timestamp=now(),
        )
        embed.set_thumbnail(url=coin.get("image"))
        embed.add_field(name="24 h", value=fmt_change(coin.get("price_change_percentage_24h_in_currency")))
        embed.add_field(name="7 Tage", value=fmt_change(coin.get("price_change_percentage_7d_in_currency")))
        embed.add_field(name="Rang", value=f"#{coin.get('market_cap_rank') or '–'}")
        embed.add_field(name="24h Hoch / Tief",
                        value=f"{fmt_price(coin.get('high_24h'), cur)} / {fmt_price(coin.get('low_24h'), cur)}")
        embed.add_field(name="Marktkapitalisierung", value=fmt_big(coin.get("market_cap"), cur))
        embed.add_field(name="Allzeithoch", value=fmt_price(coin.get("ath"), cur))
        embed.set_footer(text=DISCLAIMER.format(source="CoinGecko"))
        return embed

    def stock_embed(self, q: dict) -> discord.Embed:
        embed = discord.Embed(
            title=f"📈 {q['name']} ({q['symbol']})",
            description=f"## {fmt_price(q['price'], q['currency'])}",
            color=0x2ECC71 if (q["change"] or 0) >= 0 else 0xE74C3C,
            timestamp=now(),
        )
        embed.add_field(name="Heute", value=fmt_change(q["change"]))
        embed.add_field(name="Vortag", value=fmt_price(q["prev"], q["currency"]))
        embed.add_field(name="Börse", value=q["exchange"] or "–")
        embed.add_field(name="Tageshoch / -tief",
                        value=f"{fmt_price(q['high'], q['currency'])} / {fmt_price(q['low'], q['currency'])}")
        embed.set_footer(text=DISCLAIMER.format(source="Yahoo Finance (ggf. verzögert)"))
        return embed

    # ------------------------------------------------------------ /kurs

    @app_commands.command(name="kurs", description="Aktueller Kurs von Krypto, Aktien, ETFs oder Indizes")
    @app_commands.describe(symbol="z. B. BTC, ETH, AAPL, TSLA, ^GDAXI oder ein Name wie 'Apple'",
                           markt="Automatisch erkennen oder festlegen")
    @app_commands.choices(markt=[
        app_commands.Choice(name="Automatisch", value="auto"),
        app_commands.Choice(name="Krypto", value="krypto"),
        app_commands.Choice(name="Aktie / ETF / Index", value="aktie"),
    ])
    async def kurs(self, interaction: discord.Interaction, symbol: app_commands.Range[str, 1, 40],
                   markt: str = "auto"):
        await interaction.response.defer(thinking=True)
        query = symbol.strip()
        try:
            embed = await self.lookup(query, markt)
        except MarketError as e:
            await interaction.followup.send(f"⚠️ {e}")
            return
        except aiohttp.ClientError:
            log.exception("Kurs-Abruf fehlgeschlagen")
            await interaction.followup.send("⚠️ Kurs-Dienst gerade nicht erreichbar. Versuch es später nochmal.")
            return
        if embed is None:
            await interaction.followup.send(f"🤷 Nichts gefunden für **{query}**. Probier das Börsenkürzel (z. B. `AAPL`, `BTC`).")
            return
        await interaction.followup.send(embed=embed)

    async def lookup(self, query: str, markt: str) -> discord.Embed | None:
        upper = query.upper()
        # 1) Bekannte Krypto-Kürzel direkt
        if markt in ("auto", "krypto") and upper in config.CRYPTO_SYMBOLS:
            coins = await self.crypto_markets([config.CRYPTO_SYMBOLS[upper]])
            return self.crypto_embed(coins[0]) if coins else None
        # 2) Aktie über Symbol, dann über Namenssuche
        if markt in ("auto", "aktie"):
            quote = await self.stock_quote(upper)
            if quote is None:
                found = await self.search_stock(query)
                quote = await self.stock_quote(found) if found else None
            if quote:
                return self.stock_embed(quote)
        # 3) Krypto über Suche
        if markt in ("auto", "krypto"):
            coin_id = await self.resolve_crypto(query)
            if coin_id:
                coins = await self.crypto_markets([coin_id])
                return self.crypto_embed(coins[0]) if coins else None
        return None

    # ------------------------------------------------------------ Markt-Report

    async def build_crypto_report(self) -> discord.Embed:
        coins = await self.crypto_markets(config.CRYPTO_REPORT_COINS)
        cur = config.CRYPTO_CURRENCY.upper()
        lines = [
            f"**{c['symbol'].upper()}** {fmt_price(c['current_price'], cur)} · "
            f"{fmt_change(c.get('price_change_percentage_24h_in_currency'))}"
            for c in coins
        ]
        best = max(coins, key=lambda c: c.get("price_change_percentage_24h_in_currency") or -999)
        embed = discord.Embed(
            title=f"☀️ Krypto-Morgenreport · {today().strftime('%d.%m.%Y')}",
            description="\n".join(lines) + f"\n\n🚀 Top-Performer (24 h): **{best['name']}**",
            color=0xF7931A,
            timestamp=now(),
        )
        embed.set_footer(text=DISCLAIMER.format(source="CoinGecko"))
        return embed

    async def build_stock_report(self) -> discord.Embed:
        lines = []
        for symbol, name in config.STOCK_REPORT_SYMBOLS.items():
            q = await self.stock_quote(symbol)
            if q:
                lines.append(f"**{name}** {fmt_price(q['price'], q['currency'])} · {fmt_change(q['change'])}")
        embed = discord.Embed(
            title=f"☀️ Aktien-Morgenreport · {today().strftime('%d.%m.%Y')}",
            description="\n".join(lines) or "Keine Daten verfügbar.",
            color=0x2ECC71,
            timestamp=now(),
        )
        embed.set_footer(text=DISCLAIMER.format(source="Yahoo Finance · Schlusskurse bzw. letzter Stand"))
        return embed

    async def post_reports(self, guild: discord.Guild, force_stocks: bool = False) -> list[str]:
        posted = []
        crypto_ch = get_text_channel(guild, config.CRYPTO_CHANNEL)
        if crypto_ch:
            try:
                await crypto_ch.send(embed=await self.build_crypto_report())
                posted.append(crypto_ch.mention)
            except (MarketError, aiohttp.ClientError) as e:
                log.warning("Krypto-Report fehlgeschlagen: %s", e)
        stocks_ch = get_text_channel(guild, config.STOCKS_CHANNEL)
        if stocks_ch and (force_stocks or today().weekday() < 5):
            try:
                await stocks_ch.send(embed=await self.build_stock_report())
                posted.append(stocks_ch.mention)
            except (MarketError, aiohttp.ClientError) as e:
                log.warning("Aktien-Report fehlgeschlagen: %s", e)
        return posted

    @tasks.loop(time=dtime(*config.MARKET_REPORT_TIME, tzinfo=TZ))
    async def daily_report(self):
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild:
            await self.post_reports(guild)

    @daily_report.error
    async def daily_report_error(self, error):
        log.exception("Markt-Report fehlgeschlagen", exc_info=error)

    @app_commands.command(name="marktbericht", description="(Admin) Markt-Report jetzt posten")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def marktbericht(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        posted = await self.post_reports(interaction.guild, force_stocks=True)
        await interaction.followup.send(
            f"✅ Gepostet in {', '.join(posted)}." if posted else "⚠️ Konnte keinen Report posten.", ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Markets(bot))
