"""Katalog: liest die Connector-Dateien und liefert Gruppen, Versionen und Feld-Schemata."""
import json
import os
import re

CONNECTOR_DIR = os.environ.get("WEBLAB_CONNECTORS", "/opt/weblab/connectors/keep")

# Gilt für alle Apps gleich, daher hier statt im Connector.
BASIC_FIELDS = [
    {"key": "name", "label": "Name", "type": "string", "required": True,
     "help": "Anzeigename dieser App-Instanz."},
    {"key": "domain", "label": "Domain", "type": "string",
     "help": "z. B. spiel.example.com — leer = nur über IP/Port erreichbar."},
    {"key": "exposure", "label": "Erreichbarkeit", "type": "select",
     "options": ["external", "internal", "specific"],
     "option_labels": {"external": "Extern (öffentlich)",
                       "internal": "Intern (nur dieser Server)",
                       "specific": "Spezifisch (nur erlaubte IPs)"},
     "default": "external"},
    {"key": "allow_cidr", "label": "Erlaubte IPs/CIDR", "type": "string",
     "help": "Nur bei „Spezifisch“ — z. B. 203.0.113.5/32, mehrere per Komma.",
     "depends_on": {"exposure": "specific"}},
    {"key": "host_port", "label": "Port (extern)", "type": "number",
     "help": "Port auf dem Server. Leer = automatisch."},
    {"key": "location", "label": "Ablageort", "type": "select",
     "options": ["docker", "device"],
     "option_labels": {"docker": "Docker (Container)", "device": "Auf dem Gerät (Host)"},
     "default": "docker"},
    {"key": "data_path", "label": "Datenlaufwerk / Pfad", "type": "select_path",
     "help": "Auf welcher Platte die Daten dieser App liegen."},
    {"key": "cpu", "label": "CPU (Kerne)", "type": "number", "default": 1, "min": 0.1, "max": 64, "step": 0.1},
    {"key": "ram_mb", "label": "RAM (MB)", "type": "number", "default": 1024, "min": 128, "max": 262144},
    {"key": "network", "label": "Netzwerk", "type": "select_network", "default": "bridge",
     "help": "Docker-Netzwerk / Subnetz dieser App."},
]

_cache = {"mtime": None, "items": []}


def _dir_signature():
    try:
        entries = sorted(os.listdir(CONNECTOR_DIR))
    except OSError:
        return None
    sig = []
    for name in entries:
        if name.endswith(".json"):
            try:
                sig.append((name, os.path.getmtime(os.path.join(CONNECTOR_DIR, name))))
            except OSError:
                pass
    return tuple(sig)


def load_all(force=False):
    """Alle Connector-Dateien laden."""
    sig = _dir_signature()
    if not force and sig is not None and sig == _cache["mtime"]:
        return _cache["items"]
    items = []
    if os.path.isdir(CONNECTOR_DIR):
        for name in sorted(os.listdir(CONNECTOR_DIR)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(CONNECTOR_DIR, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            if not data.get("id") or not data.get("image"):
                continue
            data.setdefault("group", data["id"])
            data.setdefault("name", data["id"])
            data.setdefault("version", "1")
            data.setdefault("category", "Sonstige")
            data.setdefault("icon", "📦")
            data.setdefault("fields", {})
            data["fields"].setdefault("required", [])
            data["fields"].setdefault("specific", [])
            data.setdefault("advanced", {})
            data.setdefault("env", {})
            data.setdefault("protocol", "tcp")
            data.setdefault("http", False)
            data.setdefault("container_port", 8080)
            items.append(data)
    _cache["mtime"] = sig
    _cache["items"] = items
    return items


def _version_key(version):
    """Numerisch sortieren: 1.21.5 > 1.20.6 > 1.9."""
    return [int(p) if p.isdigit() else p for p in re.split(r"[.\-_]", str(version))]


def groups():
    """Eine Kachel je Gruppe, neueste Version zuerst."""
    by_group = {}
    for conn in load_all():
        by_group.setdefault(conn["group"], []).append(conn)
    result = []
    for group_id, entries in by_group.items():
        try:
            entries.sort(key=lambda c: _version_key(c["version"]), reverse=True)
        except TypeError:
            entries.sort(key=lambda c: str(c["version"]), reverse=True)
        newest = entries[0]
        result.append({
            "group": group_id,
            "name": newest["name"],
            "icon": newest["icon"],
            "category": newest["category"],
            "summary": newest.get("summary", ""),
            "description": newest.get("description", ""),
            "versions": entries,
            "latest": newest,
        })
    result.sort(key=lambda g: (g["category"], g["name"]))
    return result


def get_group(group_id):
    for grp in groups():
        if grp["group"] == group_id:
            return grp
    return None


def get(connector_id):
    for conn in load_all():
        if conn["id"] == connector_id:
            return conn
    return None


def categories():
    return sorted({g["category"] for g in groups()})


def field_defaults(connector):
    """Standardwerte aller Connector-Felder (required + specific)."""
    values = {}
    for group in ("required", "specific"):
        for field in connector.get("fields", {}).get(group, []):
            if "default" in field:
                values[field["key"]] = field["default"]
    return values


def all_fields(connector):
    return (connector.get("fields", {}).get("required", [])
            + connector.get("fields", {}).get("specific", []))


def find_field(connector, key):
    for field in all_fields(connector):
        if field.get("key") == key:
            return field
    return None
