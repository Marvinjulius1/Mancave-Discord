"""
Ticket-System.

In #ticket-erstellen steht eine Nachricht mit Button. Klick -> privater Kanal in "🎫 TICKETS",
den nur das Mitglied und das Team (Admin, Consigliere, Türsteher) sehen. "Schließen" speichert ein Protokoll in #bot-logs
und löscht den Kanal. Alternativ: /ticket.
"""

import asyncio
import io
import re

import discord
from discord import app_commands
from discord.ext import commands

import config
import db
from utils import bot_can_manage, get_role, get_text_channel, is_mod, log, now, send_log, post_or_update

OPEN_ID = "mancave:ticket_open"
CLOSE_ID = "mancave:ticket_close"
PANEL_MARKER = "mancave-ticket-panel"


def panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎫 Support & Fragen an die Admins",
        description=(
            "Du hast eine Frage, ein Problem oder willst etwas melden?\n\n"
            "Klick auf **Ticket öffnen** – dann bekommst du einen **privaten Kanal**, "
            "den nur du und das Admin-/Mod-Team sehen."
        ),
        color=0x3498DB,
    )
    embed.set_footer(text=f"{config.SERVER_NAME} • {PANEL_MARKER}")
    return embed


async def open_ticket(interaction: discord.Interaction):
    guild = interaction.guild
    member = interaction.user
    existing = db.fetchone("SELECT channel_id FROM tickets WHERE user_id = ? AND closed_at IS NULL", (member.id,))
    if existing and guild.get_channel(existing["channel_id"]):
        await interaction.response.send_message(f"Du hast schon ein offenes Ticket: <#{existing['channel_id']}>",
                                                ephemeral=True)
        return
    category = discord.utils.get(guild.categories, name=config.TICKET_CATEGORY)
    if category is None:
        await interaction.response.send_message("⚠️ Ticket-Kategorie fehlt – ein Admin muss /setup ausführen.",
                                                ephemeral=True)
        return

    team = [r for r in (get_role(guild, name) for name in config.TEAM_ROLES) if r]
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: bot_can_manage(),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True,
                                            embed_links=True, read_message_history=True),
    }
    for role in team:
        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                       read_message_history=True, manage_messages=True)
    slug = re.sub(r"[^a-z0-9-]", "", member.name.lower()) or str(member.id)
    channel = await category.create_text_channel(
        f"ticket-{slug}"[:90], overwrites=overwrites, topic=f"Ticket von {member} ({member.id})",
        reason="Ticket geöffnet",
    )
    db.execute("INSERT INTO tickets(channel_id, user_id, created_at) VALUES (?, ?, ?)",
               (channel.id, member.id, now().isoformat()))

    embed = discord.Embed(
        title="🎫 Ticket geöffnet",
        description=(f"Hey {member.mention}, beschreib dein Anliegen so genau wie möglich. "
                     "Das Team meldet sich hier so schnell es geht.\n\n"
                     "Wenn alles geklärt ist: **Ticket schließen** klicken."),
        color=0x3498DB,
    )
    ping = " ".join([member.mention] + [r.mention for r in team])
    await channel.send(ping, embed=embed, view=CloseView(),
                       allowed_mentions=discord.AllowedMentions(users=True, roles=True))
    await interaction.response.send_message(f"✅ Dein Ticket: {channel.mention}", ephemeral=True)
    await send_log(guild, f"🎫 Ticket geöffnet von {member.mention}: {channel.mention}")


class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket öffnen", emoji="🎫", style=discord.ButtonStyle.primary, custom_id=OPEN_ID)
    async def open(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_ticket(interaction)


class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket schließen", emoji="🔒", style=discord.ButtonStyle.danger, custom_id=CLOSE_ID)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = db.fetchone("SELECT * FROM tickets WHERE channel_id = ?", (interaction.channel_id,))
        if ticket is None:
            await interaction.response.send_message("Das ist kein Ticket-Kanal.", ephemeral=True)
            return
        if interaction.user.id != ticket["user_id"] and not is_mod(interaction.user):
            await interaction.response.send_message("Nur der Ersteller oder ein Mod kann schließen.", ephemeral=True)
            return
        await interaction.response.send_message("🔒 Ticket wird in 5 Sekunden geschlossen ...")
        channel = interaction.channel

        lines = []
        async for msg in channel.history(limit=500, oldest_first=True):
            stamp = msg.created_at.astimezone().strftime("%d.%m.%Y %H:%M")
            text = msg.content or ""
            if msg.embeds:
                text += " " + " ".join(f"[Embed: {e.title or ''} {e.description or ''}]" for e in msg.embeds)
            if msg.attachments:
                text += " " + " ".join(f"[Anhang: {a.url}]" for a in msg.attachments)
            lines.append(f"[{stamp}] {msg.author}: {text.strip()}")
        transcript = discord.File(io.BytesIO("\n".join(lines).encode("utf-8")), filename=f"{channel.name}.txt")

        db.execute("UPDATE tickets SET closed_at = ? WHERE channel_id = ?", (now().isoformat(), channel.id))
        log_channel = get_text_channel(interaction.guild, config.LOG_CHANNEL)
        if log_channel:
            try:
                await log_channel.send(
                    f"🔒 Ticket `{channel.name}` von <@{ticket['user_id']}> geschlossen von {interaction.user.mention}.",
                    file=transcript, allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                pass
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket geschlossen von {interaction.user}")
        except discord.HTTPException as e:
            log.warning("Ticket-Kanal konnte nicht gelöscht werden: %s", e)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(PanelView())
        self.bot.add_view(CloseView())

    @commands.Cog.listener()
    async def on_mancave_ready(self, guild: discord.Guild):
        """Panel-Nachricht in #ticket-erstellen posten bzw. aktualisieren."""
        channel = get_text_channel(guild, config.TICKET_PANEL_CHANNEL)
        if channel is None:
            return
        embed = panel_embed()
        existing = None
        async for msg in channel.history(limit=50):
            if msg.author == guild.me and msg.embeds and PANEL_MARKER in (msg.embeds[0].footer.text or ""):
                existing = msg
                break
        await post_or_update(channel, existing, embed, banner_key="tickets", view=PanelView(),
                             force=existing is not None and not existing.components)
        if existing is None:
            log.info("Ticket-Panel gepostet.")

    @app_commands.command(name="ticket", description="Privates Ticket an die Admins öffnen")
    @app_commands.guild_only()
    async def ticket(self, interaction: discord.Interaction):
        await open_ticket(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
