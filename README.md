# Mancave – Discord-Server-Bot

Baut den kompletten **Mancave**-Server automatisch auf und übernimmt die Verifizierung.

| Datei | Inhalt |
|---|---|
| `bot.py` | Setup-Logik, Verifizierung, `/setup`-Befehl |
| `config.py` | **Alles zum Anpassen:** Rollen, Farben, Kategorien, Kanäle, Regel-Text, Willkommensnachricht |
| `.env` | Bot-Token + Server-ID (nicht committen!) |

## Was der Bot macht

- **Rollen** (von oben nach unten): Admin / Mod › König Krypto › Skalierer › Saftler › Niche › Gooner › Mitglied › Unverified
- **Kategorien & Kanäle:** 📜 START, 💬 COMMUNITY, 💰 BUSINESS & MONEY, 🎙️ VOICE, 🔒 ADMIN
- **Kein Bestätigen nötig (Standard):** Wer joint, sieht sofort alle Kanäle (außer 🔒 ADMIN) und kann schreiben. Das funktioniert auch, wenn der Bot gerade offline ist. Ist er online, gibt er neuen Leuten die Rolle `Mitglied` und begrüßt sie in `#willkommen`.
- **Optional: Verifizierung per ✅** – in `config.py` `VERIFICATION_ENABLED = True` setzen. Dann bekommen neue Leute `Unverified`, sehen nur `#regeln-und-zustimmung` und werden erst nach ✅ freigeschaltet (Bot muss dafür dauerhaft laufen).
- **Idempotent:** Beim erneuten Ausführen wird nichts doppelt angelegt, nur Abweichungen (Farben, Rechte, Themen, Regeltext) werden angepasst.
- `/setup` (nur Admins): Setup jederzeit erneut ausführen, z. B. nachdem du `config.py` geändert hast.

Die Rang-Rollen (König Krypto, Skalierer, Saftler, Niche, Gooner) vergibst du manuell
(Rechtsklick auf Mitglied › Rollen). Admin / Mod bekommt Moderationsrechte, aber bewusst **nicht** „Administrator“.

---

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

Starten:

```bash
python bot.py
```

Beim ersten Start baut der Bot den kompletten Server auf (dauert ~30 Sekunden). In der Konsole und in `#bot-logs` siehst du, was angelegt wurde.

> **Der Bot muss danach weiterlaufen**, damit Verifizierung (✅) und die `Unverified`-Rolle beim Join funktionieren. Für den Dauerbetrieb eignet sich ein kleiner VPS, ein Raspberry Pi oder ein Bot-Hoster. Wenn du nur das Setup willst, kannst du ihn danach auch stoppen – dann klappt die Verifizierung aber nicht.

### Anpassen

- **Regeln:** `RULES_DESCRIPTION` in `config.py` ändern → Bot neu starten oder `/setup` → die bestehende Regel-Nachricht wird bearbeitet (nicht neu gepostet).
- **Neuer Kanal:** Eintrag in der passenden Kategorie in `CATEGORIES` hinzufügen → `/setup`.
- **Neue Rolle:** Eintrag in `ROLES` an der gewünschten Stelle der Hierarchie einfügen → `/setup`.
- **Regelkanal nach Verifizierung ausblenden:** `RULES_VISIBLE_AFTER_VERIFY = False`.

⚠️ Das Skript erkennt Rollen und Kanäle **am Namen**. Wenn du einen Namen in `config.py` änderst, wird etwas Neues angelegt – den alten Eintrag dann in Discord manuell löschen. Das Skript selbst löscht nie etwas.
