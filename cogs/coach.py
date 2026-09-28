"""
KI-Coach mit Claude.

  /coach frage [privat]  -> Antwort zu Business, Finanzen, Training, Mindset

Braucht ANTHROPIC_API_KEY in der .env (https://console.anthropic.com).
Optional kennt der Coach deine letzten Check-ins, Workouts und dein Level (config.COACH_USE_CONTEXT).
"""

import os
from datetime import timedelta

import anthropic
import discord
from discord import app_commands
from discord.ext import commands

import config
import db
from cogs.checkin import current_streak
from utils import is_mod, log, today, today_str, week_start

MAX_EMBED = 4000


def member_context(member: discord.Member) -> str:
    level = db.scalar("SELECT level FROM users WHERE user_id = ?", (member.id,))
    lines = [f"Mitglied: {member.display_name} · Level {level} · Check-in-Serie: {current_streak(member.id)} Tage"]

    checkins = db.fetchall(
        "SELECT day, koerper, business, wissen FROM checkins WHERE user_id = ? ORDER BY day DESC LIMIT 5", (member.id,),
    )
    if checkins:
        lines.append("Letzte Check-ins:")
        lines += [f"- {c['day']}: Körper: {c['koerper']} | Business: {c['business']} | Wissen: {c['wissen']}"
                  for c in checkins]

    since = (today() - timedelta(days=13)).isoformat()
    workouts = db.fetchall(
        "SELECT day, kind, minutes, note FROM workouts WHERE user_id = ? AND day >= ? ORDER BY day DESC LIMIT 10",
        (member.id, since),
    )
    week = db.fetchone("SELECT COUNT(*) AS s, COALESCE(SUM(minutes), 0) AS m FROM workouts WHERE user_id = ? AND day >= ?",
                       (member.id, week_start().isoformat()))
    lines.append(f"Training diese Woche: {week['s']}× / {week['m']} Min.")
    if workouts:
        lines.append("Workouts der letzten 2 Wochen:")
        lines += [f"- {w['day']}: {w['kind']} {w['minutes']} Min." + (f" ({w['note']})" if w["note"] else "")
                  for w in workouts]
    return "\n".join(lines)


def split_text(text: str, size: int = MAX_EMBED) -> list[str]:
    parts = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        cut = cut if cut > size // 2 else size
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    parts.append(text)
    return parts


class Coach(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        key = os.getenv("ANTHROPIC_API_KEY")
        self.client = anthropic.AsyncAnthropic(api_key=key) if key else None
        if not key:
            log.info("KI-Coach deaktiviert (kein ANTHROPIC_API_KEY in der .env).")

    async def cog_unload(self):
        if self.client:
            await self.client.close()

    async def ask(self, member: discord.Member, question: str) -> str:
        content = question
        if config.COACH_USE_CONTEXT:
            content = f"<kontext>\n{member_context(member)}\n</kontext>\n\n{question}"

        response = await self.client.beta.messages.create(
            model=config.COACH_MODEL,
            max_tokens=16000,
            system=config.COACH_SYSTEM_PROMPT,
            output_config={"effort": config.COACH_EFFORT},
            # Falls die Anfrage vom Modell abgelehnt wird, übernimmt automatisch ein Ersatzmodell
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": content}],
        )
        if response.stop_reason == "refusal":
            return "Dazu kann ich leider nichts sagen. Frag mich gern etwas anderes zu Business, Training oder Mindset."
        text = "\n".join(b.text for b in response.content if b.type == "text").strip()
        if response.stop_reason == "max_tokens":
            text += "\n\n*(Antwort gekürzt)*"
        return text or "Ich habe gerade keine Antwort parat – formulier die Frage gern nochmal anders."

    @app_commands.command(name="coach", description="Frag den KI-Coach: Business, Finanzen, Training, Mindset")
    @app_commands.describe(frage="Deine Frage", privat="Nur für dich sichtbar?")
    @app_commands.guild_only()
    async def coach(self, interaction: discord.Interaction, frage: app_commands.Range[str, 3, 1500],
                    privat: bool = False):
        if self.client is None:
            await interaction.response.send_message(
                "🤖 Der Coach ist noch nicht eingerichtet (ANTHROPIC_API_KEY fehlt).", ephemeral=True,
            )
            return
        member = interaction.user
        day = today_str()
        used = db.scalar("SELECT count FROM coach_usage WHERE user_id = ? AND day = ?", (member.id, day))
        if used >= config.COACH_DAILY_LIMIT and not is_mod(member):
            await interaction.response.send_message(
                f"⏳ Du hast heute schon {used} Fragen gestellt (Limit {config.COACH_DAILY_LIMIT}). Morgen wieder!",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=privat)
        try:
            answer = await self.ask(member, frage)
        except anthropic.RateLimitError:
            await interaction.followup.send("⏳ Der Coach ist gerade ausgelastet. Versuch es in einer Minute nochmal.",
                                            ephemeral=True)
            return
        except anthropic.AuthenticationError:
            log.error("KI-Coach: ANTHROPIC_API_KEY ist ungültig.")
            await interaction.followup.send("⚠️ Der Coach ist falsch eingerichtet (API-Key ungültig).", ephemeral=True)
            return
        except anthropic.APIStatusError as e:
            log.error("KI-Coach API-Fehler %s: %s", e.status_code, e.message)
            await interaction.followup.send("⚠️ Der Coach ist gerade nicht erreichbar. Versuch es später nochmal.",
                                            ephemeral=True)
            return
        except anthropic.APIConnectionError:
            await interaction.followup.send("⚠️ Keine Verbindung zum Coach. Versuch es später nochmal.", ephemeral=True)
            return

        db.execute("INSERT INTO coach_usage(user_id, day, count) VALUES (?, ?, 1) "
                   "ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1", (member.id, day))

        parts = split_text(answer)
        for i, part in enumerate(parts):
            embed = discord.Embed(description=part, color=0x9B59B6)
            if i == 0:
                embed.title = "🤖 Mancave-Coach"
                embed.add_field(name="Frage", value=frage[:1024], inline=False)
                embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            if i == len(parts) - 1:
                embed.set_footer(text="KI-Antwort – keine Finanz-, Rechts- oder medizinische Beratung.")
            await interaction.followup.send(embed=embed, ephemeral=privat)


async def setup(bot: commands.Bot):
    await bot.add_cog(Coach(bot))
