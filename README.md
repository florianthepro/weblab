# weblab — Server-Verwaltung mit App-Katalog

Aus einem frischen **Ubuntu 24.04 LTS** wird mit **einem Kommando** ein gehärteter Server mit
Weboberfläche: Apps (Minecraft, Webseiten, Datenbanken …) aus einem **Katalog** installieren,
Domains und Ports vergeben, Ressourcen, Netzwerk, Speicher und Benutzer verwalten.

## Installation (als root)

```bash
git clone https://github.com/florianthepro/weblab && sudo bash weblab/software/run.sh
```

Danach **`http://<server-ip>`** öffnen: Der Assistent fragt **Admin + Passwort +
Verwaltungs-Domain** (deren `@`-Record auf diese IP zeigt), richtet optional per
Cloudflare-Token das DNS ein und zeigt einen Ladebalken. Anschließend läuft die Oberfläche
unter **`https://deine-domain`**.

### Von Grund auf neu (Server bereinigen)

Läuft auf dem Ubuntu schon anderes (Cockpit, Apache/Nginx, ein anderes Panel …) oder eine
frühere weblab-Installation, bringt dieses Kommando den Server zuerst in einen **sauberen
Zustand** — es entfernt konkurrierende Software, alle Docker-Container/-Volumes und alte
weblab-Daten — und installiert dann frisch:

```bash
rm -rf weblab && git clone https://github.com/florianthepro/weblab \
  && sudo bash weblab/software/fresh-install.sh
```

Es zeigt an, was gefunden wurde, und fragt einmal nach (`JA`). Für einen Lauf ohne Rückfrage
`sudo FORCE=1 bash weblab/software/fresh-install.sh`. **Achtung:** löscht vorhandene Daten.

## Oberfläche

| Bereich | Inhalt |
|---|---|
| **Dashboard** | Auslastung des Servers (CPU/RAM/Platte) + Verbrauch je App |
| **Apps** | Katalog (installieren) und installierte Apps (verwalten) |
| **Netzwerk** | DNS-Konto + Einträge, VPN (Tailscale + Mullvad/Proton), offene Ports |
| **Speicher** | Laufwerke (physisch) mit Belegung je Disk und welche App wie viel belegt |
| **Benutzer** | Konten für die Oberfläche |
| **Einstellungen** | Domain, Server-IP, Katalog, automatische Updates |

## Automatische Updates
weblab prüft regelmäßig das Repo und installiert neue Versionen selbst (systemd-Timer).
Unter **Einstellungen** siehst du die Version, kannst manuell „Jetzt prüfen & aktualisieren"
und die automatischen Updates ein-/ausschalten.

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
Minecraft (Java), Webseite (Apache + PHP), Webseite (Nginx), Mailserver, PostgreSQL.

## Cloudflare verknüpfen
Unter **Netzwerk → DNS** verknüpfst du dein Konto — **du musst keinen Token
selbst anlegen**. Zwei Wege:

1. **Mit Cloudflare anmelden** — du wirst zu Cloudflare geleitet und bestätigst dort den
   Zugriff (OAuth, Authorization Code + PKCE). Dafür legst du einmalig einen OAuth-Client in
   deinem Cloudflare-Konto an; die nötige Rückleitungs-Adresse zeigt weblab an.
2. **Konto-Anmeldung** (ohne Vorbereitung) — einmalige Eingabe von Konto-E-Mail und
   Konto-Schlüssel. weblab erzeugt daraus selbst einen Token, der **nur DNS** ändern darf und
   nach einem Jahr abläuft; der Schlüssel wird **nicht gespeichert**.

Danach legt weblab die DNS-Einträge jeder App automatisch an (Webseiten: A-Record;
Mailserver: A, MX, SPF, DMARC).

Details zum Connector-Format: [`connectors/README.md`](connectors/README.md).

Vorgaben und Komponentenwahl: [`anforderungen.md`](anforderungen.md).
