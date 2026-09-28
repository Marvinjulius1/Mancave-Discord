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

# Server-Icon: wird beim Setup gesetzt, sobald sich die Datei ändert (leer = nicht anfassen).
# Am besten ein quadratisches Bild mit mind. 512×512 Pixeln.
SERVER_ICON = "assets/server-icon.png"

# Beim Start des Bots automatisch das komplette Setup ausführen?
RUN_SETUP_ON_START = True

# Bestehende Mitglieder ohne "Mitglied"/"Unverified" bekommen beim Setup
# automatisch "Unverified" (sie müssen dann auch erst den Regeln zustimmen).
# Der Server-Owner und Bots sind davon ausgenommen.
ASSIGN_UNVERIFIED_TO_EXISTING = True

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
ROLE_MEMBER = "Mitglied"
ROLE_UNVERIFIED = "Unverified"
ROLE_RECRUITER = "Recruiter"
ROLE_CHAMPION = "Challenge-Champion"

# --------------------------------------------------------------------------- #
# Rollen – von OBEN (höchste) nach UNTEN (niedrigste) sortiert.
# Diese Reihenfolge wird im Server als Hierarchie gesetzt.
#
#   name        -> Rollenname
#   color       -> Farbe als Hex-Zahl
#   hoist       -> separat in der Mitgliederliste anzeigen
#   member      -> True = sieht alle normalen Kanäle (wie "Mitglied")
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
    # Auszeichnungs-Rollen (werden automatisch vergeben)
    {"name": ROLE_CHAMPION, "color": 0xF1C40F, "hoist": False, "member": True},  # Gelb
    {"name": ROLE_RECRUITER, "color": 0xE91E63, "hoist": False, "member": True}, # Pink
    {"name": ROLE_MEMBER, "color": 0x95A5A6, "hoist": False, "member": True},    # Grau
    {"name": ROLE_UNVERIFIED, "color": 0x546E7A, "hoist": False, "member": False},  # Dunkelgrau
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
TICKET_PANEL_CHANNEL = "ticket-erstellen"
SELF_IMPROVEMENT_CHANNEL = "self-improvement"
WINS_CHANNEL = "erfolge-feiern"
HALL_OF_FAME_CHANNEL = "hall-of-fame"
CHECKIN_CHANNEL = "daily-checkin"
GYM_CHANNEL = "gym-log"
CHALLENGE_CHANNEL = "challenges"
LEVELUP_CHANNEL = "level-ups"
CRYPTO_CHANNEL = "krypto"
STOCKS_CHANNEL = "aktien"
IDEAS_CHANNEL = "business-ideen"
TICKET_CATEGORY = "🎫 TICKETS"
INVITE_RANKING_CHANNEL = "invite-ranking"
NEWS_POLITICS_CHANNEL = "politik-news"
NEWS_MARKETS_CHANNEL = "börsen-news"
NEWS_CRYPTO_CHANNEL = "krypto-news"

CATEGORIES = [
    {
        "name": "📜 START",
        "access": "members",
        "channels": [
            {"name": RULES_CHANNEL, "type": "text", "mode": "rules",
             "topic": f"Lies die Regeln und reagiere mit {VERIFY_EMOJI}, um freigeschaltet zu werden."},
            {"name": WELCOME_CHANNEL, "type": "text", "mode": "readonly",
             "topic": "Willkommen in der Mancave!"},
            {"name": "vorstellung", "type": "text",
             "topic": "Stell dich vor: Wer bist du, woran arbeitest du, was ist dein Ziel?"},
            {"name": TICKET_PANEL_CHANNEL, "type": "text", "mode": "readonly",
             "topic": "Frage an die Admins? Klick auf den Button und öffne ein privates Ticket."},
        ],
    },
    {
        "name": "💬 COMMUNITY",
        "access": "members",
        "channels": [
            {"name": "allgemeiner-chat", "type": "text", "topic": "Alles, was sonst nirgends reinpasst."},
            {"name": SELF_IMPROVEMENT_CHANNEL, "type": "text", "topic": "Gym, Mindset, Routinen, Bücher, Disziplin."},
            {"name": "buchempfehlungen", "type": "text",
             "topic": "Bücher, die dich weitergebracht haben: Titel, Autor, wichtigste Erkenntnis. 📚"},
            {"name": CHECKIN_CHANNEL, "type": "text",
             "topic": "Täglich /checkin: Was hast du heute für Körper, Business und Wissen getan? 🔥"},
            {"name": GYM_CHANNEL, "type": "text", "topic": "Trainings mit /workout eintragen. Leaderboard: /gym-leaderboard 💪"},
            {"name": CHALLENGE_CHANNEL, "type": "text", "mode": "readonly",
             "topic": "Wochen-Challenges: Mitmachen per Button, täglich /challenge-checkin."},
            {"name": "chill-area", "type": "text", "topic": "Abschalten, Memes, Off-Topic."},
            {"name": WINS_CHANNEL, "type": "text", "topic": "Teile deine Wins – egal wie klein. 🏆 Viele 🔥 = Hall of Fame."},
            {"name": HALL_OF_FAME_CHANNEL, "type": "text", "mode": "readonly",
             "topic": "Die größten Wins der Mancave – automatisch ab genug 🔥-Reaktionen."},
            {"name": LEVELUP_CHANNEL, "type": "text", "mode": "readonly",
             "topic": "Level-Ups und neue Ränge. /rank zeigt deinen Fortschritt."},
            {"name": INVITE_RANKING_CHANNEL, "type": "text", "mode": "readonly",
             "topic": "Wer hat die meisten Leute in die Mancave geholt? Wird automatisch aktualisiert. 🔗"},
        ],
    },
    {
        "name": "📰 NEWS",
        "access": "members",
        "channels": [
            {"name": NEWS_POLITICS_CHANNEL, "type": "text", "mode": "readonly",
             "topic": "Politik-Schlagzeilen – automatisch morgens & abends."},
            {"name": NEWS_MARKETS_CHANNEL, "type": "text", "mode": "readonly",
             "topic": "Börse, Wirtschaft & Trading – automatisch morgens & abends. Keine Finanzberatung."},
            {"name": NEWS_CRYPTO_CHANNEL, "type": "text", "mode": "readonly",
             "topic": "Krypto-News – automatisch morgens & abends. Keine Finanzberatung."},
        ],
    },
    {
        "name": "🪙 KRYPTO",
        "access": "members",
        "channels": [
            {"name": CRYPTO_CHANNEL, "type": "text", "topic": "Coins, On-Chain, Projekte. Morgens Krypto-Report. Keine Finanzberatung."},
            {"name": "krypto-analysen", "type": "text", "topic": "Charts, Research, Tokenomics – mit Begründung, nicht nur Moon-Emojis."},
            {"name": "wallets-und-sicherheit", "type": "text", "topic": "Wallets, Börsen, Sicherheit. NIEMALS Seed-Phrase oder Private Key teilen!"},
        ],
    },
    {
        "name": "🐸 MEMECOINS",
        "access": "members",
        "channels": [
            {"name": "memecoins-chat", "type": "text", "topic": "Memecoins, Narrative, Hype. Extrem riskant – nur Spielgeld!"},
            {"name": "memecoin-calls", "type": "text", "topic": "Calls mit Contract-Adresse & Begründung. Keine Pump-&-Dump-Aufrufe. DYOR."},
            {"name": "rug-warnungen", "type": "text", "topic": "Scams, Rugpulls, Honeypots melden – schützt die anderen. 🚨"},
        ],
    },
    {
        "name": "📊 TRADING",
        "access": "members",
        "channels": [
            {"name": "trading", "type": "text", "topic": "Allgemeiner Trading-Talk. Keine Finanzberatung."},
            {"name": "trade-setups", "type": "text", "topic": "Setups mit Entry, Stop-Loss, Take-Profit und Begründung."},
            {"name": "trading-journal", "type": "text", "topic": "Deine Trades inkl. Verluste – ehrlich reflektieren, besser werden."},
            {"name": STOCKS_CHANNEL, "type": "text", "topic": "Aktien, ETFs, Langfrist-Investments. Morgens Börsen-Report (Mo–Fr)."},
        ],
    },
    {
        "name": "📦 DROPSHIPPING",
        "access": "members",
        "channels": [
            {"name": "dropshipping-chat", "type": "text", "topic": "Shops, Stores, Ads, Erfahrungen."},
            {"name": "produkt-research", "type": "text", "topic": "Winning Products, Trends, Nischen – mit Zahlen."},
            {"name": "lieferanten-und-shops", "type": "text", "topic": "Lieferanten, Agenten, Shopify-Apps, Tools."},
        ],
    },
    {
        "name": "🔗 AFFILIATE MARKETING",
        "access": "members",
        "channels": [
            {"name": "affiliate-marketing", "type": "text", "topic": "Allgemeiner Affiliate-Talk: Strategien, Erfahrungen, Zahlen."},
            {"name": "affiliate-programme", "type": "text", "topic": "Gute Programme & Provisionen teilen (keine eigenen Referral-Links spammen)."},
            {"name": "traffic-und-funnels", "type": "text", "topic": "SEO, Social, Paid Ads, Landingpages, E-Mail-Funnels."},
        ],
    },
    {
        "name": "🛍️ TIKTOK SHOP",
        "access": "members",
        "channels": [
            {"name": "tiktok-shop-chat", "type": "text", "topic": "TikTok Shop, Creator-Affiliate, Seller-Erfahrungen."},
            {"name": "virale-produkte", "type": "text", "topic": "Produkte, die gerade auf TikTok gehen – mit Link/Video."},
            {"name": "content-ideen", "type": "text", "topic": "Hooks, Video-Ideen, Skripte, was gerade performt."},
        ],
    },
    {
        "name": "🤖 KI",
        "access": "members",
        "channels": [
            {"name": "chatgpt", "type": "text", "topic": "ChatGPT: Prompts, GPTs, Workflows, Business-Anwendungen."},
            {"name": "claude-code", "type": "text", "topic": "Claude Code: Coden mit KI, Projekte, Tipps & Workflows."},
            {"name": "codex", "type": "text", "topic": "OpenAI Codex: KI-Coding-Agent, Erfahrungen & Vergleiche."},
        ],
    },
    {
        "name": "💰 BUSINESS & MONEY",
        "access": "members",
        "channels": [
            {"name": IDEAS_CHANNEL, "type": "text", "topic": "Ideen mit /idee pitchen, per 👍/👎 abstimmen, im Thread diskutieren."},
            {"name": "website-bauen", "type": "text", "topic": "Webdesign, Hosting, SEO, No-Code & Code."},
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
    {
        # Hier legt der Bot die privaten Ticket-Kanäle an
        "name": TICKET_CATEGORY,
        "access": "admin",
        "channels": [],
    },
]

# --------------------------------------------------------------------------- #
# Texte
# --------------------------------------------------------------------------- #

# Wird im Footer der Regel-Nachricht versteckt, damit der Bot "seine" Nachricht
# beim nächsten Setup wiederfindet und nicht doppelt postet. Nicht ändern.
RULES_MESSAGE_MARKER = "mancave-rules"

RULES_TITLE = "📜 Regeln & Community-Guidelines"

# Platzhalter {ch_<kanalname>} werden zu klickbaren Kanal-Links (wie bei WELCOME_MESSAGE)
RULES_DESCRIPTION = (
    "Willkommen in der **Mancave** – dem Ort für Leute, die jeden Tag besser werden wollen: "
    "Körper, Business, Wissen. Bevor es losgeht, lies dir die Regeln durch.\n\n"

    "**1. Respekt ist Pflicht** 🤝\n"
    "Keine Beleidigungen, kein Rassismus, keine Diskriminierung, kein Mobbing. "
    "Harte Kritik an Ideen ist okay – Angriffe auf Personen nicht.\n\n"

    "**2. Kein Spam & keine Eigenwerbung** 🚫\n"
    "Keine Werbung, Referral-Links oder Einladungen zu anderen Servern ohne Erlaubnis der Admins. "
    "Keine Massen-Pings, kein Flooding. Links sind ab Level 3 freigeschaltet.\n\n"

    "**3. Keine Scams & kein Shilling** 🪙\n"
    "Keine Pump-&-Dump-Aufrufe, keine „garantierten“ Gewinne, keine Fake-Gewinnbeweise, "
    "keine DMs mit Investment-Angeboten. Wer andere abzocken will, fliegt sofort.\n\n"

    "**4. Keine Finanzberatung** ⚠️\n"
    "Alles zu Krypto, Trading, Aktien & Co. ist Meinung und Erfahrungsaustausch – keine Anlageberatung. "
    "Jeder ist für seine eigenen Entscheidungen verantwortlich. Investiere nur, was du verlieren kannst.\n\n"

    "**5. Richtiger Kanal, richtiges Thema** 📂\n"
    "Poste in den passenden Kanal. Off-Topic gehört in {ch_chill_area}, Wins in {ch_erfolge_feiern}, "
    "Ideen per `/idee` in {ch_business_ideen}.\n\n"

    "**6. Keine NSFW- oder illegalen Inhalte** 🔞\n"
    "Keine pornografischen, gewaltverherrlichenden oder illegalen Inhalte – auch nicht als Link oder Meme. "
    "Keine Anleitungen zu Betrug, Steuerhinterziehung oder Ähnlichem.\n\n"

    "**7. Privatsphäre schützen** 🔒\n"
    "Keine privaten Daten, Screenshots aus DMs oder Fotos anderer ohne deren Zustimmung.\n\n"

    "**8. Mehrwert liefern** 💪\n"
    "Hier wird geteilt, nicht nur genommen. Hilf anderen, teile Erfahrungen und Wissen, "
    "feiere die Wins der anderen mit. Wer nur konsumiert, verpasst das Beste.\n\n"

    "**9. Anweisungen des Teams folgen** 🛡️\n"
    "Admins & Mods haben das letzte Wort. Probleme oder Fragen? Öffne ein Ticket in {ch_ticket_erstellen} – "
    "nicht öffentlich diskutieren.\n\n"

    "**Konsequenzen:** Verwarnung → Timeout → Kick → Bann. Bei Scam, Hass oder illegalen Inhalten "
    "gibt's direkt den Bann. Es gelten außerdem die Discord-Nutzungsbedingungen.\n\n"

    f"✅ Reagiere mit {VERIFY_EMOJI} auf diese Nachricht, um den Regeln zuzustimmen "
    "und alle Kanäle freizuschalten."
)

RULES_COLOR = 0xF7931A

# Platzhalter:
#   {mention}        -> Erwähnung des neuen Mitglieds
#   {ch_<kanalname>} -> klickbarer Link zu einem Textkanal
#                       (Bindestriche werden zu Unterstrichen, z. B. {ch_erfolge_feiern})
WELCOME_MESSAGE = (
    "🔥 Willkommen in der Mancave, {mention}! "
    "Stell dich kurz in {ch_vorstellung} vor, mach deinen ersten `/checkin` in {ch_daily_checkin} "
    "und dann: ab ans Saften. 💪"
)

# =========================================================================== #
#                               FEATURES
# =========================================================================== #

# Zeitzone für "heute", Streaks und geplante Posts
TIMEZONE = "Europe/Berlin"

# Module, die beim Start geladen werden. Zum Deaktivieren einfach auskommentieren.
EXTENSIONS = [
    "cogs.moderation",
    "cogs.leveling",
    "cogs.checkin",
    "cogs.fitness",
    "cogs.markets",
    "cogs.news",
    "cogs.hall_of_fame",
    "cogs.ideas",
    "cogs.daily",
    "cogs.challenges",
    "cogs.tickets",
    "cogs.stats",
    "cogs.invites",
    "cogs.coach",
    "cogs.dashboard",
]

# --------------------------------------------------------------------------- #
# XP & Level
#
# Pro Level braucht man 5·L² + 50·L + 100 XP (L = aktuelles Level).
# Level 5 ≈ 1.150 XP · Level 10 ≈ 4.675 XP · Level 20 ≈ 23.850 XP
# Level 30 ≈ 67.500 XP · Level 40 ≈ 145.700 XP
# --------------------------------------------------------------------------- #

XP_PER_MESSAGE = (15, 25)      # zufällig zwischen min und max
XP_COOLDOWN_SECONDS = 60       # nur eine XP-Nachricht pro Minute zählt (Anti-Spam)
XP_MIN_MESSAGE_LENGTH = 3      # kürzere Nachrichten ("ok") geben keine XP
XP_VOICE_PER_MINUTE = 5        # im Voice mit mind. 1 weiteren Person, nicht taub gestellt
XP_EXCLUDED_CHANNELS = [LOG_CHANNEL, "admin-chat"]

# Bonus-XP für Aktionen
XP_CHECKIN = 40
XP_STREAK_BONUS = {7: 150, 30: 750, 100: 3000}   # einmalig beim Erreichen der Serie
XP_WORKOUT = 30
XP_WORKOUT_MAX_PER_DAY = 2     # so viele Workouts pro Tag geben XP
XP_IDEA = 20
XP_HALL_OF_FAME = 100
XP_CHALLENGE_CHECKIN = 20
XP_CHALLENGE_COMPLETE = 250

# Rang-Rollen: ab welchem Level welche Rolle automatisch vergeben wird (aufsteigend).
# Niedrigere Rang-Rollen werden beim Aufstieg entfernt. Manuell vergebene
# höhere Ränge werden nie weggenommen.
LEVEL_ROLES = [
    (5, "Gooner"),
    (10, "Niche"),
    (20, "Saftler"),
    (30, "Skalierer"),
    (40, "König Krypto"),
]

# --------------------------------------------------------------------------- #
# Kurse & Markt-Report  (keine API-Keys nötig: CoinGecko + Yahoo Finance)
# --------------------------------------------------------------------------- #

CRYPTO_CURRENCY = "eur"
# Kürzel -> CoinGecko-ID (für /kurs; unbekannte Kürzel werden automatisch gesucht)
CRYPTO_SYMBOLS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple",
    "BNB": "binancecoin", "ADA": "cardano", "DOGE": "dogecoin", "DOT": "polkadot",
    "AVAX": "avalanche-2", "LINK": "chainlink", "LTC": "litecoin", "TRX": "tron",
    "SHIB": "shiba-inu", "PEPE": "pepe", "SUI": "sui", "TON": "the-open-network",
    "USDT": "tether", "USDC": "usd-coin", "POL": "polygon-ecosystem-token",
}
CRYPTO_REPORT_COINS = ["bitcoin", "ethereum", "solana", "ripple", "binancecoin", "cardano", "dogecoin"]

# Yahoo-Finance-Symbole -> Anzeigename
STOCK_REPORT_SYMBOLS = {
    "^GDAXI": "DAX",
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "TSLA": "Tesla",
    "AMZN": "Amazon",
}
MARKET_REPORT_TIME = (8, 0)        # Stunde, Minute
MARKET_REPORT_ENABLED = True       # Aktien-Report nur Mo–Fr, Krypto jeden Tag

# --------------------------------------------------------------------------- #
# News (RSS-Feeds, kein API-Key nötig)
# Kanal -> Liste von (Quellenname, Feed-URL). Eigene Feeds einfach ergänzen.
# --------------------------------------------------------------------------- #

NEWS_FEEDS = {
    NEWS_POLITICS_CHANNEL: [
        ("Tagesschau", "https://www.tagesschau.de/infoservices/alle-meldungen-100~rss2.xml"),
    ],
    NEWS_MARKETS_CHANNEL: [
        ("Tagesschau Wirtschaft", "https://www.tagesschau.de/wirtschaft/index~rss2.xml"),
        ("n-tv Wirtschaft", "https://www.n-tv.de/wirtschaft/rss"),
        ("finanzen.net", "https://www.finanzen.net/rss/news"),
        ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ],
    NEWS_CRYPTO_CHANNEL: [
        ("BTC-Echo", "https://www.btc-echo.de/feed/"),
        ("Cointelegraph", "https://cointelegraph.com/rss"),
    ],
}
NEWS_TIMES = [(7, 30), (18, 0)]    # Briefings um diese Uhrzeiten (Stunde, Minute)
NEWS_ITEMS_PER_BRIEFING = 8        # max. Schlagzeilen pro Kanal und Briefing
NEWS_MAX_AGE_HOURS = 24            # ältere Meldungen werden ignoriert

# --------------------------------------------------------------------------- #
# Hall of Fame
# --------------------------------------------------------------------------- #

HALL_OF_FAME_EMOJI = "🔥"
HALL_OF_FAME_THRESHOLD = 5     # so viele 🔥 (ohne den Autor selbst) braucht ein Win

# --------------------------------------------------------------------------- #
# Tägliches Zitat / Lern-Impuls (Texte in quotes.py)
# --------------------------------------------------------------------------- #

DAILY_QUOTE_TIME = (7, 0)
DAILY_QUOTE_ENABLED = True

# --------------------------------------------------------------------------- #
# Gym-Log
# --------------------------------------------------------------------------- #

WORKOUT_TYPES = ["Kraft", "Cardio", "Kampfsport", "Sport / Spiel", "Mobility / Yoga", "Sonstiges"]
# Wochen-Rückblick montags um diese Uhrzeit in #gym-log
GYM_WEEKLY_RECAP_TIME = (9, 0)

# --------------------------------------------------------------------------- #
# Auto-Moderation (Admin / Mod und alle mit "Nachrichten verwalten" sind ausgenommen)
# --------------------------------------------------------------------------- #

AUTOMOD_ENABLED = True
SPAM_MAX_MESSAGES = 6          # mehr als X Nachrichten ...
SPAM_INTERVAL_SECONDS = 8      # ... in Y Sekunden = Spam
SPAM_TIMEOUT_MINUTES = 5
DUPLICATE_MAX = 3              # gleiche Nachricht öfter als X-mal in 60 Sek. = Spam
MAX_MENTIONS = 5               # mehr Erwähnungen in einer Nachricht werden gelöscht
BLOCK_INVITE_LINKS = True      # fremde Discord-Einladungen löschen
LINK_MIN_LEVEL = 3             # Links erst ab diesem Level (stoppt Spam-Bots). 0 = aus
LINK_ALLOWED_DOMAINS = ["tenor.com", "giphy.com", "discord.com", "youtube.com", "youtu.be"]
BAD_WORDS: list[str] = []      # Wörter, die automatisch gelöscht werden (klein schreiben)
WARN_AUTO_TIMEOUT_AT = 3       # ab so vielen Verwarnungen automatischer Timeout
WARN_AUTO_TIMEOUT_MINUTES = 60

# --------------------------------------------------------------------------- #
# Server-Statistik
# --------------------------------------------------------------------------- #

STATS_CATEGORY = "📊 SERVER-STATS"
STATS_MEMBER_FORMAT = "👥 Mitglieder: {count}"

# --------------------------------------------------------------------------- #
# Einladungs-Tracking
# --------------------------------------------------------------------------- #

INVITE_REWARD_COUNT = 5        # ab so vielen (noch aktiven) Einladungen gibt's die Rolle
INVITE_REWARD_ROLE = ROLE_RECRUITER

# --------------------------------------------------------------------------- #
# KI-Coach (/coach) – braucht ANTHROPIC_API_KEY in der .env
# --------------------------------------------------------------------------- #

COACH_MODEL = "claude-opus-5"
COACH_EFFORT = "medium"        # low | medium | high – höher = gründlicher, aber teurer/langsamer
COACH_DAILY_LIMIT = 15         # Fragen pro Person und Tag (Admins unbegrenzt)
COACH_USE_CONTEXT = True       # Check-ins, Workouts & Level als Kontext mitschicken
COACH_SYSTEM_PROMPT = (
    "Du bist der Coach der Mancave, einer deutschsprachigen Self-Improvement- und Business-Community "
    "auf Discord. Die Mitglieder arbeiten an ihrem Körper (Gym, Ernährung, Schlaf), an Businesses "
    "(Online-Business, Affiliate, Websites, Krypto, Trading, Aktien) und an ihrem Wissen.\n\n"
    "So antwortest du:\n"
    "- Auf Deutsch, direkt, motivierend und ehrlich – wie ein erfahrener Mentor, nicht wie ein Lehrbuch.\n"
    "- Konkret und umsetzbar: klare nächste Schritte statt allgemeiner Tipps.\n"
    "- Kurz genug für Discord: meist unter 250 Wörtern, Aufzählungen sind gut, keine Tabellen.\n"
    "- Wenn Kontext zum Mitglied (Check-ins, Workouts) mitgeschickt wird, beziehe dich darauf.\n"
    "- Bei Geldanlage, Krypto und Trading: erkläre Prinzipien und Risiken, gib aber keine konkreten "
    "Kauf-/Verkaufsempfehlungen und weise darauf hin, dass es keine Finanzberatung ist.\n"
    "- Bei Gesundheit/Verletzungen/Medikamenten: allgemeine Infos ja, bei ernsten Themen an Arzt verweisen."
)

# --------------------------------------------------------------------------- #
# Web-Dashboard
# DASHBOARD_PORT und DASHBOARD_PASSWORD kommen aus der .env.
# Ohne Passwort ist das Dashboard nur lokal (127.0.0.1) erreichbar.
# --------------------------------------------------------------------------- #

DASHBOARD_ENABLED = True
