"""
Konfiguration für den Mancave-Server.

Hier passt du alles an, was du später erweitern willst:
  - Servername
  - Rollen (Name, Farbe, Rechte, Reihenfolge)
  - Kategorien und Kanäle
  - Regel-Text und Willkommensnachricht

Das Setup ist idempotent: Du kannst hier einfach neue Einträge ergänzen und
das Setup erneut laufen lassen (Bot neu starten oder /setup im Server).
Vorhandenes wird nur angepasst, nichts wird doppelt angelegt.
Achtung: Wenn du einen NAMEN änderst, legt das Skript eine neue Rolle bzw.
einen neuen Kanal an (es erkennt Dinge am Namen). Alte Einträge dann manuell löschen.
"""

import discord

# --------------------------------------------------------------------------- #
# Allgemein
# --------------------------------------------------------------------------- #

SERVER_NAME = "Mancave"

# Verifizierung per ✅-Reaktion?
#   False -> Jeder, der joint, sieht SOFORT alle Kanäle und kann schreiben.
#            Funktioniert auch, wenn der Bot gerade offline ist.
#   True  -> Neue Leute bekommen "Unverified" und sehen nur den Regelkanal,
#            bis sie mit ✅ zustimmen (Bot muss dafür dauerhaft laufen).
VERIFICATION_ENABLED = False

# Beim Start des Bots automatisch das komplette Setup ausführen?
RUN_SETUP_ON_START = True

# Nur bei VERIFICATION_ENABLED = True:
# Bestehende Mitglieder ohne "Mitglied"/"Unverified" bekommen beim Setup
# automatisch "Unverified" (sie müssen dann auch erst den Regeln zustimmen).
# Der Server-Owner und Bots sind davon ausgenommen.
ASSIGN_UNVERIFIED_TO_EXISTING = True

# Nur bei VERIFICATION_ENABLED = True:
# Soll #regeln-und-zustimmung nach der Verifizierung weiterhin sichtbar sein?
#   True  -> alle sehen den Kanal (Mitglieder können die Regeln nachlesen)
#   False -> nur Unverified (und Admins) sehen ihn
RULES_VISIBLE_AFTER_VERIFY = True

VERIFY_EMOJI = "✅"

# --------------------------------------------------------------------------- #
# Rollen-Namen, auf die der Code direkt zugreift (nicht umbenennen, ohne es
# hier anzupassen)
# --------------------------------------------------------------------------- #

ROLE_ADMIN = "Admin / Mod"
ROLE_MEMBER = "Grinder"
# Frühere Namen der Standardrolle – werden beim Setup automatisch umbenannt
ROLE_MEMBER_OLD_NAMES = ["Mitglied"]
ROLE_UNVERIFIED = "Unverified"

# --------------------------------------------------------------------------- #
# Rollen – von OBEN (höchste) nach UNTEN (niedrigste) sortiert.
# Diese Reihenfolge wird im Server als Hierarchie gesetzt.
#
#   name        -> Rollenname
#   color       -> Farbe als Hex-Zahl
#   hoist       -> separat in der Mitgliederliste anzeigen
#   member      -> True = sieht alle normalen Kanäle (wie "Grinder")
#   verification_only -> Rolle wird nur bei VERIFICATION_ENABLED = True angelegt
#   permissions -> Server-weite Rechte (Standard: keine Extra-Rechte)
# --------------------------------------------------------------------------- #

ROLES = [
    {
        "name": ROLE_ADMIN,
        "color": 0xE74C3C,  # Rot
        "hoist": True,
        "member": True,
        # Moderationsrechte, aber bewusst KEIN "Administrator"
        "permissions": discord.Permissions(
            manage_channels=True,
            manage_roles=True,
            manage_messages=True,
            manage_nicknames=True,
            kick_members=True,
            ban_members=True,
            moderate_members=True,
            view_audit_log=True,
            mention_everyone=True,
            mute_members=True,
            move_members=True,
            deafen_members=True,
        ),
    },
    {"name": "König Krypto", "color": 0xF7931A, "hoist": True, "member": True},  # Bitcoin-Gold
    {"name": "Skalierer", "color": 0x9B59B6, "hoist": True, "member": True},     # Lila
    {"name": "Saftler", "color": 0x2ECC71, "hoist": True, "member": True},       # Grün
    {"name": "Niche", "color": 0x1ABC9C, "hoist": True, "member": True},         # Türkis
    {"name": "Gooner", "color": 0x3498DB, "hoist": True, "member": True},        # Blau
    {"name": ROLE_MEMBER, "color": 0x95A5A6, "hoist": False, "member": True},    # Grau – bekommt jeder sofort beim Join
    {"name": ROLE_UNVERIFIED, "color": 0x546E7A, "hoist": False, "member": False,
     "verification_only": True},  # Dunkelgrau
]

# --------------------------------------------------------------------------- #
# Kategorien & Kanäle
#
# Kategorie "access":
#   "members" -> nur Rollen mit member=True sehen die Kategorie
#   "admin"   -> nur ROLE_ADMIN sieht die Kategorie
#
# Kanal-Felder:
#   name   -> Kanalname (Textkanäle: klein, mit Bindestrichen)
#   type   -> "text" oder "voice"
#   topic  -> Kanalbeschreibung (nur Text)
#   mode   -> optional:
#               "rules"    -> Regel-/Verifizierungskanal (für Unverified sichtbar)
#               "readonly" -> Mitglieder können lesen, aber nicht schreiben
# --------------------------------------------------------------------------- #

RULES_CHANNEL = "regeln-und-zustimmung"
WELCOME_CHANNEL = "willkommen"
LOG_CHANNEL = "bot-logs"

CATEGORIES = [
    {
        "name": "📜 START",
        "access": "members",
        "channels": [
            {"name": RULES_CHANNEL, "type": "text", "mode": "rules",
             "topic": (f"Lies die Regeln und reagiere mit {VERIFY_EMOJI}, um freigeschaltet zu werden."
                       if VERIFICATION_ENABLED else "Die Regeln der Mancave – bitte einmal durchlesen.")},
            {"name": WELCOME_CHANNEL, "type": "text", "mode": "readonly",
             "topic": "Willkommen in der Mancave!"},
            {"name": "vorstellung", "type": "text",
             "topic": "Stell dich vor: Wer bist du, woran arbeitest du, was ist dein Ziel?"},
        ],
    },
    {
        "name": "💬 COMMUNITY",
        "access": "members",
        "channels": [
            {"name": "allgemeiner-chat", "type": "text", "topic": "Alles, was sonst nirgends reinpasst."},
            {"name": "self-improvement", "type": "text", "topic": "Gym, Mindset, Routinen, Bücher, Disziplin."},
            {"name": "chill-area", "type": "text", "topic": "Abschalten, Memes, Off-Topic."},
            {"name": "erfolge-feiern", "type": "text", "topic": "Teile deine Wins – egal wie klein. 🏆"},
        ],
    },
    {
        "name": "💰 BUSINESS & MONEY",
        "access": "members",
        "channels": [
            {"name": "krypto", "type": "text", "topic": "Coins, On-Chain, News. Keine Finanzberatung."},
            {"name": "trading", "type": "text", "topic": "Setups, Charts, Trade-Reviews. Keine Finanzberatung."},
            {"name": "aktien", "type": "text", "topic": "Aktien, ETFs, Langfrist-Investments."},
            {"name": "website-bauen", "type": "text", "topic": "Webdesign, Hosting, SEO, No-Code & Code."},
            {"name": "affiliate-marketing", "type": "text", "topic": "Programme, Traffic, Funnels, Conversions."},
            {"name": "business-ideen", "type": "text", "topic": "Ideen pitchen, Feedback holen, gemeinsam bauen."},
            {"name": "ressourcen-tools", "type": "text", "topic": "Tools, Kurse, Bücher, Links – das Beste gesammelt."},
        ],
    },
    {
        "name": "🎙️ VOICE",
        "access": "members",
        "channels": [
            {"name": "Grind Session", "type": "voice"},
            {"name": "Chill Voice", "type": "voice"},
            {"name": "Meeting/Call", "type": "voice"},
        ],
    },
    {
        "name": "🔒 ADMIN",
        "access": "admin",
        "channels": [
            {"name": "admin-chat", "type": "text", "topic": "Interner Admin-/Mod-Chat."},
            {"name": LOG_CHANNEL, "type": "text", "topic": "Automatische Logs vom Bot."},
        ],
    },
]

# --------------------------------------------------------------------------- #
# Texte
# --------------------------------------------------------------------------- #

# Wird im Footer der Regel-Nachricht versteckt, damit der Bot "seine" Nachricht
# beim nächsten Setup wiederfindet und nicht doppelt postet. Nicht ändern.
RULES_MESSAGE_MARKER = "mancave-rules"

RULES_TITLE = "📜 Regeln & Community-Guidelines"

RULES_DESCRIPTION = (
    "Willkommen in der **Mancave**! Bevor es losgeht, lies dir bitte die Regeln durch.\n\n"
    "**1.** [PLATZHALTER – Regel 1]\n"
    "**2.** [PLATZHALTER – Regel 2]\n"
    "**3.** [PLATZHALTER – Regel 3]\n"
    "**4.** [PLATZHALTER – Regel 4]\n"
    "**5.** [PLATZHALTER – Regel 5]\n\n"
    "⚠️ *Nichts auf diesem Server ist Finanzberatung.*"
)
if VERIFICATION_ENABLED:
    RULES_DESCRIPTION += (
        f"\n\nReagiere mit {VERIFY_EMOJI} auf diese Nachricht, um den Regeln zuzustimmen "
        "und alle Kanäle freizuschalten."
    )

RULES_COLOR = 0xF7931A

# Platzhalter:
#   {mention}        -> Erwähnung des neuen Mitglieds
#   {ch_<kanalname>} -> klickbarer Link zu einem Textkanal
#                       (Bindestriche werden zu Unterstrichen, z. B. {ch_erfolge_feiern})
WELCOME_MESSAGE = (
    "🔥 Willkommen in der Mancave, {mention}! "
    "Stell dich kurz in {ch_vorstellung} vor und dann: ab ans Saften. 💪"
)
