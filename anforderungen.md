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
3. Danach `https://<domain>`: Dashboard, Apps, Netzwerk, DNS, Speicher, Benutzer, Einstellungen.

## Aufbau

| Baustein | Wahl | Warum |
|---|---|---|
| Oberfläche/Logik | **Python 3 (nur Standardbibliothek)** | Keine Fremd-Pakete → keine Lieferketten-Risiken, Installation kann nicht an Paketquellen scheitern. |
| Datenhaltung | **SQLite** | Eingebaut, robust, keine zusätzliche Datenbank nötig. |
| App-Laufzeit | **Docker** | Standard, saubere Isolation je App, Ressourcenlimits (CPU/RAM). |
| Proxy/TLS | **Caddy** | Automatisches HTTPS je Domain, minimale Konfiguration. |
| DNS | **Cloudflare-API** | Einträge direkt aus der Oberfläche. |
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

## Bereiche der Oberfläche
- **Dashboard** — Auslastung des Geräts und Verbrauch je App (CPU/RAM/Netz), Status, Ports.
- **Apps** — Katalog + installierte Apps; je App Übersicht, Einstellungen (Basis/Spezifisch/
  Erweitert), Protokoll, Start/Stopp/Neustart/Entfernen.
- **Netzwerk** — Schnittstellen, **Subnetze anlegen/löschen**, alle belegten Ports (intern/extern).
- **DNS** — Einträge der Verwaltungs-Domain anlegen/ersetzen/löschen.
- **Speicher** — Dateisysteme, Laufwerke, Datenpfade und Belegung je App.
- **Benutzer** — Konten anlegen/löschen, eigenes Passwort ändern.
- **Einstellungen** — Domain, Server-IP, Cloudflare-Token, Katalog neu einlesen, Status.

## Bewusste Grenzen
- Die Oberfläche ist auf Desktop ausgelegt (Tabellen/Übersicht), funktioniert aber responsiv.
- „Ablageort: auf dem Gerät“ ist vorbereitet; ausgeführt werden Apps derzeit als Docker-Container.
- Konfiguration ohne Secrets im Repo: alles Sensible entsteht erst beim Setup auf dem Server.
