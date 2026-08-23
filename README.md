# weblab — Server-Verwaltung mit App-Katalog

Aus einem frischen **Ubuntu 24.04 LTS** wird mit **einem Kommando** ein gehärteter Server mit
Weboberfläche: Apps (Minecraft, Webseiten, Datenbanken …) aus einem **Katalog** installieren,
Domains und Ports vergeben, Ressourcen, Netzwerk, Speicher und Benutzer verwalten.

## Installation

Ein Befehl — für alles:

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/florianthepro/weblab/main/install.sh)"
```

Er sieht nach, was auf dem Server liegt:

| Vorgefunden | Was passiert |
|---|---|
| **Nichts** | weblab wird installiert |
| **Fremde Software** (Cockpit, Apache/Nginx, anderes Panel) | fragt, ob sie vorher entfernt wird |
| **weblab** | fragt: **Aktualisieren** oder **Neu installieren** |

**Aktualisieren** vergleicht mit GitHub und ersetzt nur die Programmdateien von weblab —
Apps, Webseiten und Datenbanken unter `/var/lib/weblab` bleiben unangetastet. Weicht eine
Kerndatei ab, wird sie ebenfalls wieder hergestellt.
**Neu installieren** setzt den Server zurück; Apps und Daten gehen dabei verloren.

Ohne Rückfragen: `--update`, `--reinstall` oder `--install`, jeweils mit `--yes`.
Dieselbe Prüfung läuft regelmäßig von selbst (systemd-Timer).

Nach der Installation **`http://<server-ip>`** öffnen: Der Assistent fragt **Admin + Passwort +
Verwaltungs-Domain** (deren `@`-Record auf diese IP zeigt). Anschließend läuft die Oberfläche
unter **`https://deine-domain`**; das DNS-Konto verbindest du danach unter *Netzwerk*.

## Oberfläche

| Bereich | Inhalt |
|---|---|
| **Dashboard** | Auslastung des Servers (CPU/RAM/Platte) + Verbrauch je App |
| **Apps** | Katalog (installieren) und installierte Apps (verwalten) |
| **Netzwerk** | Domain & Server-IP, DNS-Konto + Einträge, VPN, offene Ports |
| **Speicher** | Laufwerke (physisch) mit Belegung je Disk und welche App wie viel belegt |
| **Benutzer** | Konten für die Oberfläche |

Tiefere Angaben stecken in aufklappbaren Bereichen; Fehler erscheinen als Banner, das auf
jeder Seite bleibt, bis man es schließt.

## Updates
weblab vergleicht sich regelmäßig mit GitHub und aktualisiert sich selbst — Daten bleiben.
Sichtbar ist davon nur, was zählt: neue Apps im Katalog sind mit **neu** markiert, und bei
installierten Apps erscheint **Update**, wenn es eine neuere Version gibt.

## VPN je App
Unter **Netzwerk → VPN**:
- **Tailscale (privat):** Konto verbinden (Auth-Key); Apps mit Erreichbarkeit
  **Tailscale (privat)** sind dann nur in deinem Tailscale-Netz erreichbar — ideal zum
  Verwalten, ohne etwas öffentlich zu machen.
- **Ausgehende Tunnel (Mullvad/Proton):** WireGuard-Zugang hinterlegen; je App unter
  **Einstellungen → Basis → Ausgang über VPN** wählbar. Der ausgehende Verkehr dieser App
  läuft dann durch den VPN (via gluetun).

## Apps

Jede App kommt aus einer **Connector-Datei** in [`connectors/keep/`](connectors/keep).
Im Katalog erscheint eine App einmal (z. B. „Minecraft (Java)“) mit **Versionsauswahl**.

Beim Installieren werden nur die **Pflichtfelder** abgefragt (z. B. RAM bei Minecraft) plus die
**Basis-Angaben**, die für alle Apps gleich sind: Name, Domain, intern/extern/spezifisch, Port,
Ablageort (Docker/Gerät), Datenlaufwerk, CPU und RAM.

Webseiten (Apache/Nginx) und der Mailserver haben eine eigene **Verwaltungs-Adresse**
(standardmäßig `apache.<domain>` / `nginx.<domain>` / `mail.<domain>`). Dort öffnet sich das
**Dashboard mit Dateimanager** dieser App — durchsuchen, Ordner anlegen, hochladen, Textdateien
bearbeiten, löschen. Die Seite selbst läuft unter ihrer eigenen Domain (`domain.com` oder
`<name>.domain.com`). So lassen sich Apache/Nginx **mehrfach** installieren — je Webseite eine
eigene Domain, eine eigene Verwaltungs-Adresse und ein eigener Dateibereich.

Unter **App → Einstellungen** gibt es drei Bereiche:
- **Basis** — Name, Domain, Port, Sichtbarkeit, Laufwerk, CPU/RAM
- **Spezifisch** — was der Connector definiert (bei Minecraft z. B. MOTD, Spielmodus)
- **Erweitert** — z. B. **Plugins**: Quelle wählen, suchen, hinzufügen, Liste mit Löschen

### Enthaltene Apps
Webseite (Apache), Webseite (Nginx), Nextcloud, Jellyfin, Mailserver, Minecraft (Java),
PostgreSQL, MariaDB, Redis, Adminer, Gitea, Vaultwarden, Uptime Kuma, FreshRSS,
code-server, IT-Tools.

## DNS-Konto verbinden
Unter **Netzwerk → DNS-Konto verbinden** (Overlay). Am einfachsten mit einem **API-Token**
(Cloudflare → Profil → API-Tokens → Vorlage „Zone-DNS bearbeiten"). Unter *Andere Wege* gibt
es zusätzlich die Konto-Anmeldung (E-Mail + Global API Key, wird nicht gespeichert) und
die Anmeldung per OAuth.

Danach wählst du bei jeder App die **Domain aus einer Liste** und optional eine Subdomain;
die DNS-Einträge legt weblab selbst an (Webseiten: A-Record; Mailserver: A, MX, SPF, DMARC).

Details zum Connector-Format: [`connectors/README.md`](connectors/README.md).

Vorgaben und Komponentenwahl: [`anforderungen.md`](anforderungen.md).
