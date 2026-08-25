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
                json.load(open(os.path.join(conn, name), encoding="utf-8"))
            except ValueError as exc:
                rc = fail(f"connectors/keep/{name}: ungültiges JSON: {exc}")
    if rc == 0:
        print("Selbsttest ok.")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
