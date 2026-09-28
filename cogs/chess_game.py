"""
Schach direkt im Discord-Chat.

  /schach [gegner]     -> Herausforderung (ohne Gegner: offen für alle)
  /zug e4 | Sf3 | e2e4 -> Zug machen (englische, deutsche und UCI-Notation)
  /schach-brett        -> aktuelles Brett nochmal zeigen
  /remis               -> Remis anbieten bzw. annehmen
  /aufgeben            -> Partie aufgeben
  /schach-rangliste    -> Elo-Rangliste
  /schach-stats        -> eigene Statistik

Regeln prüft python-chess (Schach, Matt, Patt, Rochade, en passant, Umwandlung, Remis-Regeln).
Sieg/Remis/Niederlage geben XP, dazu Elo-Wertung. Wer zu lange nicht zieht, verliert (config.CHESS_TIMEOUT_HOURS).
"""

import io
import random
from datetime import timedelta

import chess
import chess.pgn
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import db
from chess_render import render_board
from cogs.leveling import grant_xp
from utils import get_text_channel, log, medal, member_name, now

db.execute("""CREATE TABLE IF NOT EXISTS chess_games (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id  INTEGER NOT NULL,
    message_id  INTEGER,
    white_id    INTEGER NOT NULL,
    black_id    INTEGER NOT NULL,
    moves       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active',
    result      TEXT,
    reason      TEXT,
    draw_offer  INTEGER,
    created_at  TEXT,
    updated_at  TEXT
)""")
db.execute("""CREATE TABLE IF NOT EXISTS chess_ratings (
    user_id INTEGER PRIMARY KEY,
    elo     INTEGER NOT NULL,
    wins    INTEGER NOT NULL DEFAULT 0,
    losses  INTEGER NOT NULL DEFAULT 0,
    draws   INTEGER NOT NULL DEFAULT 0
)""")

# Deutsche Figurenbuchstaben -> englische SAN (D=Dame, T=Turm, L=Läufer, S=Springer)
GERMAN = str.maketrans({"D": "Q", "T": "R", "L": "B", "S": "N"})
TO_GERMAN = str.maketrans({"Q": "D", "R": "T", "B": "L", "N": "S"})


def de(san: str) -> str:
    """Englische SAN -> deutsche Anzeige (Nf3 -> Sf3, Bxc4 -> Lxc4, e8=Q -> e8=D)."""
    return san.translate(TO_GERMAN)
REASONS = {
    "checkmate": "Schachmatt",
    "stalemate": "Patt",
    "insufficient_material": "zu wenig Material",
    "seventyfive_moves": "75-Züge-Regel",
    "fivefold_repetition": "fünffache Stellungswiederholung",
    "fifty_moves": "50-Züge-Regel",
    "threefold_repetition": "dreifache Stellungswiederholung",
    "resign": "Aufgabe",
    "draw_agreed": "Remis vereinbart",
    "timeout": "Zeitüberschreitung",
}


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #

def board_of(game) -> chess.Board:
    board = chess.Board()
    for uci in game["moves"].split():
        board.push_uci(uci)
    return board


def active_game(user_id: int):
    return db.fetchone("SELECT * FROM chess_games WHERE status = 'active' AND (white_id = ? OR black_id = ?)",
                       (user_id, user_id))


def rating(user_id: int):
    db.execute("INSERT OR IGNORE INTO chess_ratings(user_id, elo) VALUES (?, ?)", (user_id, config.CHESS_START_ELO))
    return db.fetchone("SELECT * FROM chess_ratings WHERE user_id = ?", (user_id,))


def parse_move(board: chess.Board, text: str) -> chess.Move | None:
    text = text.strip().replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    candidates = [text, text.translate(GERMAN)]
    for cand in candidates:
        for parser in (board.parse_san, lambda t: board.parse_uci(t.lower())):
            try:
                return parser(cand)
            except ValueError:
                continue
    return None


def move_list(board: chess.Board, last: int = 10) -> str:
    """Letzte Züge in Schachnotation: 1. e4 e5 2. Sf3 ..."""
    replay = chess.Board()
    parts = []
    for i, move in enumerate(board.move_stack):
        san = de(replay.san(move))
        parts.append(f"{i // 2 + 1}. {san}" if i % 2 == 0 else san)
        replay.push(move)
    text = " ".join(parts)
    if len(parts) > last:
        text = "… " + " ".join(parts[-last:])
    return text or "–"


def pgn_file(game, board: chess.Board, guild: discord.Guild) -> discord.File:
    pgn = chess.pgn.Game.from_board(board)
    pgn.headers["Event"] = f"{config.SERVER_NAME} Schach #{game['id']}"
    pgn.headers["Site"] = "Discord"
    pgn.headers["Date"] = (game["created_at"] or "")[:10].replace("-", ".")
    pgn.headers["White"] = member_name(guild, game["white_id"])
    pgn.headers["Black"] = member_name(guild, game["black_id"])
    pgn.headers["Result"] = game["result"] or "*"
    return discord.File(io.BytesIO(str(pgn).encode()), filename=f"schach-{game['id']}.pgn")


def elo_update(white: int, black: int, score_white: float) -> tuple[int, int]:
    rw, rb = rating(white)["elo"], rating(black)["elo"]
    expected = 1 / (1 + 10 ** ((rb - rw) / 400))
    k = config.CHESS_ELO_K
    new_w = round(rw + k * (score_white - expected))
    new_b = round(rb + k * ((1 - score_white) - (1 - expected)))
    return new_w - rw, new_b - rb


# --------------------------------------------------------------------------- #
# Herausforderung
# --------------------------------------------------------------------------- #

class ChallengeView(discord.ui.View):
    def __init__(self, cog: "Chess", challenger: discord.Member, opponent: discord.Member | None):
        super().__init__(timeout=config.CHESS_CHALLENGE_MINUTES * 60)
        self.cog, self.challenger, self.opponent = cog, challenger, opponent
        self.message: discord.Message | None = None

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(content=f"⌛ Die Schach-Herausforderung von {self.challenger.mention} ist abgelaufen.",
                                        embed=None, view=None)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Annehmen", emoji="♟️", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.id == self.challenger.id:
            await interaction.response.send_message("Du kannst nicht gegen dich selbst spielen. 😄", ephemeral=True)
            return
        if self.opponent and user.id != self.opponent.id:
            await interaction.response.send_message("Diese Herausforderung gilt nicht dir.", ephemeral=True)
            return
        for player in (self.challenger, user):
            if active_game(player.id):
                await interaction.response.send_message(
                    f"{player.mention} spielt gerade schon eine Partie. Erst beenden, dann neu starten!", ephemeral=True)
                return
        self.stop()
        await interaction.response.edit_message(
            content=f"✅ {user.mention} hat die Herausforderung von {self.challenger.mention} angenommen!",
            embed=None, view=None)
        await self.cog.start_game(interaction.channel, self.challenger, user)

    @discord.ui.button(label="Ablehnen", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        allowed = user.id == self.challenger.id or (self.opponent and user.id == self.opponent.id)
        if not allowed:
            await interaction.response.send_message("Nur die beiden Spieler können ablehnen.", ephemeral=True)
            return
        self.stop()
        text = ("🚫 Herausforderung zurückgezogen." if user.id == self.challenger.id
                else f"🚫 {user.mention} hat die Herausforderung abgelehnt.")
        await interaction.response.edit_message(content=text, embed=None, view=None)


# --------------------------------------------------------------------------- #
# Cog
# --------------------------------------------------------------------------- #

class Chess(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_unload(self):
        self.timeout_check.cancel()

    @commands.Cog.listener()
    async def on_mancave_ready(self, guild: discord.Guild):
        if not self.timeout_check.is_running():
            self.timeout_check.start()

    def game_channel(self, interaction: discord.Interaction) -> discord.abc.Messageable:
        """Partien laufen in den Schach-Kanälen; von woanders aus -> #schach-partien."""
        name = getattr(interaction.channel, "name", "")
        if name in config.CHESS_CHANNELS:
            return interaction.channel
        return get_text_channel(interaction.guild, config.CHESS_CHANNELS[0]) or interaction.channel

    # ---------------------------------------------------------------- Anzeige

    async def post_board(self, game, note: str | None = None):
        """Postet das aktuelle Brett (neue Nachricht) und löscht das vorherige."""
        channel = self.bot.get_channel(game["channel_id"])
        if channel is None:
            return
        guild = channel.guild
        board = board_of(game)
        to_move = game["white_id"] if board.turn == chess.WHITE else game["black_id"]
        rw, rb = rating(game["white_id"])["elo"], rating(game["black_id"])["elo"]
        color = "Weiß ⚪" if board.turn == chess.WHITE else "Schwarz ⚫"

        desc = (f"⚪ **Weiß:** <@{game['white_id']}> ({rw})\n"
                f"⚫ **Schwarz:** <@{game['black_id']}> ({rb})\n\n")
        if note:
            desc += f"{note}\n"
        if board.is_check():
            desc += "⚠️ **Schach!**\n"
        desc += f"👉 **Am Zug:** <@{to_move}> ({color})"
        if game["draw_offer"]:
            desc += f"\n🤝 <@{game['draw_offer']}> bietet Remis an – `/remis` zum Annehmen."

        embed = discord.Embed(title=f"♟️ Schach-Partie #{game['id']}", description=desc, color=0xB58863)
        embed.add_field(name="Züge", value=move_list(board), inline=False)
        embed.set_image(url="attachment://brett.png")
        embed.set_footer(text="Ziehen: /zug e4 · /zug Sf3 · /zug e2e4 · /remis · /aufgeben")
        file = discord.File(render_board(board, flipped=board.turn == chess.BLACK), filename="brett.png")

        msg = await channel.send(content=f"<@{to_move}> du bist dran!", embed=embed, file=file,
                                 allowed_mentions=discord.AllowedMentions(users=True))
        if game["message_id"]:
            try:
                old = await channel.fetch_message(game["message_id"])
                await old.delete()
            except discord.HTTPException:
                pass
        db.execute("UPDATE chess_games SET message_id = ? WHERE id = ?", (msg.id, game["id"]))

    async def start_game(self, channel: discord.abc.Messageable, a: discord.Member, b: discord.Member):
        white, black = (a, b) if random.random() < 0.5 else (b, a)
        stamp = now().isoformat()
        cur = db.execute(
            "INSERT INTO chess_games(channel_id, white_id, black_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (channel.id, white.id, black.id, stamp, stamp))
        game = db.fetchone("SELECT * FROM chess_games WHERE id = ?", (cur.lastrowid,))
        await self.post_board(game, note="🎲 Farben wurden ausgelost. Viel Erfolg!")

    async def finish(self, game, board: chess.Board, result: str, reason: str):
        """Partie beenden: Ergebnis, Elo, XP, PGN."""
        db.execute("UPDATE chess_games SET status = 'finished', result = ?, reason = ?, draw_offer = NULL, "
                   "updated_at = ? WHERE id = ?", (result, reason, now().isoformat(), game["id"]))
        game = db.fetchone("SELECT * FROM chess_games WHERE id = ?", (game["id"],))
        channel = self.bot.get_channel(game["channel_id"])
        guild = channel.guild if channel else self.bot.get_guild(self.bot.guild_id)

        score = {"1-0": 1.0, "0-1": 0.0}.get(result, 0.5)
        dw, dbk = elo_update(game["white_id"], game["black_id"], score)
        for uid, delta, s in ((game["white_id"], dw, score), (game["black_id"], dbk, 1 - score)):
            col = "wins" if s == 1 else "losses" if s == 0 else "draws"
            db.execute(f"UPDATE chess_ratings SET elo = elo + ?, {col} = {col} + 1 WHERE user_id = ?", (delta, uid))
            member = guild.get_member(uid) if guild else None
            if member:
                xp = config.XP_CHESS_WIN if s == 1 else config.XP_CHESS_LOSS if s == 0 else config.XP_CHESS_DRAW
                await grant_xp(member, xp)

        if result == "1/2-1/2":
            headline = f"🤝 **Remis** ({REASONS.get(reason, reason)})"
        else:
            winner = game["white_id"] if result == "1-0" else game["black_id"]
            headline = f"🏆 <@{winner}> gewinnt durch **{REASONS.get(reason, reason)}**!"
        rw, rb = rating(game["white_id"])["elo"], rating(game["black_id"])["elo"]
        desc = (f"{headline}\n\n"
                f"⚪ <@{game['white_id']}> – Elo {rw} ({dw:+d})\n"
                f"⚫ <@{game['black_id']}> – Elo {rb} ({dbk:+d})\n\n"
                f"Ergebnis: **{result.replace('1/2', '½')}** · {len(board.move_stack)} Halbzüge")
        embed = discord.Embed(title=f"♟️ Partie #{game['id']} beendet", description=desc, color=0xF1C40F)
        embed.add_field(name="Züge", value=move_list(board, last=16), inline=False)
        embed.set_image(url="attachment://brett.png")
        embed.set_footer(text="PGN-Datei zum Nachspielen, z. B. auf lichess.org/paste · Neue Partie: /schach")
        if channel:
            files = [discord.File(render_board(board), filename="brett.png"), pgn_file(game, board, guild)]
            await channel.send(embed=embed, files=files, allowed_mentions=discord.AllowedMentions(users=True))
            if game["message_id"]:
                try:
                    old = await channel.fetch_message(game["message_id"])
                    await old.delete()
                except discord.HTTPException:
                    pass

    # ---------------------------------------------------------------- Befehle

    @app_commands.command(name="schach", description="Fordere jemanden zu einer Partie Schach heraus")
    @app_commands.describe(gegner="Wen? (leer = offene Herausforderung für alle)")
    @app_commands.guild_only()
    async def schach(self, interaction: discord.Interaction, gegner: discord.Member | None = None):
        me = interaction.user
        if gegner and (gegner.bot or gegner.id == me.id):
            await interaction.response.send_message("Such dir einen echten Gegner. 😄", ephemeral=True)
            return
        if active_game(me.id):
            await interaction.response.send_message("Du spielst schon eine Partie – `/schach-brett` zeigt sie.",
                                                    ephemeral=True)
            return
        if gegner and active_game(gegner.id):
            await interaction.response.send_message(f"{gegner.mention} spielt gerade schon.", ephemeral=True)
            return

        channel = self.game_channel(interaction)
        r = rating(me.id)["elo"]
        embed = discord.Embed(
            title="♟️ Schach-Herausforderung",
            description=(f"{me.mention} (Elo {r}) fordert "
                         + (f"{gegner.mention} heraus!" if gegner else "**jeden** heraus – wer traut sich?")
                         + f"\n\nFarben werden ausgelost. Läuft ab in {config.CHESS_CHALLENGE_MINUTES} Min."),
            color=0xB58863,
        )
        view = ChallengeView(self, me, gegner)
        view.message = await channel.send(content=gegner.mention if gegner else None, embed=embed, view=view,
                                          allowed_mentions=discord.AllowedMentions(users=True))
        where = "" if channel.id == interaction.channel_id else f" in {channel.mention}"
        await interaction.response.send_message(f"✅ Herausforderung gepostet{where}.", ephemeral=True)

    @app_commands.command(name="zug", description="Schachzug machen, z. B. e4, Sf3, O-O oder e2e4")
    @app_commands.describe(zug="Dein Zug (englisch: Nf3 · deutsch: Sf3 · UCI: g1f3 · Rochade: O-O)")
    @app_commands.guild_only()
    async def zug(self, interaction: discord.Interaction, zug: app_commands.Range[str, 2, 10]):
        game = active_game(interaction.user.id)
        if game is None:
            await interaction.response.send_message("Du hast keine laufende Partie. Starte eine mit `/schach`.",
                                                    ephemeral=True)
            return
        board = board_of(game)
        mover = game["white_id"] if board.turn == chess.WHITE else game["black_id"]
        if interaction.user.id != mover:
            await interaction.response.send_message("⏳ Du bist nicht am Zug.", ephemeral=True)
            return
        move = parse_move(board, zug)
        if move is None or move not in board.legal_moves:
            legal = ", ".join(sorted(de(board.san(m)) for m in list(board.legal_moves)[:12]))
            await interaction.response.send_message(
                f"❌ **{zug}** ist hier kein gültiger Zug.\nMögliche Züge z. B.: {legal}", ephemeral=True)
            return

        san = de(board.san(move))
        board.push(move)
        moves = (game["moves"] + " " + move.uci()).strip()
        db.execute("UPDATE chess_games SET moves = ?, draw_offer = NULL, updated_at = ? WHERE id = ?",
                   (moves, now().isoformat(), game["id"]))
        game = db.fetchone("SELECT * FROM chess_games WHERE id = ?", (game["id"],))
        await interaction.response.send_message(f"✅ {san}", ephemeral=True)

        outcome = board.outcome(claim_draw=True)
        if outcome:
            result = outcome.result()
            reason = outcome.termination.name.lower()
            await self.finish(game, board, result, reason)
        else:
            await self.post_board(game, note=f"Letzter Zug: **{san}**")

    @app_commands.command(name="schach-brett", description="Zeigt das Brett deiner laufenden Partie")
    @app_commands.guild_only()
    async def brett(self, interaction: discord.Interaction):
        game = active_game(interaction.user.id)
        if game is None:
            await interaction.response.send_message("Du hast keine laufende Partie.", ephemeral=True)
            return
        await interaction.response.send_message("📋 Brett wird neu gepostet.", ephemeral=True)
        await self.post_board(game)

    @app_commands.command(name="remis", description="Remis anbieten oder ein Angebot annehmen")
    @app_commands.guild_only()
    async def remis(self, interaction: discord.Interaction):
        game = active_game(interaction.user.id)
        if game is None:
            await interaction.response.send_message("Du hast keine laufende Partie.", ephemeral=True)
            return
        me = interaction.user.id
        if game["draw_offer"] and game["draw_offer"] != me:
            await interaction.response.send_message("🤝 Remis angenommen.", ephemeral=True)
            await self.finish(game, board_of(game), "1/2-1/2", "draw_agreed")
            return
        if game["draw_offer"] == me:
            await interaction.response.send_message("Du hast schon Remis angeboten – warte auf die Antwort.",
                                                    ephemeral=True)
            return
        db.execute("UPDATE chess_games SET draw_offer = ? WHERE id = ?", (me, game["id"]))
        game = db.fetchone("SELECT * FROM chess_games WHERE id = ?", (game["id"],))
        await interaction.response.send_message("🤝 Remis angeboten.", ephemeral=True)
        await self.post_board(game)

    @app_commands.command(name="aufgeben", description="Deine laufende Schach-Partie aufgeben")
    @app_commands.guild_only()
    async def aufgeben(self, interaction: discord.Interaction):
        game = active_game(interaction.user.id)
        if game is None:
            await interaction.response.send_message("Du hast keine laufende Partie.", ephemeral=True)
            return
        result = "0-1" if interaction.user.id == game["white_id"] else "1-0"
        await interaction.response.send_message("🏳️ Partie aufgegeben.", ephemeral=True)
        await self.finish(game, board_of(game), result, "resign")

    @app_commands.command(name="schach-rangliste", description="Die besten Schachspieler der Mancave (Elo)")
    @app_commands.guild_only()
    async def rangliste(self, interaction: discord.Interaction):
        rows = db.fetchall("SELECT * FROM chess_ratings WHERE wins + losses + draws > 0 "
                           "ORDER BY elo DESC, wins DESC LIMIT 10")
        if not rows:
            await interaction.response.send_message("Noch keine gewerteten Partien. Leg los mit `/schach`! ♟️")
            return
        lines = [f"{medal(i)} **{member_name(interaction.guild, r['user_id'])}** – Elo {r['elo']} "
                 f"({r['wins']}S / {r['draws']}R / {r['losses']}N)" for i, r in enumerate(rows)]
        embed = discord.Embed(title="♟️ Schach-Rangliste", description="\n".join(lines), color=0xB58863)
        embed.set_footer(text="S = Siege · R = Remis · N = Niederlagen")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="schach-stats", description="Schach-Statistik (deine oder von jemand anderem)")
    @app_commands.guild_only()
    async def stats(self, interaction: discord.Interaction, mitglied: discord.Member | None = None):
        member = mitglied or interaction.user
        r = rating(member.id)
        games = r["wins"] + r["losses"] + r["draws"]
        pos = db.scalar("SELECT COUNT(*) FROM chess_ratings WHERE elo > ? AND wins + losses + draws > 0",
                        (r["elo"],)) + 1
        embed = discord.Embed(title=f"♟️ Schach-Stats von {member.display_name}", color=0xB58863)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Elo", value=str(r["elo"]))
        embed.add_field(name="Platz", value=f"#{pos}" if games else "–")
        embed.add_field(name="Partien", value=str(games))
        embed.add_field(name="Bilanz", value=f"{r['wins']} Siege · {r['draws']} Remis · {r['losses']} Niederlagen",
                        inline=False)
        if games:
            embed.add_field(name="Siegquote", value=f"{r['wins'] / games * 100:.0f} %")
        await interaction.response.send_message(embed=embed)

    # ---------------------------------------------------------------- Zeitüberschreitung

    @tasks.loop(minutes=30)
    async def timeout_check(self):
        limit = (now() - timedelta(hours=config.CHESS_TIMEOUT_HOURS)).isoformat()
        for game in db.fetchall("SELECT * FROM chess_games WHERE status = 'active' AND updated_at < ?", (limit,)):
            board = board_of(game)
            # Wer am Zug ist und nicht zieht, verliert
            result = "0-1" if board.turn == chess.WHITE else "1-0"
            await self.finish(game, board, result, "timeout")

    @timeout_check.error
    async def timeout_check_error(self, error):
        log.exception("Schach-Timeout-Prüfung fehlgeschlagen", exc_info=error)


async def setup(bot: commands.Bot):
    await bot.add_cog(Chess(bot))
