# Discord API Reference (Kontext für Claude Code)

Kurzreferenz der offiziellen Discord-API-Dokumentation (https://docs.discord.com/developers/reference), zusammengestellt als Projekt-Kontext für dieses Repo. Nützlich, falls der Bot über discord.py hinaus direkt gegen die REST-/Gateway-API sprechen soll (z. B. eigene HTTP-Requests, Webhooks, OAuth2-Flows).

> ⚠️ Kein Bot-Token oder Secret hier eintragen. Tokens gehören ausschließlich in die lokale `.env` (siehe `.env.example`) und werden nie committet.

## Base URLs
- REST API: `https://discord.com/api` (Version anhängen: `https://discord.com/api/v10`)
- CDN (Bilder/Assets): `https://cdn.discordapp.com/`

## API-Versionierung
- Aktuelle Default-Version: **v10** (v9 ebenfalls verfügbar, v8 und älter deprecated/discontinued)
- Version immer explizit in den Pfad schreiben: `/api/v10/...`

## Authentifizierung
Drei Möglichkeiten, jeweils per `Authorization`-Header:

| Methode | Header-Format | Einsatz |
|---|---|---|
| Bot Token | `Authorization: Bot <TOKEN>` | Server-seitiger Bot (unser Fall, aus Developer Portal → Bot → Reset Token) |
| OAuth2 Bearer Token | `Authorization: Bearer <TOKEN>` | Im Namen eines Users handeln (z. B. Login mit Discord) |
| Basic Auth | `Authorization: Basic base64(client_id:client_secret)` | Nur für OAuth2-Token-Endpoints |

## Rate Limiting
- Discord limitiert Requests pro Route/Bucket (RFC 6585). Wiederholtes Ignorieren von Rate Limits kann zum Entzug des API-Keys führen.
- Immer die Rate-Limit-Header der Response auswerten (`X-RateLimit-*`), statt fix zu pollen.

## User Agent & Content-Type
- Eigener User-Agent-Header erforderlich: `User-Agent: DiscordBot ($url, $versionNumber)` – fehlt er, kann Cloudflare den Request blocken.
- Gültiger `Content-Type` nötig: `application/json`, `application/x-www-form-urlencoded` oder `multipart/form-data`.

## Snowflakes (IDs)
- Discord-IDs sind 64-bit "Snowflakes" (Zeitstempel + Worker-ID + Process-ID + Increment), aus API immer als **String** (nicht Integer) zurückgegeben.
- Timestamp aus Snowflake extrahieren: `(snowflake >> 22) + 1420070400000` (Discord Epoch = 1. Januar 2015).
- Nützlich für Pagination (`before`/`after`/`limit` Query-Parameter) und um IDs für einen Zeitpunkt zu generieren: `(timestamp_ms - 1420070400000) << 22`.

## Gateway (WebSocket) API
- Für persistente, stateful Verbindungen (Echtzeit-Events wie Member-Join, Reaktionen etc.) – genau das, was `bot.py` über discord.py nutzt.
- Sichere WebSocket-Verbindung nach RFC 6455.

## Nachrichtenformatierung (Mentions, Timestamps)
| Typ | Syntax | Beispiel |
|---|---|---|
| User-Mention | `<@USER_ID>` | `<@80351110224678912>` |
| Channel-Mention | `<#CHANNEL_ID>` | `<#103735883630395392>` |
| Rollen-Mention | `<@&ROLE_ID>` | `<@&165511591545143296>` |
| Custom Emoji | `<:NAME:ID>` | `<:mmLol:216154654256398347>` |
| Unix-Timestamp | `<t:TIMESTAMP:STYLE>` | `<t:1618953630:R>` → „vor 4 Jahren" |

Timestamp-Styles: `t`/`T` (Zeit kurz/lang), `d`/`D` (Datum kurz/lang), `f`/`F` (Datum+Zeit), `R` (relativ, z. B. „vor 4 Jahren").

## Bild-/CDN-Formate
- Formate: JPEG, PNG, WebP, GIF, Lottie (`.json`)
- Größe per Query-Param steuerbar: `?size=<16 bis 4096, Zweierpotenz>`
- Wichtige CDN-Pfade: `icons/{guild_id}/{icon}.png`, `avatars/{user_id}/{avatar}.png`, `role-icons/{role_id}/{icon}.png`

## Datei-Uploads
- `multipart/form-data`, Feldname `files[n]` (z. B. `files[0]`)
- Standard-Limit 20 MiB pro Datei (abhängig von Boost-Tier/Nitro)
- Bilder in Embeds referenzierbar über `attachment://filename.png`

## Fehler-Format
Responses liefern strukturierte Fehler mit `code`, `message` und optional verschachteltem `errors`-Objekt, das das betroffene Feld benennt – z. B. `50035` = "Invalid Form Body".

## Relevanz für dieses Projekt (Mancave-Discord)
- `bot.py` nutzt aktuell die **discord.py-Library** (kapselt REST + Gateway bereits ab) – die rohe HTTP-API wird i. d. R. nicht direkt gebraucht.
- Diese Referenz ist relevant, sobald z. B. eigene Slash-Commands mit komplexeren Interactions, direkte REST-Calls (z. B. für ein Dashboard/Website-Backend), OAuth2-Login für eine externe Seite, oder Webhooks (z. B. Log-Einträge von außerhalb des Bots) dazukommen.
- Vollständige, laufend aktualisierte Doku: https://docs.discord.com/developers/reference

---
*Erstellt von Claude als Projekt-Kontext, Quelle: offizielle Discord Developer Docs (Stand 2026-09-28).*
