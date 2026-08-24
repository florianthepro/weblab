"""Alte Installationen (die zu einem Connector passen) erkennen, sichern und übernehmen.

Ablauf: erkennen -> tmp-Backup (stage) -> Connector sauber installieren, dabei das
Backup als Startdaten einspielen und die vorhandenen Einstellungen übernehmen."""
import glob
import os
import shutil
import tempfile
import time

import apps as appsvc
import catalog

IMPORT_STAGE = os.environ.get("WEBLAB_IMPORT_DIR", "/var/lib/weblab/import")
DIR_SIZE_MAX_SECONDS = 8
DIR_SIZE_MAX_ENTRIES = 3_000_000


def _connectors_with_import():
    return [c for c in catalog.load_all() if c.get("import")]


def _sig_ok(path, signatures, signatures_not=None):
    sigs = signatures if isinstance(signatures, list) else [signatures]
    if not sigs or not all(os.path.exists(os.path.join(path, s)) for s in sigs if s):
        return False
    for s in (signatures_not or []):
        if s and os.path.exists(os.path.join(path, s)):
            return False        # Ausschluss-Marker vorhanden -> passt doch nicht
    return True


def dir_size(path):
    """Grösse eines Ordners — zeit- und anzahlbegrenzt, damit ein riesiger/hängender
    Baum den Request-Thread nicht blockiert. Kann bei sehr grossen Bäumen unterschätzen."""
    total = seen = 0
    start = time.monotonic()
    for root, _dirs, files in os.walk(path):
        for name in files:
            seen += 1
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
            if seen >= DIR_SIZE_MAX_ENTRIES:
                return total
        if time.monotonic() - start > DIR_SIZE_MAX_SECONDS:
            return total
    return total


def scan():
    """Vorhandene Alt-Installationen finden, die zu einem Connector passen. Nach Pfad
    gruppiert — dieselbe Welt kann z. B. als Java ODER als Crossplay übernommen werden."""
    by_path = {}
    for con in _connectors_with_import():
        imp = con["import"]
        for pattern in imp.get("search", []):
            for path in glob.glob(pattern):
                rp = os.path.realpath(path)
                if not os.path.isdir(rp):
                    continue
                # eigene, bereits von weblab verwaltete Daten nicht als "alt" anbieten
                if rp.startswith(os.path.realpath(os.environ.get("WEBLAB_DATA", "/var/lib/weblab"))):
                    continue
                if not _sig_ok(rp, imp.get("signature"), imp.get("signature_not")):
                    continue
                entry = by_path.setdefault(rp, {"path": rp, "options": []})
                if not any(o["connector_id"] == con["id"] for o in entry["options"]):
                    entry["options"].append({"connector_id": con["id"], "name": con["name"],
                                             "label": imp.get("label", con["name"])})
    return sorted(by_path.values(), key=lambda e: e["path"])


def _detection(connector_id, path):
    rp = os.path.realpath(path)
    for d in scan():
        if d["path"] == rp and any(o["connector_id"] == connector_id for o in d["options"]):
            return d
    return None


def _read_properties(path):
    props = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    props[key.strip()] = value.strip()
    except OSError:
        pass
    return props


def _import_values(connector, seed_dir):
    """Aus der übernommenen server.properties die Feldwerte + LEVEL-Env ableiten, damit
    die vorhandenen Einstellungen und die Welt erhalten bleiben (nicht mit Defaults ersetzt)."""
    imp = connector.get("import") or {}
    props = _read_properties(os.path.join(seed_dir, imp.get("properties", "server.properties")))
    form = {}
    if props:
        # file_line-Felder: prop-Schlüssel aus dem prefix ableiten (z. B. "max-players=")
        for field in appsvc.file_line_fields(connector):
            prop_key = ((field.get("target") or {}).get("prefix") or "").rstrip("=").strip()
            if prop_key and prop_key in props:
                form[field["key"]] = props[prop_key]
        # zusätzliche Zuordnung für Env-Felder (z. B. Bedrock)
        for prop_key, field_key in (imp.get("properties_map") or {}).items():
            if prop_key in props:
                form[field_key] = props[prop_key]
    extra_env = {}
    level = props.get("level-name")
    if level and imp.get("level_env"):
        extra_env[imp["level_env"]] = level    # itzg soll die vorhandene Welt laden
    return form, extra_env


def stage(path):
    """tmp-Backup: den gefundenen Ordner in einen eigenen Staging-Ordner kopieren."""
    os.makedirs(IMPORT_STAGE, exist_ok=True)
    base = os.path.basename(path.rstrip("/")) or "import"
    dest = tempfile.mkdtemp(prefix=f"{base}-", dir=IMPORT_STAGE)
    shutil.copytree(path, dest, symlinks=True, dirs_exist_ok=True)
    return dest


def _fits(path):
    """Grobe Prüfung, ob genug Platz da ist (Backup + Einspielen = ~2x), sonst abbrechen."""
    try:
        need = dir_size(path) * 2 + 512 * 1024**2
        free = shutil.disk_usage(IMPORT_STAGE if os.path.isdir(IMPORT_STAGE)
                                 else os.path.dirname(IMPORT_STAGE) or "/").free
        return need <= free, need, free
    except OSError:
        return True, 0, 0


def take_over(connector_id, path, form=None):
    """Alt-Installation übernehmen: sichern -> sauber installieren -> Daten + Einstellungen
    einspielen. Das tmp-Backup wird danach wieder entfernt; die Originaldaten bleiben unberührt."""
    det = _detection(connector_id, path)
    if not det:
        raise ValueError("Diese Alt-Installation wurde nicht (mehr) gefunden.")
    connector = catalog.get(connector_id)
    if not connector:
        raise ValueError("Connector nicht gefunden.")
    ok, need, free = _fits(det["path"])
    if not ok:
        raise ValueError(f"Zu wenig Speicher: gebraucht ~{need // 1024**2} MB, frei ~{free // 1024**2} MB.")
    staged = stage(det["path"])
    try:
        imported_form, extra_env = _import_values(connector, staged)
        merged = dict(imported_form)
        # Schalter, die nicht in der Datei stehen, auf ihren Default lassen (nicht auf "aus").
        for field in catalog.all_fields(connector):
            if field.get("type") == "bool" and field["key"] not in merged:
                merged[field["key"]] = "true" if field.get("default") else "false"
        merged.update(form or {})               # explizite Vorgaben haben Vorrang
        merged.setdefault("name", connector.get("name", "Übernommen"))
        return appsvc.install(connector_id, merged, seed_dir=staged, extra_env=extra_env)
    finally:
        shutil.rmtree(staged, ignore_errors=True)    # tmp-Backup aufräumen (Daten sind eingespielt)
