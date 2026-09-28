# Mancave-Bot kostenlos 24/7 auf Oracle Cloud hosten

Dauer: ca. 30–45 Minuten. Kosten: 0 € (Oracle „Always Free“).
Du brauchst: E-Mail, Handynummer, Kreditkarte (nur zur Verifizierung – wird nicht belastet) und einen PC.

> Oracle ändert seine Oberfläche ab und zu. Wenn ein Button anders heißt, such nach dem ähnlichsten Begriff.

---

## Schritt 1 – Oracle-Konto anlegen

1. Geh auf **<https://www.oracle.com/cloud/free/>** → **Start for free**.
2. Land: **Germany**, Name, E-Mail → E-Mail bestätigen.
3. **Home Region: `Germany Central (Frankfurt)`** wählen.
   ⚠️ Die Home Region kann man **nie wieder ändern**. Gratis-Server gibt es nur dort.
4. Adresse, Handynummer und Kreditkarte eingeben. Oracle bucht evtl. einen kleinen Betrag zur Prüfung ab und erstattet ihn wieder.
5. Warten, bis die Mail „Your account is ready“ kommt (manchmal ein paar Minuten, selten Stunden).

---

## Schritt 2 – Server (VM) erstellen

1. In der Oracle-Konsole einloggen → oben links **☰ Menü → Compute → Instances** → **Create instance**.
2. **Name:** `mancave-bot`
3. **Image and shape → Edit:**
   - **Image:** `Canonical Ubuntu` (neueste Version, z. B. 24.04) → *Select image*
   - **Shape:** *Change shape* → **Ampere** → **VM.Standard.A1.Flex**
     → **1 OCPU** und **6 GB RAM** reichen völlig → *Select shape*
   - Steht dort **„Always Free-eligible“**? Dann passt es.
4. **Networking:** Standard lassen (*Create new virtual cloud network*, *Assign a public IPv4 address* = **Ja**).
5. **Add SSH keys:** **Generate a key pair for me** → **Save private key** klicken.
   ⚠️ Diese Datei (`ssh-key-….key`) gut aufheben – ohne sie kommst du nicht mehr auf den Server!
6. **Create** klicken. Nach 1–2 Minuten steht der Status auf **Running**.
7. Auf der Instanz-Seite die **Public IP address** notieren (z. B. `130.61.x.x`).

**Fehler „Out of capacity“?** Das kommt bei Ampere häufig vor. Lösungen:
- Unter *Placement* eine andere **Availability Domain** (AD-1/2/3) wählen und erneut versuchen, oder
- später nochmal probieren (nachts klappt es oft), oder
- stattdessen Shape **VM.Standard.E2.1.Micro** (AMD, 1 GB RAM, auch Always Free) nehmen – reicht auch für den Bot.

---

## Schritt 3 – Mit dem Server verbinden

**Windows** (PowerShell öffnen):

```powershell
# Key an einen festen Ort legen und Rechte einschränken (sonst verweigert SSH den Key)
mkdir $HOME\.ssh -Force
move $HOME\Downloads\ssh-key-*.key $HOME\.ssh\oracle.key
icacls $HOME\.ssh\oracle.key /inheritance:r /grant:r "$($env:USERNAME):(R)"

ssh -i $HOME\.ssh\oracle.key ubuntu@DEINE_IP
```

**Mac / Linux** (Terminal):

```bash
mkdir -p ~/.ssh && mv ~/Downloads/ssh-key-*.key ~/.ssh/oracle.key
chmod 600 ~/.ssh/oracle.key
ssh -i ~/.ssh/oracle.key ubuntu@DEINE_IP
```

Beim ersten Mal fragt SSH „Are you sure you want to continue connecting?“ → `yes`.
Du bist drin, wenn die Zeile mit `ubuntu@mancave-bot:~$` beginnt.

---

## Schritt 4 – Bot installieren

Alle folgenden Befehle **auf dem Server** eingeben.

### 4a) Code holen

Ist das GitHub-Repo **öffentlich**:

```bash
git clone -b claude/festive-feynman-chjtyf https://github.com/Marvinjulius1/Mancave-Discord.git
```

Ist das Repo **privat**, brauchst du einen GitHub-Token:
1. GitHub → *Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token*
2. *Repository access:* nur `Mancave-Discord` · *Permissions → Contents:* **Read-only** → *Generate*
3. Dann:

```bash
git clone -b claude/festive-feynman-chjtyf https://github.com/Marvinjulius1/Mancave-Discord.git
# Username: dein GitHub-Name   ·   Password: den Token einfügen (wird nicht angezeigt)
```

> Tipp: Wenn du die Änderungen vorher in den `main`-Branch übernimmst, kannst du `-b claude/festive-feynman-chjtyf` weglassen.

### 4b) Installieren

```bash
cd Mancave-Discord
bash deploy/install.sh
```

Das dauert 1–3 Minuten. Das Skript installiert alles, richtet den Bot als Dienst ein
(startet automatisch beim Hochfahren und nach Abstürzen) und macht jede Nacht ein Datenbank-Backup.

### 4c) Zugangsdaten eintragen

```bash
nano .env
```

Eintragen:

```
DISCORD_TOKEN=dein-neuer-token
GUILD_ID=deine-server-id
ANTHROPIC_API_KEY=            # optional, für /coach
DASHBOARD_PASSWORD=           # leer lassen (siehe Schritt 6)
```

⚠️ **Setz den Bot-Token vorher im Discord Developer Portal zurück** (Bot → *Reset Token*), weil der alte im Chat stand – und nimm den neuen.

Speichern: **Strg + O**, **Enter**, **Strg + X**.

### 4d) Starten

```bash
sudo systemctl restart mancave-bot
journalctl -u mancave-bot -f
```

Du solltest `Eingeloggt als …` und `=== Setup fertig ===` sehen. Mit **Strg + C** verlässt du das Log (der Bot läuft weiter).
Jetzt kannst du das SSH-Fenster schließen – **der Bot läuft 24/7**. 🎉

> Wichtig: Läuft der Bot jetzt auf Oracle, darf er **nirgendwo anders gleichzeitig** laufen (sonst antwortet er doppelt).

---

## Schritt 5 – Die wichtigsten Befehle

| Was | Befehl |
|---|---|
| Läuft der Bot? | `sudo systemctl status mancave-bot` |
| Live-Log ansehen | `journalctl -u mancave-bot -f` |
| Neu starten (z. B. nach `.env`-Änderung) | `sudo systemctl restart mancave-bot` |
| Stoppen | `sudo systemctl stop mancave-bot` |
| Neue Version von GitHub holen | `cd ~/Mancave-Discord && bash deploy/update.sh` |
| Backup von Hand | `bash ~/Mancave-Discord/deploy/backup.sh` |

Backups liegen in `~/Mancave-Discord/backups/` (14 Tage).

---

## Schritt 6 – Dashboard ansehen (sicher, ohne Ports zu öffnen)

Das Dashboard läuft auf dem Server nur intern. Du holst es dir per SSH-Tunnel auf deinen PC:

```bash
ssh -i ~/.ssh/oracle.key -L 8080:localhost:8080 ubuntu@DEINE_IP
```

(Windows: `$HOME\.ssh\oracle.key` statt `~/.ssh/oracle.key`)

Solange dieses Fenster offen ist, öffnest du im Browser **<http://localhost:8080>**.
So ist das Dashboard nie öffentlich im Internet – kein Passwort nötig.

---

## Wichtig zu wissen

- **Inaktive Gratis-Server:** Oracle kann Always-Free-Server zurückfordern, die über 7 Tage kaum
  CPU, Netzwerk und Arbeitsspeicher nutzen. Ein Discord-Bot braucht sehr wenig – das Risiko besteht also.
  Sicherste Lösung: Konto auf **„Pay As You Go“ upgraden** (*Billing → Upgrade and Manage Payment*).
  Solange du nur Always-Free-Ressourcen nutzt, bleibt es **kostenlos**, und die Rückforderung entfällt.
  Richte dann zur Sicherheit unter *Billing → Budgets* ein Budget von 1 € mit E-Mail-Alarm ein.
- **Nur Always-Free-Sachen anlegen.** Alles ohne „Always Free-eligible“-Label kann Geld kosten.
- **Updates des Servers** ab und zu: `sudo apt update && sudo apt upgrade -y` (danach ggf. `sudo reboot` – der Bot startet von selbst wieder).
- **Datenbank:** Auf dem neuen Server startet die Datenbank leer (XP, Streaks usw. beginnen bei 0).
  Rollen, Kanäle und Nachrichten auf Discord bleiben natürlich erhalten.

---

## Probleme?

| Problem | Lösung |
|---|---|
| `Permission denied (publickey)` | Falscher Key-Pfad oder Benutzer. Benutzer ist `ubuntu`, Key ist die heruntergeladene `.key`-Datei. Windows: `icacls`-Befehl aus Schritt 3 ausführen. |
| `UNPROTECTED PRIVATE KEY FILE` | Mac/Linux: `chmod 600 ~/.ssh/oracle.key` · Windows: `icacls`-Befehl aus Schritt 3 |
| Log zeigt `Improper token` | Token in `.env` falsch → neu kopieren, `sudo systemctl restart mancave-bot` |
| Log zeigt `Server … nicht gefunden` | `GUILD_ID` falsch oder Bot nicht eingeladen |
| Bot antwortet doppelt | Er läuft noch woanders → dort stoppen |
