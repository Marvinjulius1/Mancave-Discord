"""
Trading-Spiel mit Spielgeld – echte Kurse, kein echtes Risiko.

Jeder startet mit config.TRADING_START_CASH € virtuellem Geld und handelt Krypto, Aktien, ETFs und Indizes
zu echten Kursen (CoinGecko / Yahoo Finance, alles in € umgerechnet).

  /kaufen BTC 500          -> für 500 € kaufen
  /verkaufen BTC [anteil]  -> ganz oder teilweise verkaufen (Anteil in %)
  /depot [mitglied]        -> Depot mit Gewinn/Verlust
  /trading-rangliste       -> wer hat das beste Depot?
  /trading-reset           -> Neustart mit Startkapital (max. 1× pro Woche)

Kein Echtgeld, keine Finanzberatung.
"""

import asyncio
import time
from datetime import datetime, timedelta

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import config
import db
from cogs.markets import COINGECKO, YAHOO_CHART, MarketError, fmt_change, fmt_price
from utils import log, medal, member_name, now

db.execute("""CREATE TABLE IF NOT EXISTS trade_accounts (
    user_id    INTEGER PRIMARY KEY,
    cash       REAL NOT NULL,
    last_value REAL,
    resets     INTEGER NOT NULL DEFAULT 0,
    reset_at   TEXT,
    created_at TEXT
)""")
db.execute("""CREATE TABLE IF NOT EXISTS trade_positions (
    user_id   INTEGER NOT NULL,
    kind      TEXT NOT NULL,      -- 'krypto' oder 'aktie'
    asset_key TEXT NOT NULL,      -- CoinGecko-ID bzw. Yahoo-Symbol
    symbol    TEXT NOT NULL,      -- Anzeige, z. B. BTC oder AAPL
    name      TEXT,
    qty       REAL NOT NULL,
    cost      REAL NOT NULL,      -- insgesamt investierte € (für Einstandskurs)
    PRIMARY KEY (user_id, kind, asset_key)
)""")
db.execute("""CREATE TABLE IF NOT EXISTS trade_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    side       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    asset_key  TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    qty        REAL NOT NULL,
    price_eur  REAL NOT NULL,
    value_eur  REAL NOT NULL,
    profit_eur REAL,
    created_at TEXT
)""")

PRICE_TTL = 60          # Sekunden – Kurse kurz zwischenspeichern (schont die Kurs-APIs)
FX_TTL = 600
DISCLAIMER = "Spielgeld · echte Kurse (evtl. verzögert) · keine Finanzberatung"


def eur(value: float) -> str:
    return fmt_price(value, "EUR")


def fmt_qty(qty: float) -> str:
    text = f"{qty:,.8f}".rstrip("0").rstrip(".") if qty < 1 else f"{qty:,.4f}".rstrip("0").rstrip(".")
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def account(user_id: int):
    db.execute("INSERT OR IGNORE INTO trade_accounts(user_id, cash, created_at) VALUES (?, ?, ?)",
               (user_id, config.TRADING_START_CASH, now().isoformat()))
    return db.fetchone("SELECT * FROM trade_accounts WHERE user_id = ?", (user_id,))


class TradingGame(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.price_cache: dict[tuple[str, str], tuple[float, float]] = {}
        self.fx_cache: dict[str, tuple[float, float]] = {}

    @property
    def markets(self):
        mk = self.bot.get_cog("Markets")
        if mk is None:
            raise MarketError("Das Kurs-Modul ist nicht geladen.")
        return mk

    # ---------------------------------------------------------------- Kurse

    async def fx_to_eur(self, currency: str) -> float:
        raw = currency or "EUR"
        factor = 1.0
        if raw in ("GBp", "GBX"):          # Londoner Kurse in Pence
            raw, factor = "GBP", 0.01
        currency = raw.upper()
        if currency == "EUR":
            return factor
        hit = self.fx_cache.get(currency)
        if hit and time.monotonic() - hit[1] < FX_TTL:
            return hit[0] * factor
        data = await self.markets._get_json(YAHOO_CHART.format(symbol=f"{currency}EUR=X"),
                                            {"range": "1d", "interval": "1d"})
        rate = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        self.fx_cache[currency] = (rate, time.monotonic())
        return rate * factor

    async def prices_eur(self, assets: list[tuple[str, str]]) -> dict[tuple[str, str], float]:
        """Aktuelle Kurse in € für [(kind, key)] – Krypto gebündelt in einer Anfrage."""
        result, missing = {}, []
        for a in set(assets):
            hit = self.price_cache.get(a)
            if hit and time.monotonic() - hit[1] < PRICE_TTL:
                result[a] = hit[0]
            else:
                missing.append(a)
        crypto = [key for kind, key in missing if kind == "krypto"]
        if crypto:
            data = {}
            try:
                data = await self.markets._get_json(f"{COINGECKO}/simple/price",
                                                    {"ids": ",".join(crypto), "vs_currencies": "eur"})
            except (MarketError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                log.info("CoinGecko nicht verfügbar (%s) – nutze Yahoo Finance als Ersatz", e)
            for key in crypto:
                if key in data and "eur" in data[key]:
                    result[("krypto", key)] = float(data[key]["eur"])
                else:
                    price = await self.crypto_price_yahoo(key)
                    if price:
                        result[("krypto", key)] = price
        for kind, key in missing:
            if kind != "aktie":
                continue
            quote = await self.markets.stock_quote(key)
            if quote:
                result[("aktie", key)] = quote["price"] * await self.fx_to_eur(quote["currency"])
        for a, p in result.items():
            self.price_cache[a] = (p, time.monotonic())
        return result

    async def crypto_price_yahoo(self, coin_id: str) -> float | None:
        """Ersatz, wenn CoinGecko drosselt: Yahoo-Paar wie BTC-EUR."""
        symbol = next((s for s, cid in config.CRYPTO_SYMBOLS.items() if cid == coin_id), None)
        if symbol is None:
            row = db.fetchone("SELECT symbol FROM trade_positions WHERE kind = 'krypto' AND asset_key = ? LIMIT 1",
                              (coin_id,))
            symbol = row["symbol"] if row else None
        if symbol is None:
            return None
        quote = await self.markets.stock_quote(f"{symbol.upper()}-EUR")
        if quote is None:
            return None
        return quote["price"] * await self.fx_to_eur(quote["currency"])

    async def resolve(self, query: str, markt: str) -> dict | None:
        """Findet ein handelbares Asset: {kind, key, symbol, name}."""
        mk = self.markets
        upper = query.strip().upper()
        if markt in ("auto", "krypto") and upper in config.CRYPTO_SYMBOLS:
            cid = config.CRYPTO_SYMBOLS[upper]
            return {"kind": "krypto", "key": cid, "symbol": upper, "name": cid.replace("-", " ").title()}
        if markt in ("auto", "aktie"):
            quote = await mk.stock_quote(upper)
            if quote is None:
                found = await mk.search_stock(query)
                quote = await mk.stock_quote(found) if found else None
            if quote:
                return {"kind": "aktie", "key": quote["symbol"], "symbol": quote["symbol"], "name": quote["name"]}
        if markt in ("auto", "krypto"):
            cid = await mk.resolve_crypto(query)
            if cid:
                coins = await mk.crypto_markets([cid])
                if coins:
                    c = coins[0]
                    return {"kind": "krypto", "key": cid, "symbol": c["symbol"].upper(), "name": c["name"]}
        return None

    async def depot_value(self, user_id: int) -> tuple[float, list[dict]]:
        acc = account(user_id)
        positions = [dict(p) for p in db.fetchall("SELECT * FROM trade_positions WHERE user_id = ?", (user_id,))]
        prices = await self.prices_eur([(p["kind"], p["asset_key"]) for p in positions]) if positions else {}
        total = acc["cash"]
        for p in positions:
            price = prices.get((p["kind"], p["asset_key"]))
            p["price"] = price
            p["value"] = p["qty"] * price if price is not None else p["cost"]  # ohne Kurs: Einstand
            total += p["value"]
        db.execute("UPDATE trade_accounts SET last_value = ? WHERE user_id = ?", (total, user_id))
        return total, positions

    async def after_trade(self, member: discord.Member):
        try:
            from cogs.achievements import check_achievements
            await check_achievements(member, force=True)
        except Exception:
            log.exception("Abzeichen-Prüfung nach Trade fehlgeschlagen")

    # ---------------------------------------------------------------- Befehle

    @app_commands.command(name="kaufen", description="Trading-Spiel: mit Spielgeld kaufen (echte Kurse)")
    @app_commands.describe(symbol="z. B. BTC, ETH, AAPL, TSLA, ^GDAXI oder ein Name", betrag="Wie viel € investieren?",
                           markt="Automatisch erkennen oder festlegen")
    @app_commands.choices(markt=[
        app_commands.Choice(name="Automatisch", value="auto"),
        app_commands.Choice(name="Krypto", value="krypto"),
        app_commands.Choice(name="Aktie / ETF / Index", value="aktie"),
    ])
    @app_commands.guild_only()
    async def kaufen(self, interaction: discord.Interaction, symbol: app_commands.Range[str, 1, 40],
                     betrag: app_commands.Range[float, 1, 100_000_000], markt: str = "auto"):
        await interaction.response.defer(thinking=True)
        acc = account(interaction.user.id)
        if betrag > acc["cash"] + 0.001:
            await interaction.followup.send(f"❌ Nicht genug Spielgeld. Verfügbar: **{eur(acc['cash'])}**")
            return
        try:
            asset = await self.resolve(symbol, markt)
            if asset is None:
                await interaction.followup.send(f"🤷 Nichts gefunden für **{symbol}**. Probier das Kürzel (BTC, AAPL …).")
                return
            price = (await self.prices_eur([(asset["kind"], asset["key"])])).get((asset["kind"], asset["key"]))
        except (MarketError, aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
            await interaction.followup.send(f"⚠️ Kurs gerade nicht abrufbar: {e}")
            return
        if not price:
            await interaction.followup.send("⚠️ Für dieses Asset gibt es gerade keinen Kurs.")
            return

        qty = betrag / price
        db.execute("UPDATE trade_accounts SET cash = cash - ? WHERE user_id = ?", (betrag, interaction.user.id))
        db.execute(
            "INSERT INTO trade_positions(user_id, kind, asset_key, symbol, name, qty, cost) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, kind, asset_key) DO UPDATE SET qty = qty + excluded.qty, cost = cost + excluded.cost",
            (interaction.user.id, asset["kind"], asset["key"], asset["symbol"], asset["name"], qty, betrag))
        db.execute("INSERT INTO trade_history(user_id, side, kind, asset_key, symbol, qty, price_eur, value_eur, created_at) "
                   "VALUES (?, 'kauf', ?, ?, ?, ?, ?, ?, ?)",
                   (interaction.user.id, asset["kind"], asset["key"], asset["symbol"], qty, price, betrag, now().isoformat()))
        cash = account(interaction.user.id)["cash"]
        embed = discord.Embed(
            title=f"🟢 Kauf: {asset['symbol']}",
            description=(f"{interaction.user.mention} kauft **{fmt_qty(qty)} {asset['symbol']}** ({asset['name']})\n"
                         f"für **{eur(betrag)}** · Kurs {eur(price)}"),
            color=0x2ECC71)
        embed.set_footer(text=f"Restliches Spielgeld: {eur(cash)} · {DISCLAIMER}")
        await interaction.followup.send(embed=embed)
        await self.after_trade(interaction.user)

    @app_commands.command(name="verkaufen", description="Trading-Spiel: Position ganz oder teilweise verkaufen")
    @app_commands.describe(symbol="Was verkaufen? (z. B. BTC, AAPL)", anteil="Wie viel Prozent der Position? (Standard: 100)")
    @app_commands.guild_only()
    async def verkaufen(self, interaction: discord.Interaction, symbol: app_commands.Range[str, 1, 40],
                        anteil: app_commands.Range[int, 1, 100] = 100):
        uid = interaction.user.id
        q = symbol.strip()
        positions = db.fetchall("SELECT * FROM trade_positions WHERE user_id = ?", (uid,))
        pos = next((p for p in positions if q.upper() in (p["symbol"].upper(), p["asset_key"].upper())
                    or (p["name"] or "").lower().startswith(q.lower())), None)
        if pos is None:
            owned = ", ".join(p["symbol"] for p in positions) or "nichts"
            await interaction.response.send_message(f"❌ Du hast kein **{q}** im Depot. Im Depot: {owned}", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            price = (await self.prices_eur([(pos["kind"], pos["asset_key"])])).get((pos["kind"], pos["asset_key"]))
        except (MarketError, aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
            await interaction.followup.send(f"⚠️ Kurs gerade nicht abrufbar: {e}")
            return
        if not price:
            await interaction.followup.send("⚠️ Für dieses Asset gibt es gerade keinen Kurs.")
            return

        share = anteil / 100
        qty = pos["qty"] * share
        cost = pos["cost"] * share
        value = qty * price
        profit = value - cost
        if anteil == 100:
            db.execute("DELETE FROM trade_positions WHERE user_id = ? AND kind = ? AND asset_key = ?",
                       (uid, pos["kind"], pos["asset_key"]))
        else:
            db.execute("UPDATE trade_positions SET qty = qty - ?, cost = cost - ? WHERE user_id = ? AND kind = ? "
                       "AND asset_key = ?", (qty, cost, uid, pos["kind"], pos["asset_key"]))
        db.execute("UPDATE trade_accounts SET cash = cash + ? WHERE user_id = ?", (value, uid))
        db.execute("INSERT INTO trade_history(user_id, side, kind, asset_key, symbol, qty, price_eur, value_eur, "
                   "profit_eur, created_at) VALUES (?, 'verkauf', ?, ?, ?, ?, ?, ?, ?, ?)",
                   (uid, pos["kind"], pos["asset_key"], pos["symbol"], qty, price, value, profit, now().isoformat()))
        pct = profit / cost * 100 if cost else 0
        embed = discord.Embed(
            title=f"{'🟢' if profit >= 0 else '🔴'} Verkauf: {pos['symbol']}",
            description=(f"{interaction.user.mention} verkauft **{fmt_qty(qty)} {pos['symbol']}** ({anteil} %)\n"
                         f"für **{eur(value)}** · Kurs {eur(price)}\n"
                         f"Ergebnis: **{'+' if profit >= 0 else ''}{eur(profit)}** ({fmt_change(pct)})"),
            color=0x2ECC71 if profit >= 0 else 0xE74C3C)
        embed.set_footer(text=f"Spielgeld jetzt: {eur(account(uid)['cash'])} · {DISCLAIMER}")
        await interaction.followup.send(embed=embed)
        await self.after_trade(interaction.user)

    @app_commands.command(name="depot", description="Trading-Spiel: Depot mit Gewinn und Verlust anzeigen")
    @app_commands.describe(mitglied="Wessen Depot? (leer = deins)")
    @app_commands.guild_only()
    async def depot(self, interaction: discord.Interaction, mitglied: discord.Member | None = None):
        member = mitglied or interaction.user
        await interaction.response.defer(thinking=True)
        try:
            total, positions = await self.depot_value(member.id)
        except (MarketError, aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
            await interaction.followup.send(f"⚠️ Kurse gerade nicht abrufbar: {e}")
            return
        acc = account(member.id)
        start = config.TRADING_START_CASH
        pct = (total - start) / start * 100
        lines = []
        for p in sorted(positions, key=lambda p: p["value"], reverse=True):
            ppct = (p["value"] - p["cost"]) / p["cost"] * 100 if p["cost"] else 0
            lines.append(f"**{p['symbol']}** · {fmt_qty(p['qty'])} · {eur(p['value'])} · {fmt_change(ppct)}")
        embed = discord.Embed(
            title=f"💼 Depot von {member.display_name}",
            description="\n".join(lines) or "*Noch keine Positionen – starte mit `/kaufen BTC 500`.*",
            color=0x2ECC71 if total >= start else 0xE74C3C)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Gesamtwert", value=f"**{eur(total)}**")
        embed.add_field(name="Performance", value=fmt_change(pct))
        embed.add_field(name="Freies Spielgeld", value=eur(acc["cash"]))
        trades = db.scalar("SELECT COUNT(*) FROM trade_history WHERE user_id = ?", (member.id,))
        embed.set_footer(text=f"Start: {eur(start)} · {trades} Trades · {DISCLAIMER}")
        await interaction.followup.send(embed=embed)
        if member.id == interaction.user.id:
            await self.after_trade(member)

    @app_commands.command(name="trading-rangliste", description="Trading-Spiel: die besten Depots der Mancave")
    @app_commands.guild_only()
    async def rangliste(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        users = [r["user_id"] for r in db.fetchall(
            "SELECT DISTINCT user_id FROM trade_history WHERE user_id IN (SELECT user_id FROM trade_accounts)")]
        if not users:
            await interaction.followup.send("Noch hat niemand getradet. Starte mit `/kaufen BTC 500`! 📈")
            return
        # Alle Kurse auf einmal holen (schont die APIs), dann Depots bewerten
        all_pos = db.fetchall("SELECT kind, asset_key FROM trade_positions")
        try:
            await self.prices_eur([(p["kind"], p["asset_key"]) for p in all_pos])
            values = [(uid, (await self.depot_value(uid))[0]) for uid in users]
        except (MarketError, aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
            await interaction.followup.send(f"⚠️ Kurse gerade nicht abrufbar: {e}")
            return
        values.sort(key=lambda v: v[1], reverse=True)
        start = config.TRADING_START_CASH
        lines = [f"{medal(i)} **{member_name(interaction.guild, uid)}** – {eur(v)} "
                 f"({fmt_change((v - start) / start * 100)})" for i, (uid, v) in enumerate(values[:10])]
        embed = discord.Embed(title="📈 Trading-Rangliste (Spielgeld)", description="\n".join(lines), color=0xF7931A)
        embed.set_footer(text=f"Startkapital {eur(start)} · {DISCLAIMER}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="trading-reset", description="Trading-Spiel: Depot auflösen und neu mit Startkapital beginnen")
    @app_commands.describe(bestaetigen="Wirklich alles zurücksetzen?")
    @app_commands.guild_only()
    async def reset(self, interaction: discord.Interaction, bestaetigen: bool):
        if not bestaetigen:
            await interaction.response.send_message("Abgebrochen – dein Depot bleibt, wie es ist.", ephemeral=True)
            return
        acc = account(interaction.user.id)
        if acc["reset_at"]:
            allowed_again = datetime.fromisoformat(acc["reset_at"]) + timedelta(days=config.TRADING_RESET_COOLDOWN_DAYS)
            if now() < allowed_again:
                await interaction.response.send_message(
                    f"⏳ Neustart ist nur alle {config.TRADING_RESET_COOLDOWN_DAYS} Tage möglich.", ephemeral=True)
                return
        db.execute("DELETE FROM trade_positions WHERE user_id = ?", (interaction.user.id,))
        db.execute("UPDATE trade_accounts SET cash = ?, last_value = ?, resets = resets + 1, reset_at = ? WHERE user_id = ?",
                   (config.TRADING_START_CASH, config.TRADING_START_CASH, now().isoformat(), interaction.user.id))
        await interaction.response.send_message(
            f"🔄 Neustart! Du hast wieder **{eur(config.TRADING_START_CASH)}** Spielgeld.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TradingGame(bot))
