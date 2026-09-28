# Mancave – Discord-Server-Bot

Baut den kompletten **Mancave**-Server automatisch auf und übernimmt die Verifizierung.

| Datei / Ordner | Inhalt |
|---|---|
| `bot.py` | Server-Setup, Verifizierung, `/setup`, lädt alle Module |
| `config.py` | **Alles zum Anpassen:** Rollen, Kanäle, Texte, XP-Werte, Ränge, Uhrzeiten, Auto-Mod, Coach … |
| `cogs/` | Die Features als einzelne Module (in `config.EXTENSIONS` an-/abschaltbar) |
| `quotes.py` | Zitate & Tages-Impulse für `#self-improvement` |
| `dashboard/` | Web-Dashboard |
| `data/mancave.db` | SQLite-Datenbank (XP, Streaks, Workouts …) – wird automatisch angelegt, nicht committen |
| `.env` | Bot-Token, Server-ID, optionale Keys (nicht committen!) |

## Was der Bot macht

### Server-Aufbau & Verifizierung
- **Rollen** (von oben nach unten):
  - **Team:** Admin › Consigliere (Vize-Admin) › Türsteher (Moderator) – sehen ADMIN-Bereich & Tickets
  - **Ränge** (automatisch nach Level): Mancave-Legende (75) › Mogul (50) › König Krypto (40) › Skalierer (30) › Saftler (20) › Hustler (15) › Niche (10) › Gooner (5)
  - **Auszeichnungen:** Disziplin-Maschine (30 Tage Check-in-Serie) › Challenge-Champion › Recruiter
  - **Basis:** Grinder – bekommt jeder, sobald er die Regeln akzeptiert hat
- **Kategorien:** 📊 SERVER-STATS, 📜 START, 💬 COMMUNITY, 💪 GYM, 📰 NEWS, 🪙 KRYPTO, 🐸 MEMECOINS, 📊 TRADING, 📦 DROPSHIPPING, 🔗 AFFILIATE MARKETING, 🛍️ TIKTOK SHOP, 📱 SMMA, 🤖 KI, 💰 BUSINESS & MONEY, Schach (mit Sprachkanal für „Chess in the Park“), 🎙️ VOICE, 🔒 ADMIN, 🎫 TICKETS
- Kategorien und Kanäle werden in der Reihenfolge aus `config.py` sortiert
- **Erst Regeln, dann loslegen:** Neue haben zuerst keine Rolle und sehen nur `#regeln-und-zustimmung`. Hinweis per DM und kurze Erwähnung im Regel-Kanal (löscht sich nach 10 Min.). Klick auf **„✅ Regeln akzeptieren“** → sofort `Grinder`, alle Kanäle frei, Willkommensnachricht + „Erste Schritte“.
  Fremde Kategorien (z. B. Discords Standard-„Textkanäle“) werden für Neue ebenfalls gesperrt, bis sie bestätigt haben.
  Ohne Bestätigung: `VERIFICATION_ENABLED = False` in `config.py` → Grinder sofort beim Beitritt.
- **Rechte (gestaffelt):** Alle Mitglieds-Rollen haben die vollen normalen Rechte (`MEMBER_PERMISSIONS`: sehen, schreiben, Threads, Dateien, Reaktionen, Voice, Slash-Commands, Einladen). Extras: ab Saftler private Threads, ab Skalierer Events planen, ab König Krypto Voice-Vorrang. Türsteher: Nachrichten löschen, Timeout, Kick. Consigliere: zusätzlich Bann, Kanäle/Rollen/Server verwalten, @everyone. Admin: zusätzlich Webhooks & Emojis. `@everyone`: nur lesen + reagieren (Grundrechte kommen über die Rollen). Niemand außer dem Bot hat „Administrator“.
- **Idempotent:** erneutes Ausführen legt nichts doppelt an. `/setup` (Admins) jederzeit.
- Server-Icon aus `assets/server-icon.png` (wird nur neu hochgeladen, wenn sich die Datei ändert)

### Features & Befehle

| Feature | Befehle | Was passiert |
|---|---|---|
| **XP & Level** | `/rank`, `/leaderboard`, `/xp-geben` (Admin) | XP für Nachrichten (1×/Min.), Voice-Zeit und Aktionen. Start als Grinder, Rang-Rollen automatisch: Lvl 5 Gooner → 10 Niche → 15 Hustler → 20 Saftler → 30 Skalierer → 40 König Krypto → 50 Mogul → 75 Mancave-Legende. Level-Ups in `#level-ups` |
| **Daily Check-in** | `/checkin`, `/streak`, `/streak-leaderboard` | Täglich Körper / Business / Wissen eintragen, Serien mit Bonus-XP bei 7/30/100 Tagen |
| **Gym-Log** | `/workout`, `/gym-stats`, `/gym-leaderboard` | Trainings eintragen, Wochenstatistik, montags Wochen-Rückblick in `#gym-log` |
| **Kurse** | `/kurs BTC`, `/kurs AAPL`, `/kurs Apple`, `/marktbericht` (Admin) | Live-Kurse (CoinGecko / Yahoo Finance, ohne API-Key). Täglich 8 Uhr Report in `#krypto` und Mo–Fr in `#aktien` |
| **News** | `/news-jetzt` (Admin) | Täglich 7:30 und 18:00 Uhr Schlagzeilen-Briefing in `#politik-news` (Tagesschau), `#börsen-news` (Tagesschau Wirtschaft, n-tv, finanzen.net, MarketWatch) und `#krypto-news` (BTC-Echo, Cointelegraph) – per RSS, ohne API-Key, keine Doppelungen |
| **Schach** | `/schach [@gegner]`, `/zug`, `/schach-brett`, `/remis`, `/aufgeben`, `/schach-rangliste`, `/schach-stats` | Partien direkt im Chat (in `#schach-partien`): Brett als Bild, Züge in deutscher/englischer Notation (`/zug Sf3`, `/zug e4`, `/zug O-O`), alle Regeln inkl. Matt/Patt/Remis. Elo-Rangliste, XP für Sieg/Remis/Teilnahme, PGN-Datei am Ende. Wer 48 h nicht zieht, verliert |
| **Willkommens-Karte** | `/willkommen-vorschau` (Admin) | Bild mit Avatar, Name und „Du bist Mitglied Nr. X“ in `#willkommen` |
| **Hall of Fame** | – | Wins in `#erfolge-feiern` mit 5× 🔥 landen in `#hall-of-fame` (+100 XP) |
| **Ideen-Voting** | `/idee`, `/ideen-top` | Idee mit 👍/👎 und Diskussions-Thread in `#business-ideen` |
| **Tageszitat** | `/zitat` | Täglich 7 Uhr Zitat + Impuls des Tages in `#self-improvement` |
| **Challenges** | `/challenge-erstellen` (Admin), `/challenge-checkin`, `/challenge-status`, `/challenge-beenden` (Admin) | Mitmachen per Button in `#challenges`; wer jeden Tag abhakt, wird Challenge-Champion |
| **Auto-Mod** | `/warn`, `/warnings`, `/warn-entfernen`, `/timeout`, `/untimeout`, `/clear` | Spam → Timeout, fremde Invites / Massen-Pings / verbotene Wörter löschen, Links erst ab Level 3. Ab 3 Verwarnungen Auto-Timeout |
| **Tickets** | Button in `#ticket-erstellen`, `/ticket` | Privater Kanal mit dem Team, beim Schließen Protokoll in `#bot-logs` |
| **Server-Statistik** | `/serverinfo` | „👥 Mitglieder: N“ ganz oben, alle 10 Min. aktualisiert |
| **Einladungs-Tracking** | `/invites`, `/invite-leaderboard` | Wer wen eingeladen hat; automatisch aktualisierte Rangliste in `#invite-ranking`; ab 5 aktiven Einladungen Rolle „Recruiter“ |
| **KI-Coach** | `/coach` | Claude beantwortet Fragen zu Business, Finanzen, Training, Mindset – kennt auf Wunsch deine Check-ins & Workouts. Braucht `ANTHROPIC_API_KEY` |
| **Web-Dashboard** | – | `http://<server>:8080` – Leaderboards, Streaks, Gym, Invites, Ideen, Aktivitäts-Diagramm |

## Anleitung

### 1. Bot-Application im Developer Portal erstellen

1. Auf <https://discord.com/developers/applications> gehen → **New Application** → Name z. B. „Mancave Bot“.
2. Links auf **Bot** → **Reset Token** → Token kopieren. *Den Token niemals teilen!*
3. Optional: **Public Bot** ausschalten, damit nur du ihn einladen kannst.

### 2. Intents aktivieren

Ebenfalls unter **Bot** → *Privileged Gateway Intents*:

- ✅ **Server Members Intent**
- ✅ **Message Content Intent**

→ **Save Changes**.

### 3. Bot in den Server einladen

Links auf **OAuth2** → **OAuth2 URL Generator**:

- Scopes: `bot` und `applications.commands`
- Bot Permissions: `Administrator`

Oder direkt diesen Link nutzen (`DEINE_CLIENT_ID` durch die *Application ID* von der Seite **General Information** ersetzen):

```
https://discord.com/oauth2/authorize?client_id=DEINE_CLIENT_ID&scope=bot+applications.commands&permissions=8
```

> **Wichtig:** Der Bot braucht wirklich **Administrator** (oder mindestens *Server verwalten*, *Rollen verwalten*, *Kanäle verwalten*, *Mitglieder moderieren*, *Nachrichten verwalten*). Ohne *Server verwalten* funktionieren Server-Icon und Einladungs-Tracking nicht, ohne *Mitglieder moderieren* keine Timeouts.

> Warum Administrator? Der Bot muss Kanäle anlegen, Rechte setzen (auch in versteckten Kanälen), Rollen sortieren und den Servernamen ändern. Nach dem Setup kannst du ihm die Rechte wieder reduzieren – für die Verifizierung braucht er dann nur noch **Rollen verwalten**, **Kanäle ansehen**, **Nachrichten senden**, **Links einbetten**, **Reaktionen hinzufügen** und **Nachrichtenverlauf lesen**.

**Wichtig danach:** In Discord unter *Servereinstellungen › Rollen* die Rolle des Bots **ganz nach oben** ziehen. Ein Bot kann nur Rollen vergeben/sortieren, die unter seiner eigenen Rolle stehen.

### 4. Skript ausführen

Voraussetzung: Python 3.10+.

```bash
# einmalig: Abhängigkeiten installieren
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# .env anlegen
cp .env.example .env             # Windows: copy .env.example .env
```

In `.env` eintragen:

- `DISCORD_TOKEN` – der Token aus Schritt 1
- `GUILD_ID` – die Server-ID: In Discord *Einstellungen › Erweitert › Entwicklermodus* an, dann Rechtsklick auf den Server → **Server-ID kopieren**
- optional `ANTHROPIC_API_KEY` – für den KI-Coach (<https://console.anthropic.com>)
- optional `DASHBOARD_PASSWORD` (+ `DASHBOARD_PORT`) – ohne Passwort ist das Dashboard nur auf dem Rechner selbst erreichbar (`http://127.0.0.1:8080`), mit Passwort von überall (Login-Fenster im Browser, Benutzername egal)

Starten:

```bash
python bot.py
```

Beim ersten Start baut der Bot den kompletten Server auf (dauert ~30 Sekunden). In der Konsole und in `#bot-logs` siehst du, was angelegt wurde.

> 📘 **Kostenlos 24/7 hosten:** Schritt-für-Schritt-Anleitung für Oracle Cloud in [`docs/ORACLE-HOSTING.md`](docs/ORACLE-HOSTING.md) – mit fertigem Installations-Skript (`deploy/install.sh`).

> **Der Bot muss danach weiterlaufen**, damit neue Mitglieder beim Beitritt ihre Rolle bekommen und XP, News & Co. laufen. Für den Dauerbetrieb eignet sich ein kleiner VPS, ein Raspberry Pi oder ein Bot-Hoster. Wenn du nur das Setup willst, kannst du ihn danach auch stoppen – dann bekommen Neue aber keine Rolle.

### Anpassen

- **Regeln:** `RULES_DESCRIPTION` in `config.py` ändern → Bot neu starten oder `/setup` → die bestehende Regel-Nachricht wird bearbeitet (nicht neu gepostet).
- **Neuer Kanal:** Eintrag in der passenden Kategorie in `CATEGORIES` hinzufügen → `/setup`.
- **Neue Rolle:** Eintrag in `ROLES` an der gewünschten Stelle der Hierarchie einfügen → `/setup`.
- **Regelkanal nach Verifizierung ausblenden:** `RULES_VISIBLE_AFTER_VERIFY = False`.
- **XP-Werte, Level-Grenzen der Ränge, Uhrzeiten, Auto-Mod-Regeln, Coach-Modell:** alles im Abschnitt *FEATURES* in `config.py`.
- **Feature abschalten:** Zeile in `EXTENSIONS` in `config.py` auskommentieren → Bot neu starten.

⚠️ Das Skript erkennt Rollen und Kanäle **am Namen**. Wenn du einen Namen in `config.py` änderst, wird etwas Neues angelegt – den alten Eintrag dann in Discord manuell löschen. Das Skript selbst löscht nie etwas.
