# Connectors — der Index zwischen Katalog, UI und Container

Jede Datei in `keep/` beschreibt **eine App-Version** (z. B. `minecraft-java-1.21.5.json`).
Der Server liest diese Dateien; daraus entstehen Katalog, Formulare und die Container-Konfiguration.

## Gruppierung
Mehrere Versionen derselben Software teilen sich `group`. Im Katalog erscheint dann **eine**
Kachel (wie im Ubuntu Store) mit Versions-Auswahl — nicht jede Version einzeln.

## Feldgruppen (3 pro App)
| Gruppe | Wann | Beispiel |
|---|---|---|
| `required` | **Pflicht beim Installieren** | RAM (GB) bei Minecraft |
| *basic* | Für **alle Apps gleich**, in der Software definiert | Name, Domain, Port, intern/extern, CPU, RAM, Ablageort, Datenlaufwerk |
| `specific` | App-spezifisch, beim Bearbeiten | MOTD, Spielmodus bei Minecraft |

## Targets — wohin ein Feldwert geschrieben wird
Der Connector definiert je Feld ein `target`:

| `kind` | Bedeutung | Felder |
|---|---|---|
| `env` | Umgebungsvariable des Containers | `name`, optional `format` (z. B. `"{value}G"`) |
| `file_line` | Zeile in einer Datei im Container, die mit `prefix` beginnt | `file`, `prefix` |
| `none` | Nur Anzeige / von der Software selbst verwendet | — |

Beispiel: `{"kind":"file_line","file":"/data/server.properties","prefix":"motd="}`
→ Das Feld `motd` ist die Zeile, die in `/data/server.properties` mit `motd=` beginnt.

## Advanced (z. B. Plugins)
`advanced.plugins` aktiviert die Plugin-Verwaltung: Quelle wählen → suchen → hinzufügen,
plus Gesamtliste mit Löschen-Funktion.

## Schema
```jsonc
{
  "id": "minecraft-java-1.21.5",     // eindeutig, = Dateiname
  "group": "minecraft-java",         // Katalog-Gruppierung
  "name": "Minecraft (Java)",
  "version": "1.21.5",
  "category": "Spiele",
  "icon": "⛏️",
  "summary": "Kurztext für den Katalog",
  "description": "Langtext",
  "runtime": "docker",
  "image": "itzg/minecraft-server:java21",
  "container_port": 25565,
  "protocol": "tcp",                 // tcp | udp
  "http": false,                     // true = per Domain via Reverse-Proxy erreichbar
  "data": {"container_path": "/data", "label": "Weltdaten"},
  "env": {"EULA": "TRUE"},           // feste Umgebungsvariablen
  "fields": {"required": [...], "specific": [...]},
  "advanced": {"plugins": {...}}
}
```
