"""Dateiverwaltung je App: sicher auf das Datenverzeichnis der App begrenzt."""
import os
import shutil
import time

TEXT_SUFFIXES = {
    ".html", ".htm", ".php", ".css", ".js", ".json", ".txt", ".md", ".xml", ".yml", ".yaml",
    ".ini", ".conf", ".cfg", ".properties", ".env", ".log", ".sql", ".csv", ".svg", ".toml",
}
MAX_EDIT_BYTES = 1_000_000
MAX_UPLOAD_BYTES = 200 * 1024 * 1024


class FileError(Exception):
    pass


def resolve(base, relative):
    """Pfad innerhalb von `base` auflösen; blockiert .. und Symlinks nach außen."""
    base_real = os.path.realpath(base)
    candidate = os.path.realpath(os.path.join(base_real, (relative or "").lstrip("/")))
    if candidate != base_real and not candidate.startswith(base_real + os.sep):
        raise FileError("Ungültiger Pfad.")
    return candidate


def relative_to(base, path):
    base_real = os.path.realpath(base)
    rel = os.path.relpath(os.path.realpath(path), base_real)
    return "" if rel == "." else rel.replace(os.sep, "/")


def is_text(name):
    return os.path.splitext(name)[1].lower() in TEXT_SUFFIXES


def listing(base, relative=""):
    """Inhalt eines Verzeichnisses: Ordner zuerst, dann Dateien."""
    os.makedirs(base, exist_ok=True)
    target = resolve(base, relative)
    if not os.path.isdir(target):
        raise FileError("Kein Verzeichnis.")
    entries = []
    for name in sorted(os.listdir(target)):
        full = os.path.join(target, name)
        try:
            stat = os.stat(full)
        except OSError:
            continue
        directory = os.path.isdir(full)
        entries.append({
            "name": name,
            "path": relative_to(base, full),
            "dir": directory,
            "size": 0 if directory else stat.st_size,
            "modified": time.strftime("%d.%m.%Y %H:%M", time.localtime(stat.st_mtime)),
            "text": (not directory) and is_text(name),
        })
    entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
    return entries


def breadcrumbs(relative):
    """Navigationspfad: [(Anzeigename, Pfad), …]"""
    crumbs = [("Start", "")]
    parts = [p for p in (relative or "").split("/") if p]
    for index, part in enumerate(parts):
        crumbs.append((part, "/".join(parts[: index + 1])))
    return crumbs


def read_text(base, relative):
    target = resolve(base, relative)
    if not os.path.isfile(target):
        raise FileError("Datei nicht gefunden.")
    if os.path.getsize(target) > MAX_EDIT_BYTES:
        raise FileError("Datei ist zu groß zum Bearbeiten (max. 1 MB).")
    with open(target, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def write_text(base, relative, content):
    target = resolve(base, relative)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(content.replace("\r\n", "\n"))
    os.chmod(target, 0o644)
    return relative_to(base, target)


def read_bytes(base, relative):
    target = resolve(base, relative)
    if not os.path.isfile(target):
        raise FileError("Datei nicht gefunden.")
    with open(target, "rb") as fh:
        return fh.read(), os.path.basename(target)


def save_upload(base, relative_dir, filename, data):
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileError("Datei ist zu groß (max. 200 MB).")
    safe = os.path.basename(filename or "").strip()
    if not safe or safe in (".", ".."):
        raise FileError("Ungültiger Dateiname.")
    directory = resolve(base, relative_dir)
    if not os.path.isdir(directory):
        raise FileError("Zielordner nicht gefunden.")
    target = resolve(base, os.path.join(relative_dir or "", safe))
    with open(target, "wb") as fh:
        fh.write(data)
    os.chmod(target, 0o644)
    return safe


def make_dir(base, relative_dir, name):
    safe = os.path.basename((name or "").strip())
    if not safe or safe in (".", ".."):
        raise FileError("Ungültiger Ordnername.")
    target = resolve(base, os.path.join(relative_dir or "", safe))
    os.makedirs(target, exist_ok=True)
    os.chmod(target, 0o755)
    return relative_to(base, target)


def delete(base, relative):
    target = resolve(base, relative)
    if target == os.path.realpath(base):
        raise FileError("Das Hauptverzeichnis kann nicht gelöscht werden.")
    if not os.path.exists(target):
        raise FileError("Nicht gefunden.")
    if os.path.isdir(target):
        shutil.rmtree(target)
    else:
        os.remove(target)
    return True


def usage(base):
    """Belegter Platz und Anzahl Dateien."""
    total, count = 0, 0
    for root, _dirs, files in os.walk(base):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
                count += 1
            except OSError:
                pass
    return {"bytes": total, "files": count}


def parse_multipart(body, content_type):
    """multipart/form-data lesen. Rückgabe: (felder, [(feld, dateiname, daten)])."""
    marker = "boundary="
    if marker not in content_type:
        raise FileError("Ungültiger Formulartyp.")
    boundary = content_type.split(marker, 1)[1].strip().strip('"')
    sep = b"--" + boundary.encode()
    fields, files = {}, []
    for part in body.split(sep):
        if part in (b"", b"--", b"--\r\n") or not part.strip(b"-\r\n"):
            continue
        head, _, data = part.partition(b"\r\n\r\n")
        if not _:
            continue
        data = data[:-2] if data.endswith(b"\r\n") else data
        headers = head.decode("utf-8", "replace")
        disposition = ""
        for line in headers.split("\r\n"):
            if line.lower().startswith("content-disposition:"):
                disposition = line
                break
        if not disposition:
            continue
        name = _param(disposition, "name")
        filename = _param(disposition, "filename")
        if filename:
            files.append((name, filename, data))
        elif name:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files


def _param(header, key):
    token = f'{key}="'
    if token not in header:
        return ""
    return header.split(token, 1)[1].split('"', 1)[0]
