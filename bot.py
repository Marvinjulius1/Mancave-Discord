"""
Mancave Discord-Bot

Baut den kompletten Server auf (Rollen, Kategorien, Kanäle, Rechte, Regel-Nachricht)
und kümmert sich danach um die Verifizierung:

  - Neues Mitglied joint           -> bekommt "Unverified"
  - Reaktion ✅ auf die Regeln      -> "Unverified" weg, "Mitglied" dazu
  - /setup (nur Admins)            -> Setup erneut ausführen

Alle Namen, Farben, Kanäle und Texte stehen in config.py.
Start:  python bot.py
"""

import logging
import os

import discord
from discord import app_commands
from dotenv import load_dotenv

import config

# --------------------------------------------------------------------------- #
# Grundeinrichtung
# --------------------------------------------------------------------------- #

load_dotenv()
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
intents.message_content = True  # für spätere Erweiterungen (z. B. Chat-Befehle)


class MancaveBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.rules_message_id: int | None = None  # wird beim Setup gesetzt
        self._setup_done = False

    async def setup_hook(self):
        # Slash-Commands nur für unseren Server registrieren (sofort verfügbar)
        await self.tree.sync(guild=GUILD_OBJ)


bot = MancaveBot()


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #

def get_role(guild: discord.Guild, name: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=name)


def get_text_channel(guild: discord.Guild, name: str) -> discord.TextChannel | None:
    return discord.utils.get(guild.text_channels, name=name)


async def send_log(guild: discord.Guild, text: str):
    """Schreibt eine Zeile in #bot-logs (falls vorhanden)."""
    log.info(text)
    channel = get_text_channel(guild, config.LOG_CHANNEL)
    if channel:
        try:
            await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass


class SafeDict(dict):
    """Unbekannte {platzhalter} bleiben einfach stehen statt einen Fehler zu werfen."""

    def __missing__(self, key):
        return "{" + key + "}"


async def send_welcome(member: discord.Member):
    """Postet die Willkommensnachricht aus config.py in #willkommen."""
    guild = member.guild
    welcome = get_text_channel(guild, config.WELCOME_CHANNEL)
    if welcome is None:
        return
    values = SafeDict(mention=member.mention)
    values.update({f"ch_{c.name.replace('-', '_')}": c.mention for c in guild.text_channels})
    await welcome.send(config.WELCOME_MESSAGE.format_map(values))


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


# --------------------------------------------------------------------------- #
# Setup: Rollen
# --------------------------------------------------------------------------- #

def active_role_specs() -> list[dict]:
    """Alle Rollen aus config.ROLES – ohne "Unverified", wenn die Verifizierung aus ist."""
    return [
        s for s in config.ROLES
        if config.VERIFICATION_ENABLED or not s.get("verification_only")
    ]


async def setup_roles(guild: discord.Guild) -> dict[str, discord.Role]:
    """Legt alle Rollen aus config.ROLES an (oder aktualisiert sie) und sortiert sie."""
    roles: dict[str, discord.Role] = {}

    for spec in active_role_specs():
        name = spec["name"]
        color = discord.Color(spec["color"])
        hoist = spec.get("hoist", False)
        perms = spec.get("permissions", discord.Permissions.none())

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

    # Hierarchie setzen: erste Rolle in der Liste = höchste Position.
    # Alle Rollen müssen UNTER der Bot-Rolle liegen, sonst darf der Bot sie nicht verschieben.
    bot_top = guild.me.top_role.position
    ordered = [roles[spec["name"]] for spec in active_role_specs()]
    if len(ordered) >= bot_top:
        log.warning(
            "Die Bot-Rolle steht zu weit unten (Position %s). Zieh sie in den "
            "Servereinstellungen > Rollen ganz nach oben und führe /setup erneut aus.", bot_top,
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
      - nur Admin sieht "admin"-Kanäle
      - Regelkanal: für alle sichtbar, aber nur Reaktionen erlaubt
      - Verifizierung AUS: @everyone sieht alle "members"-Kanäle und kann schreiben
      - Verifizierung AN:  @everyone (und damit Unverified) sieht nichts,
                           nur Mitglieds-Rollen sehen "members"-Kanäle
    """
    everyone = guild.default_role
    admin = roles[config.ROLE_ADMIN]
    if config.VERIFICATION_ENABLED:
        member_roles = [roles[s["name"]] for s in active_role_specs() if s.get("member")]
    else:
        member_roles = [everyone]  # jeder auf dem Server zählt als Mitglied

    ow: dict = {
        everyone: discord.PermissionOverwrite(view_channel=False),
        guild.me: bot_overwrite(),
    }

    if mode == "rules":
        # Jeder (auch Unverified) sieht den Kanal, darf nicht schreiben, aber reagieren
        ow[everyone] = discord.PermissionOverwrite(
            view_channel=True, send_messages=False, add_reactions=True, read_message_history=True,
        )
        if config.VERIFICATION_ENABLED and not config.RULES_VISIBLE_AFTER_VERIFY:
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

        for ch_spec in cat_spec["channels"]:
            overwrites = build_overwrites(guild, roles, access, ch_spec.get("mode"))
            await ensure_channel(guild, category, ch_spec, overwrites)


# --------------------------------------------------------------------------- #
# Setup: Regel-Nachricht
# --------------------------------------------------------------------------- #

def build_rules_embed() -> discord.Embed:
    embed = discord.Embed(
        title=config.RULES_TITLE,
        description=config.RULES_DESCRIPTION,
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

    embed = build_rules_embed()
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

    # ✅-Reaktion sicherstellen (nur nötig, wenn verifiziert wird)
    if config.VERIFICATION_ENABLED and not any(str(r.emoji) == config.VERIFY_EMOJI and r.me for r in message.reactions):
        await message.add_reaction(config.VERIFY_EMOJI)

    bot.rules_message_id = message.id


# --------------------------------------------------------------------------- #
# Setup: Bestehende Mitglieder
# --------------------------------------------------------------------------- #

async def setup_existing_members(guild: discord.Guild, roles: dict[str, discord.Role]):
    """
    Verifizierung AUS: Alle bekommen "Mitglied", "Unverified" wird entfernt.
    Verifizierung AN:  Alle ohne Mitglied/Unverified bekommen "Unverified".
    """
    if not config.VERIFICATION_ENABLED:
        member_role = roles[config.ROLE_MEMBER]
        unverified = get_role(guild, config.ROLE_UNVERIFIED)  # evtl. von früher übrig
        for member in guild.members:
            if member.bot:
                continue
            try:
                if member_role not in member.roles:
                    await member.add_roles(member_role, reason="Mancave-Setup")
                    log.info("Mitglied vergeben an: %s", member)
                if unverified and unverified in member.roles:
                    await member.remove_roles(unverified, reason="Verifizierung deaktiviert")
            except discord.HTTPException as e:
                log.warning("Konnte Rollen von %s nicht anpassen: %s", member, e)
        return

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


@bot.event
async def on_member_join(member: discord.Member):
    if member.guild.id != GUILD_ID or member.bot:
        return
    await send_log(member.guild, f"📥 {member.mention} ist dem Server beigetreten.")

    if config.VERIFICATION_ENABLED:
        unverified = get_role(member.guild, config.ROLE_UNVERIFIED)
        if unverified:
            await member.add_roles(unverified, reason="Neues Mitglied – noch nicht verifiziert")
        return

    # Ohne Verifizierung: direkt Mitglied + Begrüßung
    member_role = get_role(member.guild, config.ROLE_MEMBER)
    if member_role:
        await member.add_roles(member_role, reason="Neues Mitglied")
    await send_welcome(member)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Verifizierung: ✅ auf die Regel-Nachricht -> Mitglied."""
    if not config.VERIFICATION_ENABLED:
        return
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

    await send_welcome(member)


# --------------------------------------------------------------------------- #
# Slash-Commands
# --------------------------------------------------------------------------- #

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
