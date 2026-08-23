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

---

## Weitere Felder (seit Version 1.1)

| Feld | Zweck | Beispiel |
|---|---|---|
| `init_files` | Startdateien, die im Datenverzeichnis angelegt werden (nur wenn nicht vorhanden). Platzhalter: `{app_name}`, `{domain}` und alle Feldwerte. | `index.html` einer Webseite |
| `fixed_ports` | Ports, die **fest** durchgereicht werden (Host = Container). Nötig, wenn Clients feste Ports erwarten. | Mail: 25, 143, 465, 587, 993 |
| `singleton` | `true` = App kann nur **einmal** installiert werden. | Mailserver |
| `hostname_template` | Hostname des Containers. | `{mail_hostname}.{mail_domain}` |
| `post_install` | `wait_for` (Datei abwarten) + `exec` (Kommandos im Container). | erstes Postfach anlegen |
| `dns_records` | DNS-Einträge, die weblab automatisch anlegt (bei verknüpftem Cloudflare-Konto). Platzhalter u. a. `{server_ip}`. | MX, SPF, DMARC |
| `notes` | Hinweise, die auf der App-Seite erscheinen. | „Port 25 beim Hoster freischalten“ |
| `default_exposure` | Vorbelegung der Erreichbarkeit. | `internal` bei Datenbanken |

## Mehrfach installieren
Ohne `singleton` lässt sich ein Connector **beliebig oft** installieren. Jede Installation ist
eigenständig: eigener Container, eigener Port, eigene Domain und ein **eigenes Datenverzeichnis**,
das im Panel unter **App → Dateien** verwaltet wird. So entstehen mehrere Webseiten aus demselben
Apache- oder Nginx-Connector.
