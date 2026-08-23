# Anforderungen & Aufbau — weblab

## Ziel
Eine fertige Linux-Server-Software: **ein Kommando installiert**, danach verwaltet man den
Server komplett im Browser. Server-Apps kommen aus einem **Katalog**; man füllt Pflichtfelder
aus (z. B. RAM bei einem Minecraft-Server) und die App läuft — sauber in Docker isoliert.

## Prioritäten
1. **Sicherheit**  2. Features  3. Bedienbarkeit. (Frei/OSS.)

## Ablauf
1. `sudo bash software/run.sh` auf frischem Ubuntu 24.04 LTS.
2. `http://<server-ip>` öffnen → **Setup: Admin + Passwort + Verwaltungs-Domain**
   (deren `@`-Record auf die IP zeigt), optional Cloudflare-Token → **Ladebalken**.
3. Danach `https://<domain>`: Dashboard, Apps, Netzwerk, Speicher, Benutzer, Einstellungen.

## Aufbau

| Baustein | Wahl | Warum |
|---|---|---|
| Oberfläche/Logik | **Python 3 (nur Standardbibliothek)** | Keine Fremd-Pakete → keine Lieferketten-Risiken, Installation kann nicht an Paketquellen scheitern. |
| Datenhaltung | **SQLite** | Eingebaut, robust, keine zusätzliche Datenbank nötig. |
| App-Laufzeit | **Docker** | Standard, saubere Isolation je App, Ressourcenlimits (CPU/RAM). |
| Proxy/TLS | **Caddy** | Automatisches HTTPS je Domain, minimale Konfiguration. |
| DNS | **Cloudflare-API** | Konto unter *Netzwerk* verknüpfen; Einträge je App automatisch. |
| Dateien | **Dateimanager je App** | Jede Webseite hat ihr eigenes Dateisystem im Browser. |
| Katalog | **Connector-Dateien (JSON)** | Der „Index“ zwischen Katalog, Formularen und Container. |

## Sicherheit
- Härtung: ufw (nur 22/80/443 + je App freigegebene Ports), fail2ban, unattended-upgrades, sysctl.
- Oberfläche nur über Caddy/HTTPS; der Dienst lauscht intern auf `127.0.0.1:8099`.
- Anmeldung mit eigenem Konto (scrypt-Hash), signierte Sitzungs-Cookies (HttpOnly, SameSite=Strict,
  Secure hinter HTTPS), **CSRF-Schutz** bei allen schreibenden Aktionen.
- Erreichbarkeit je App wählbar: **extern**, **intern** (nur `127.0.0.1`) oder **spezifisch**
  (nur erlaubte IPs/CIDR — als ufw-Regel).
- Container mit CPU-/RAM-Limit, eigenem Datenpfad und optional eigenem Subnetz.

## Connectors — der Index
Je App-Version eine Datei in `connectors/keep/`. Sie liefert Katalogtext, Docker-Image, Ports,
Datenpfad und die **drei Feldgruppen**:

| Gruppe | Wann | Beispiel Minecraft |
|---|---|---|
| **Pflicht** (`required`) | beim Installieren | RAM (GB), max. Spieler |
| **Basis** (in der Software) | für alle Apps gleich | Name, Domain, intern/extern, Port, Ablageort, Laufwerk, CPU, RAM |
| **Spezifisch** (`specific`) | beim Bearbeiten | MOTD, Spielmodus, Schwierigkeit, PvP … |

Jedes Feld hat ein **Target** — es sagt, wohin der Wert geschrieben wird:
`env` (Umgebungsvariable) oder `file_line` (die Zeile in einer Datei, die mit einem Präfix
beginnt, z. B. `motd=` in `/data/server.properties`).

**Gruppierung:** Versionen derselben Software teilen sich `group` und erscheinen im Katalog als
**eine** App mit Versionsauswahl — wie im Ubuntu-Store.

**Erweitert:** `advanced.plugins` schaltet die Plugin-Verwaltung frei (Quelle wählen → suchen →
hinzufügen; Gesamtliste mit Löschen). Für Minecraft: Modrinth und SpigotMC.

## Mehrere Webseiten
Apache und Nginx sind **beliebig oft** installierbar. Jede Installation ist eigenständig:
eigener Container, eigener Port, **eigene Domain** und ein **eigenes Dateisystem**, das unter
*App → Dateien* im Browser verwaltet wird (hochladen, bearbeiten, Ordner, löschen).
Der Mailserver ist **einmalig** — seine Ports (25/143/465/587/993) stehen fest.

## Bereiche der Oberfläche
- **Dashboard** — Auslastung des Geräts und Verbrauch je App (CPU/RAM/Netz), Status, Ports.
- **Apps** — Katalog + installierte Apps; je App Übersicht, **Dateien**, Einstellungen
  (Basis/Spezifisch/Erweitert), Protokoll, Start/Stopp/Neustart/Entfernen.
- **Netzwerk** — DNS-Konto verknüpfen + Übersicht aller Einträge; offene Ports (standardmäßig
  extern, per „Erweitert“ auch intern, Schnittstellen und Subnetze).
- **Speicher** — Dateisysteme, Laufwerke, Datenpfade und Belegung je App.
- **Benutzer** — Konten anlegen/löschen, eigenes Passwort ändern.
- **Einstellungen** — Domain, Server-IP, Katalog, Status.

## Grenzen
- Auf Desktop ausgelegt, aber responsiv.
- „Ablageort: auf dem Gerät“ ist vorbereitet; ausgeführt werden Apps als Docker-Container.
- Keine Secrets im Repo — Zugangsdaten entstehen erst beim Setup auf dem Server.
