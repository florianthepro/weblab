"""Alte Installationen (die zu einem Connector passen) erkennen, sichern und übernehmen.

Ablauf: erkennen -> tmp-Backup (stage) -> Connector sauber installieren, dabei das
Backup als Startdaten einspielen (apps.install(seed_dir=...))."""
import glob
import os
import shutil
import time

import apps as appsvc
import catalog

IMPORT_STAGE = os.environ.get("WEBLAB_IMPORT_DIR", "/var/lib/weblab/import")


def _connectors_with_import():
    return [c for c in catalog.load_all() if c.get("import")]


def _sig_ok(path, signatures):
    sigs = signatures if isinstance(signatures, list) else [signatures]
    return any(os.path.exists(os.path.join(path, sig)) for sig in sigs if sig)


def dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
        if total > 50 * 1024**3:      # bei sehr großen Ordnern nicht ewig zählen
            break
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
                if not _sig_ok(rp, imp.get("signature")):
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


def stage(path):
    """tmp-Backup: den gefundenen Ordner in den Staging-Bereich kopieren; Pfad zurückgeben."""
    base = os.path.basename(path.rstrip("/")) or "import"
    dest = os.path.join(IMPORT_STAGE, f"{base}-{int(time.time())}")
    os.makedirs(IMPORT_STAGE, exist_ok=True)
    shutil.copytree(path, dest, symlinks=True, dirs_exist_ok=True)
    return dest


def take_over(connector_id, path, form=None):
    """Alt-Installation übernehmen: sichern -> sauber installieren -> Backup einspielen."""
    det = _detection(connector_id, path)
    if not det:
        raise ValueError("Diese Alt-Installation wurde nicht (mehr) gefunden.")
    staged = stage(det["path"])
    form = dict(form or {})
    form.setdefault("name", catalog.get(connector_id).get("name", "Übernommen"))
    return appsvc.install(connector_id, form, seed_dir=staged)
