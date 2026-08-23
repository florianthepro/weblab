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

## Oberfläche

| Bereich | Inhalt |
|---|---|
| **Dashboard** | Auslastung des Servers (CPU/RAM/Platte) + Verbrauch je App |
| **Apps** | Katalog (installieren) und installierte Apps (verwalten) |
| **Netzwerk** | Schnittstellen, **Subnetze anlegen/verwalten**, alle belegten Ports |
| **DNS** | DNS-Einträge (Cloudflare-Konto verknüpfen → Einträge entstehen automatisch) |
| **Speicher** | Laufwerke, Belegung, Datenpfade der Apps |
| **Benutzer** | Konten für die Oberfläche |
| **Einstellungen** | Domain, Cloudflare-Token, Katalog |

## Apps

Jede App kommt aus einer **Connector-Datei** in [`connectors/keep/`](connectors/keep).
Im Katalog erscheint eine App einmal (z. B. „Minecraft (Java)“) mit **Versionsauswahl**.

Beim Installieren werden nur die **Pflichtfelder** abgefragt (z. B. RAM bei Minecraft) plus die
**Basis-Angaben**, die für alle Apps gleich sind: Name, Domain, intern/extern/spezifisch, Port,
Ablageort (Docker/Gerät), Datenlaufwerk, CPU und RAM.

Unter **App → Dateien** hat jede Installation ihr **eigenes Dateisystem** im Browser:
durchsuchen, Ordner anlegen, hochladen, Textdateien bearbeiten, löschen, herunterladen.
Damit lassen sich Apache/Nginx **mehrfach** installieren — je Webseite eine eigene Domain und
ein eigener Dateibereich.

Unter **App → Einstellungen** gibt es drei Bereiche:
- **Basis** — Name, Domain, Port, Sichtbarkeit, Laufwerk, CPU/RAM
- **Spezifisch** — was der Connector definiert (bei Minecraft z. B. MOTD, Spielmodus)
- **Erweitert** — z. B. **Plugins**: Quelle wählen, suchen, hinzufügen, Liste mit Löschen

### Enthaltene Apps
Minecraft (Java), Webseite (Apache + PHP), Webseite (Nginx), Mailserver, PostgreSQL.

## Cloudflare verknüpfen
Unter **Einstellungen → Cloudflare-Konto** verknüpfst du dein Konto — **du musst keinen Token
selbst anlegen**. Entweder per **Anmeldung bei Cloudflare** (weblab zeigt einen Code, du
bestätigst ihn im Cloudflare-Konto) oder per einmaliger **Konto-Anmeldung**, aus der weblab
selbst einen Token erzeugt, der nur DNS ändern darf. Danach legt weblab die DNS-Einträge
jeder App automatisch an (Webseiten: A-Record; Mailserver: A, MX, SPF, DMARC).

Details zum Connector-Format: [`connectors/README.md`](connectors/README.md).

Vorgaben und Komponentenwahl: [`anforderungen.md`](anforderungen.md).
