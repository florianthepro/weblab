#!/usr/bin/env python3
"""Selbsttest vor Installation/Update: verhindert, dass eine kaputte Version
aktiviert wird (der alte Dienst läuft dann einfach weiter).

Prüft:
 1. Alle Python-Module kompilieren (Syntax).
 2. Kein typografisches Anführungszeichen (’ ‘ “ ”) innerhalb von <script>-Blöcken —
    solche Zeichen als JS-String-Begrenzer sind ein Parse-Fehler, der eine ganze
    Seite lahmlegt (genau so fror die Setup-Seite bei 0 % ein).
 3. Alle Connector-JSON-Dateien sind gültiges JSON.

Aufruf: selfcheck.py <repo-root>   (Exit 0 = ok, 1 = Fehler)
"""
import json
import os
import py_compile
import re
import sys

SMART = "‘’“”"          # ‘ ’ “ ”
SCRIPT_RE = re.compile(r"<script>(.*?)</script>", re.S)


def fail(msg):
    print(f"SELBSTTEST FEHLGESCHLAGEN: {msg}")
    return 1


def main(root):
    rc = 0
    pydir = os.path.join(root, "software", "weblab")
    for name in sorted(os.listdir(pydir)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(pydir, name)
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as exc:
            rc = fail(f"{name}: Python-Syntaxfehler: {exc}")
        src = open(path, encoding="utf-8").read()
        for match in SCRIPT_RE.finditer(src):
            block = match.group(1)
            for ch in SMART:
                pos = block.find(ch)
                if pos >= 0:
                    line = src[:match.start(1) + pos].count("\n") + 1
                    rc = fail(f"{name}:{line}: typografisches Anführungszeichen "
                              f"({ch!r}) in einem <script>-Block — bricht das "
                              f"JavaScript der Seite.")
    conn = os.path.join(root, "connectors", "keep")
    if os.path.isdir(conn):
        for name in sorted(os.listdir(conn)):
            if not name.endswith(".json"):
                continue
            try:
                c = json.load(open(os.path.join(conn, name), encoding="utf-8"))
            except ValueError as exc:
                rc = fail(f"connectors/keep/{name}: ungültiges JSON: {exc}")
                continue
            rc = _check_connector(name, c) or rc
    if rc == 0:
        print("Selbsttest ok.")
    return rc


def _check_connector(name, c):
    """Schema-Prüfung eines Connectors — fängt kaputte Katalog-Einträge vor dem Deploy."""
    rc = 0
    problems = []
    if not c.get("id") or c["id"] != name[:-5]:
        problems.append("id fehlt oder passt nicht zum Dateinamen")
    image = c.get("image") or ""
    if not image:
        problems.append("image fehlt")
    elif ":" not in image or image.endswith(":latest"):
        # Nur Hinweis: gepinnte Tags sind besser, aber ein falsch geratener Pin
        # wäre schlimmer als latest.
        print(f"HINWEIS: connectors/keep/{name}: image ohne festen Tag ({image})")
    if c.get("http"):
        port = c.get("container_port")
        if not isinstance(port, int) or not 0 < port < 65536:
            problems.append(f"http-App ohne gültigen container_port: {port!r}")
    for p in c.get("fixed_ports") or []:
        if not isinstance(p.get("port"), int) or p.get("protocol", "tcp") not in ("tcp", "udp"):
            problems.append(f"fixed_ports-Eintrag ungültig: {p!r}")
    db = c.get("database")
    if db:
        choices = db.get("choices") or []
        if db.get("default") not in choices:
            problems.append("database.default fehlt in database.choices")
        for choice in choices:
            if not isinstance((db.get("env") or {}).get(choice), dict):
                problems.append(f"database.env.{choice} fehlt")
    for sec in ("required", "specific"):
        for f in (c.get("fields") or {}).get(sec, []):
            if not f.get("key"):
                problems.append(f"Feld ohne key in fields.{sec}")
            if f.get("type") == "password" and not (f.get("auto") or f.get("generate")):
                problems.append(f"Passwortfeld {f.get('key')} weder auto noch generate "
                                f"(sichtbare Passwortfelder sind nicht erlaubt)")
    for vol in c.get("volumes") or []:
        if not vol.get("host", "").startswith("/") or not vol.get("container", "").startswith("/"):
            problems.append(f"volumes-Eintrag ungültig: {vol!r}")
    mgr = c.get("manager")
    if mgr:
        mimage = mgr.get("image") or ""
        if not mimage or ":" not in mimage or mimage.endswith(":latest"):
            problems.append(f"manager.image fehlt oder ohne festen Tag: {mimage!r}")
        mport = mgr.get("container_port")
        if not isinstance(mport, int) or not 0 < mport < 65536:
            problems.append(f"manager.container_port ungültig: {mport!r}")
        if not str(mgr.get("mount") or "").startswith("/"):
            problems.append("manager.mount muss ein absoluter Container-Pfad sein")
        if mgr.get("data") and not str(mgr["data"]).startswith("/"):
            problems.append("manager.data muss ein absoluter Container-Pfad sein")
        if not c.get("data"):
            problems.append("manager ohne data-Block (kein Docroot zum Einbinden)")
        for filespec in mgr.get("files") or []:
            rel = str(filespec.get("path") or "")
            if not rel or rel.startswith("/") or ".." in rel:
                problems.append(f"manager.files-Pfad ungültig: {rel!r}")
    for prob in problems:
        rc = fail(f"connectors/keep/{name}: {prob}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
