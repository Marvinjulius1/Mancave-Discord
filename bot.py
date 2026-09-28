"""
Mancave Discord-Bot

Baut den kompletten Server auf (Rollen, Kategorien, Kanäle, Rechte, Regel-Nachricht)
und kümmert sich danach um die Verifizierung:

  - Neues Mitglied joint           -> bekommt "Unverified"
  - Reaktion ✅ auf die Regeln      -> "Unverified" weg, "Mitglied" dazu
  - /setup (nur Admins)            -> Setup erneut ausführen

Alle weiteren Features (XP, Check-ins, Gym-Log, Kurse, Tickets, ...) liegen als
Module in cogs/ und werden über config.EXTENSIONS geladen.

Alle Namen, Farben, Kanäle und Texte stehen in config.py.
Start:  python bot.py
"""

import hashlib
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

import config  # noqa: E402  (erst nach load_dotenv, damit Module die .env sehen)
import db  # noqa: E402
from utils import SafeDict, get_role, get_text_channel, send_log  # noqa: E402

# --------------------------------------------------------------------------- #
# Grundeinrichtung
# --------------------------------------------------------------------------- #

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

if not TOKEN or not GUILD_ID:
    raise SystemExit("DISCORD_TOKEN und GUILD_ID müssen in der .env-Datei stehen (siehe .env.example).")

GUILD_ID = int(GUILD_ID)
GUILD_OBJ = discord.Object(id=GUILD_ID)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mancave")

intents = discord.Intents.default()
intents.members = True          # für on_member_join + Rollen an bestehende Mitglieder
intents.message_content = True  # für XP, Auto-Moderation und Spam-Erkennung


class MancaveBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)
        self.guild_id = GUILD_ID
        self.rules_message_id: int | None = None  # wird beim Setup gesetzt
        self._setup_done = False

    async def setup_hook(self):
        for ext in config.EXTENSIONS:
            try:
                await self.load_extension(ext)
                log.info("Modul geladen: %s", ext)
            except Exception:
                log.exception("Modul %s konnte nicht geladen werden", ext)
        # Slash-Commands nur für unseren Server registrieren (sofort verfügbar)
        self.tree.copy_global_to(guild=GUILD_OBJ)
        synced = await self.tree.sync(guild=GUILD_OBJ)
        log.info("%s Slash-Commands registriert.", len(synced))


bot = MancaveBot()


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #

def bot_overwrite() -> discord.PermissionOverwrite:
    """Der Bot selbst darf in jedem Kanal alles Nötige – so sperrt er sich nie aus."""
    return discord.PermissionOverwrite(
        view_channel=True,
        send_messages=True,
        embed_links=True,
        add_reactions=True,
        read_message_history=True,
        manage_messages=True,
        connect=True,
    )


# --------------------------------------------------------------------------- #
# Setup: Servername
# --------------------------------------------------------------------------- #

async def setup_server_name(guild: discord.Guild):
    if guild.name != config.SERVER_NAME:
        try:
            await guild.edit(name=config.SERVER_NAME, reason="Mancave-Setup")
            log.info("Servername gesetzt: %s", config.SERVER_NAME)
        except discord.Forbidden:
            log.warning("Keine Berechtigung, den Servernamen zu ändern (braucht 'Server verwalten').")

    # Server-Icon nur neu hochladen, wenn sich die Bilddatei geändert hat
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config.SERVER_ICON) if config.SERVER_ICON else None
    if icon_path and os.path.isfile(icon_path):
        with open(icon_path, "rb") as f:
            icon = f.read()
        digest = hashlib.sha256(icon).hexdigest()
        if db.kv_get("server_icon_hash") != digest or guild.icon is None:
            try:
                await guild.edit(icon=icon, reason="Mancave-Setup: Server-Icon")
                db.kv_set("server_icon_hash", digest)
                log.info("Server-Icon gesetzt: %s", config.SERVER_ICON)
            except discord.HTTPException as e:
                log.warning("Server-Icon konnte nicht gesetzt werden: %s", e)


# --------------------------------------------------------------------------- #
# Setup: Rollen
# --------------------------------------------------------------------------- #

async def setup_roles(guild: discord.Guild) -> dict[str, discord.Role]:
    """Legt alle Rollen aus config.ROLES an (oder aktualisiert sie) und sortiert sie."""
    roles: dict[str, discord.Role] = {}

    for spec in config.ROLES:
        name = spec["name"]
        color = discord.Color(spec["color"])
        hoist = spec.get("hoist", False)
        default = config.MEMBER_PERMISSIONS if spec.get("member") else discord.Permissions.none()
        perms = spec.get("permissions", default)

        role = get_role(guild, name)
        if role is None:
            role = await guild.create_role(
                name=name, colour=color, hoist=hoist, permissions=perms,
                mentionable=True, reason="Mancave-Setup",
            )
            log.info("Rolle erstellt: %s", name)
        elif role < guild.me.top_role and (
            role.colour != color or role.hoist != hoist or role.permissions != perms
        ):
            await role.edit(colour=color, hoist=hoist, permissions=perms, reason="Mancave-Setup")
            log.info("Rolle aktualisiert: %s", name)
        roles[name] = role

    # @everyone (und damit Unverified) nur Grundrechte
    everyone = guild.default_role
    if everyone.permissions != config.EVERYONE_PERMISSIONS:
        await everyone.edit(permissions=config.EVERYONE_PERMISSIONS, reason="Mancave-Setup")
        log.info("Rechte von @everyone angepasst.")

    # Hierarchie setzen: erste Rolle in der Liste = höchste Position.
    # Alle Rollen müssen UNTER der Bot-Rolle liegen, sonst darf der Bot sie nicht verschieben.
    bot_top = guild.me.top_role.position
    ordered = [roles[spec["name"]] for spec in config.ROLES]
    if len(ordered) >= bot_top:
        log.warning(
            "Rollen können nicht sortiert werden: Unter der Bot-Rolle (Position %s) ist nicht genug Platz für "
            "%s Rollen. In den Servereinstellungen > Rollen die Bot-Rolle ganz nach oben ziehen (auch wenn sie "
            "schon oben steht – einmal kurz verschieben reicht, dann nummeriert Discord neu) und /setup ausführen.",
            bot_top, len(ordered),
        )
        return roles

    target = {role: len(ordered) - i for i, role in enumerate(ordered)}  # 1 = ganz unten
    if any(role.position != pos for role, pos in target.items()):
        try:
            await guild.edit_role_positions(positions=target, reason="Mancave-Setup")
            log.info("Rollen-Hierarchie sortiert.")
        except discord.HTTPException as e:
            log.warning("Konnte Rollen nicht sortieren: %s", e)

    return roles


# --------------------------------------------------------------------------- #
# Setup: Berechtigungen
# --------------------------------------------------------------------------- #

def build_overwrites(
    guild: discord.Guild,
    roles: dict[str, discord.Role],
    access: str,
    mode: str | None = None,
) -> dict:
    """
    Baut die Kanal-Rechte:
      - @everyone (und damit Unverified) sieht nichts
      - Mitglieds-Rollen sehen "members"-Kanäle
      - nur Admin sieht "admin"-Kanäle
      - Regelkanal: für alle sichtbar, aber nur Reaktionen erlaubt
    """
    everyone = guild.default_role
    admin = roles[config.ROLE_ADMIN]
    member_roles = [roles[s["name"]] for s in config.ROLES if s.get("member")]

    ow: dict = {
        everyone: discord.PermissionOverwrite(view_channel=False),
        guild.me: bot_overwrite(),
    }

    if mode == "rules":
        # Jeder (auch Unverified) sieht den Kanal, darf nicht schreiben, aber reagieren
        ow[everyone] = discord.PermissionOverwrite(
            view_channel=True, send_messages=False, add_reactions=True, read_message_history=True,
        )
        if not config.RULES_VISIBLE_AFTER_VERIFY:
            ow[roles[config.ROLE_MEMBER]] = discord.PermissionOverwrite(view_channel=False)
        # Admins sehen ihn immer und dürfen schreiben
        ow[admin] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        return ow

    if access == "admin":
        ow[admin] = discord.PermissionOverwrite(view_channel=True)
        return ow

    # access == "members"
    for role in member_roles:
        ow[role] = discord.PermissionOverwrite(view_channel=True)

    if mode == "readonly":
        for role in member_roles:
            ow[role] = discord.PermissionOverwrite(view_channel=True, send_messages=False, add_reactions=True)
        ow[admin] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    return ow


# --------------------------------------------------------------------------- #
# Setup: Kategorien & Kanäle
# --------------------------------------------------------------------------- #

async def ensure_category(guild, name, overwrites) -> discord.CategoryChannel:
    category = discord.utils.get(guild.categories, name=name)
    if category is None:
        category = await guild.create_category(name, overwrites=overwrites, reason="Mancave-Setup")
        log.info("Kategorie erstellt: %s", name)
    elif category.overwrites != overwrites:
        await category.edit(overwrites=overwrites, reason="Mancave-Setup")
        log.info("Kategorie-Rechte aktualisiert: %s", name)
    return category


async def ensure_channel(guild, category, spec, overwrites):
    name = spec["name"]
    is_voice = spec.get("type") == "voice"
    pool = guild.voice_channels if is_voice else guild.text_channels
    channel = discord.utils.get(pool, name=name)

    if channel is None:
        if is_voice:
            channel = await category.create_voice_channel(name, overwrites=overwrites, reason="Mancave-Setup")
        else:
            channel = await category.create_text_channel(
                name, topic=spec.get("topic"), overwrites=overwrites, reason="Mancave-Setup",
            )
        log.info("Kanal erstellt: %s", name)
        return channel

    # Kanal existiert schon -> nur anpassen, was abweicht
    changes = {}
    if channel.category_id != category.id:
        changes["category"] = category
    if channel.overwrites != overwrites:
        changes["overwrites"] = overwrites
    if not is_voice and spec.get("topic") and channel.topic != spec["topic"]:
        changes["topic"] = spec["topic"]
    if changes:
        await channel.edit(**changes, reason="Mancave-Setup")
        log.info("Kanal aktualisiert: %s (%s)", name, ", ".join(changes))
    return channel


async def setup_channels(guild: discord.Guild, roles: dict[str, discord.Role]):
    for cat_spec in config.CATEGORIES:
        access = cat_spec.get("access", "members")
        # Die START-Kategorie enthält den Regelkanal – der braucht sichtbare Kategorie,
        # deshalb bekommt die Kategorie selbst die "rules"-Rechte, wenn sie ihn enthält.
        has_rules = any(c.get("mode") == "rules" for c in cat_spec["channels"])
        cat_mode = "rules" if has_rules else None
        category = await ensure_category(
            guild, cat_spec["name"], build_overwrites(guild, roles, access, cat_mode),
        )

        channels = []
        for ch_spec in cat_spec["channels"]:
            overwrites = build_overwrites(guild, roles, access, ch_spec.get("mode"))
            channels.append(await ensure_channel(guild, category, ch_spec, overwrites))
        await sort_text_channels(guild, category, [c for c in channels if isinstance(c, discord.TextChannel)])

    await sort_categories(guild)


async def sort_text_channels(guild: discord.Guild, category: discord.CategoryChannel, wanted: list):
    """Textkanäle einer Kategorie in der Reihenfolge aus der Config anordnen."""
    others = [c for c in category.text_channels if c not in wanted]  # z. B. Ticket-Kanäle
    order = wanted + sorted(others, key=lambda c: c.position)
    current = sorted(category.text_channels, key=lambda c: (c.position, c.id))
    if current == order or len(order) < 2:
        return
    base = min(c.position for c in order)
    payload = [{"id": c.id, "position": base + i} for i, c in enumerate(order)]
    try:
        await guild._state.http.bulk_channel_update(guild.id, payload, reason="Mancave-Setup")
    except discord.HTTPException as e:
        log.warning("Kanäle in %s konnten nicht sortiert werden: %s", category.name, e)


async def sort_categories(guild: discord.Guild):
    """Kategorien in der Reihenfolge aus config.CATEGORIES anordnen (Stats-Kategorie bleibt ganz oben,
    selbst angelegte Kategorien kommen ans Ende)."""
    wanted = [discord.utils.get(guild.categories, name=c["name"]) for c in config.CATEGORIES]
    wanted = [c for c in wanted if c]
    others = [c for c in guild.categories if c not in wanted]
    top = [c for c in others if c.name == config.STATS_CATEGORY]
    order = top + wanted + [c for c in others if c not in top]
    current = sorted(guild.categories, key=lambda c: (c.position, c.id))
    if current == order:
        return
    payload = [{"id": c.id, "position": i} for i, c in enumerate(order)]
    try:
        # Ein einziger API-Aufruf für alle Kategorien statt vieler Einzel-Edits
        await guild._state.http.bulk_channel_update(guild.id, payload, reason="Mancave-Setup")
        log.info("Kategorien sortiert.")
    except discord.HTTPException as e:
        log.warning("Kategorien konnten nicht sortiert werden: %s", e)


# --------------------------------------------------------------------------- #
# Setup: Regel-Nachricht
# --------------------------------------------------------------------------- #

def channel_placeholders(guild: discord.Guild) -> SafeDict:
    """{ch_kanal_name} -> klickbarer Link zum Textkanal."""
    values = SafeDict()
    values.update({f"ch_{c.name.replace('-', '_')}": c.mention for c in guild.text_channels})
    return values


def build_rules_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title=config.RULES_TITLE,
        description=config.RULES_DESCRIPTION.format_map(channel_placeholders(guild)),
        color=config.RULES_COLOR,
    )
    embed.set_footer(text=f"{config.SERVER_NAME} • {config.RULES_MESSAGE_MARKER}")
    return embed


async def setup_rules_message(guild: discord.Guild):
    """Postet die Regel-Nachricht – oder aktualisiert die vorhandene."""
    channel = get_text_channel(guild, config.RULES_CHANNEL)
    if channel is None:
        log.error("Regelkanal #%s nicht gefunden.", config.RULES_CHANNEL)
        return

    embed = build_rules_embed(guild)
    message = None

    # Eigene, schon gepostete Regel-Nachricht suchen (am Marker im Footer erkennbar)
    async for msg in channel.history(limit=50):
        if msg.author == guild.me and msg.embeds:
            footer = msg.embeds[0].footer.text or ""
            if config.RULES_MESSAGE_MARKER in footer:
                message = msg
                break

    if message is None:
        message = await channel.send(embed=embed)
        log.info("Regel-Nachricht gepostet.")
    elif message.embeds[0].to_dict() != embed.to_dict():
        await message.edit(embed=embed)
        log.info("Regel-Nachricht aktualisiert.")

    # ✅-Reaktion sicherstellen
    if not any(str(r.emoji) == config.VERIFY_EMOJI and r.me for r in message.reactions):
        await message.add_reaction(config.VERIFY_EMOJI)

    bot.rules_message_id = message.id


# --------------------------------------------------------------------------- #
# Setup: Bestehende Mitglieder
# --------------------------------------------------------------------------- #

async def setup_existing_members(guild: discord.Guild, roles: dict[str, discord.Role]):
    """Gibt allen Mitgliedern ohne Mitglied/Unverified die Rolle Unverified."""
    if not config.ASSIGN_UNVERIFIED_TO_EXISTING:
        return
    unverified = roles[config.ROLE_UNVERIFIED]
    member_role = roles[config.ROLE_MEMBER]
    for member in guild.members:
        if member.bot or member.id == guild.owner_id:
            continue
        if unverified in member.roles or member_role in member.roles:
            continue
        try:
            await member.add_roles(unverified, reason="Mancave-Setup: noch nicht verifiziert")
            log.info("Unverified vergeben an: %s", member)
        except discord.HTTPException as e:
            log.warning("Konnte %s nicht Unverified geben: %s", member, e)


# --------------------------------------------------------------------------- #
# Komplettes Setup
# --------------------------------------------------------------------------- #

async def run_setup(guild: discord.Guild):
    log.info("=== Setup startet für '%s' ===", guild.name)
    await setup_server_name(guild)
    roles = await setup_roles(guild)
    await setup_channels(guild, roles)
    await setup_rules_message(guild)
    await setup_existing_members(guild, roles)
    log.info("=== Setup fertig ===")
    await send_log(guild, "✅ Server-Setup abgeschlossen.")
    # Module (Tickets, Stats, ...) richten jetzt ihre eigenen Nachrichten/Kanäle ein
    bot.dispatch("mancave_ready", guild)


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #

@bot.event
async def on_ready():
    log.info("Eingeloggt als %s", bot.user)
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        log.error("Server %s nicht gefunden – ist der Bot eingeladen und GUILD_ID korrekt?", GUILD_ID)
        return

    # on_ready kann bei Reconnects mehrfach kommen -> Setup nur einmal pro Start
    if bot._setup_done:
        return
    bot._setup_done = True

    if config.RUN_SETUP_ON_START:
        await run_setup(guild)
    else:
        # Auch ohne Setup muss der Bot wissen, welche Nachricht die Regel-Nachricht ist
        await setup_rules_message(guild)
        bot.dispatch("mancave_ready", guild)


@bot.event
async def on_message(message: discord.Message):
    """Zentrale Nachrichten-Verarbeitung: erst Auto-Moderation, dann XP & Co."""
    if message.guild is None or message.guild.id != GUILD_ID or message.author.bot:
        return
    if not isinstance(message.author, discord.Member):
        return
    moderation = bot.get_cog("Moderation")
    if moderation and await moderation.check_message(message):
        return  # Nachricht wurde gelöscht -> keine XP
    bot.dispatch("mancave_message", message)


@bot.event
async def on_member_join(member: discord.Member):
    if member.guild.id != GUILD_ID or member.bot:
        return
    unverified = get_role(member.guild, config.ROLE_UNVERIFIED)
    if unverified:
        await member.add_roles(unverified, reason="Neues Mitglied – noch nicht verifiziert")
    await send_log(member.guild, f"📥 {member.mention} ist dem Server beigetreten.")


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Verifizierung: ✅ auf die Regel-Nachricht -> Mitglied."""
    if payload.guild_id != GUILD_ID or payload.message_id != bot.rules_message_id:
        return
    if str(payload.emoji) != config.VERIFY_EMOJI:
        return
    member = payload.member
    if member is None or member.bot:
        return

    guild = member.guild
    unverified = get_role(guild, config.ROLE_UNVERIFIED)
    member_role = get_role(guild, config.ROLE_MEMBER)
    if member_role is None:
        log.error("Rolle '%s' fehlt – /setup ausführen.", config.ROLE_MEMBER)
        return
    if member_role in member.roles:
        return  # schon verifiziert

    try:
        await member.add_roles(member_role, reason="Regeln akzeptiert")
        if unverified and unverified in member.roles:
            await member.remove_roles(unverified, reason="Regeln akzeptiert")
    except discord.Forbidden:
        await send_log(guild, f"⚠️ Konnte {member.mention} nicht verifizieren – Bot-Rolle zu niedrig?")
        return

    await send_log(guild, f"✅ {member.mention} hat die Regeln akzeptiert.")

    # Willkommensnachricht in #willkommen
    welcome = get_text_channel(guild, config.WELCOME_CHANNEL)
    if welcome:
        values = channel_placeholders(guild)
        values["mention"] = member.mention
        text = config.WELCOME_MESSAGE.format_map(values)
        await welcome.send(text)


# --------------------------------------------------------------------------- #
# Slash-Commands
# --------------------------------------------------------------------------- #

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        text = "⛔ Dafür fehlen dir die Rechte."
    elif isinstance(error, app_commands.CommandOnCooldown):
        text = f"⏳ Kurz warten – noch {error.retry_after:.0f} Sek."
    else:
        log.error("Fehler in /%s", interaction.command.name if interaction.command else "?", exc_info=error)
        text = "❌ Da ist etwas schiefgelaufen. Die Admins sehen den Fehler im Log."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except discord.HTTPException:
        pass


@bot.tree.command(name="setup", description="Server-Struktur erneut aufbauen/aktualisieren", guild=GUILD_OBJ)
@app_commands.default_permissions(administrator=True)
@app_commands.guild_only()
async def setup_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await run_setup(interaction.guild)
    except discord.HTTPException as e:
        log.exception("Setup fehlgeschlagen")
        await interaction.followup.send(f"❌ Setup fehlgeschlagen: {e}", ephemeral=True)
        return
    await interaction.followup.send("✅ Setup abgeschlossen.", ephemeral=True)


if __name__ == "__main__":
    bot.run(TOKEN, log_handler=None)
