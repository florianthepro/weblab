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
| **DNS** | DNS-Einträge der Domain (über Cloudflare) |
| **Speicher** | Laufwerke, Belegung, Datenpfade der Apps |
| **Benutzer** | Konten für die Oberfläche |
| **Einstellungen** | Domain, Cloudflare-Token, Katalog |

## Apps

Jede App kommt aus einer **Connector-Datei** in [`connectors/keep/`](connectors/keep).
Im Katalog erscheint eine App einmal (z. B. „Minecraft (Java)“) mit **Versionsauswahl**.

Beim Installieren werden nur die **Pflichtfelder** abgefragt (z. B. RAM bei Minecraft) plus die
**Basis-Angaben**, die für alle Apps gleich sind: Name, Domain, intern/extern/spezifisch, Port,
Ablageort (Docker/Gerät), Datenlaufwerk, CPU und RAM.

Unter **App → Einstellungen** gibt es drei Bereiche:
- **Basis** — Name, Domain, Port, Sichtbarkeit, Laufwerk, CPU/RAM
- **Spezifisch** — was der Connector definiert (bei Minecraft z. B. MOTD, Spielmodus)
- **Erweitert** — z. B. **Plugins**: Quelle wählen, suchen, hinzufügen, Liste mit Löschen

Details zum Connector-Format: [`connectors/README.md`](connectors/README.md).

Vorgaben und Komponentenwahl: [`anforderungen.md`](anforderungen.md).
