"""App-Lebenszyklus: aus Connector + Formularwerten wird ein laufender Container."""
import os
import re
import secrets
import shlex
import subprocess
import urllib.request

import catalog
import dockerctl
import integrations
import store
import sysinfo

SLUG_RE = re.compile(r"[^a-z0-9-]+")


def slugify(name):
    slug = SLUG_RE.sub("-", (name or "").lower()).strip("-")
    return slug or "app"


def unique_slug(name):
    base = slugify(name)
    slug, index = base, 2
    while store.get_app_by_slug(slug):
        slug = f"{base}-{index}"
        index += 1
    return slug


def coerce(field, raw):
    """Formularwert gemäß Feldtyp umwandeln."""
    ftype = field.get("type", "string")
    if ftype == "bool":
        return str(raw).lower() in ("1", "true", "on", "yes", "ja")
    if ftype == "number":
        if raw in (None, ""):
            return field.get("default")
        try:
            num = float(raw)
        except (TypeError, ValueError):
            return field.get("default")
        if "min" in field:
            num = max(float(field["min"]), num)
        if "max" in field:
            num = min(float(field["max"]), num)
        return int(num) if float(num).is_integer() else num
    if ftype == "password" and not raw and field.get("generate"):
        return secrets.token_urlsafe(18)
    return raw if raw is not None else field.get("default", "")


def env_for(connector, values):
    """Feste Connector-Env + alle Felder mit target.kind == 'env'."""
    env = dict(connector.get("env") or {})
    for field in catalog.all_fields(connector):
        target = field.get("target") or {}
        if target.get("kind") != "env":
            continue
        value = values.get(field["key"], field.get("default"))
        if value is None or value == "":
            continue
        if field.get("type") == "bool":
            value = "true" if value else "false"
        fmt = target.get("format")
        env[target["name"]] = fmt.format(value=value) if fmt else str(value)
    return env


def file_line_fields(connector):
    return [f for f in catalog.all_fields(connector)
            if (f.get("target") or {}).get("kind") == "file_line"]


def apply_file_lines(app, connector, values, only_keys=None):
    """Felder in Dateien im Container schreiben (z. B. motd in server.properties)."""
    applied = []
    for field in file_line_fields(connector):
        key = field["key"]
        if only_keys is not None and key not in only_keys:
            continue
        if key not in values:
            continue
        value = values[key]
        if field.get("type") == "bool":
            value = "true" if value else "false"
        target = field["target"]
        dockerctl.set_file_line(app["slug"], target["file"], target["prefix"], value)
        applied.append(key)
    return applied


def host_data_path(app_or_slug, data_path):
    slug = app_or_slug if isinstance(app_or_slug, str) else app_or_slug["slug"]
    base = data_path or "/var/lib/weblab/data"
    return os.path.join(base, slug)


def port_binding(exposure, host_port, container_port, protocol):
    """intern = nur 127.0.0.1, sonst auf allen Interfaces (Firewall regelt „spezifisch“)."""
    bind = f"127.0.0.1:{host_port}" if exposure == "internal" else f"0.0.0.0:{host_port}"
    return [(bind, container_port, protocol)]


def sync_proxy():
    """Caddy-Konfiguration aus Manage-Domain + allen HTTP-Apps mit Domain neu schreiben."""
    manage_domain = store.get_setting("manage_domain", "")
    routes = []
    for app in store.list_apps():
        connector = catalog.get(app["connector_id"])
        if not connector or not connector.get("http") or not app.get("domain"):
            continue
        routes.append({"domain": app["domain"], "port": app["host_port"], "name": app["name"]})
    return integrations.write_caddyfile_safe(manage_domain, routes)


def _ufw(*args):
    """ufw aufrufen; fehlt ufw oder schlägt es fehl, ist das kein Abbruchgrund."""
    try:
        subprocess.run(["ufw", *args], capture_output=True, text=True, timeout=30)
        return True
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False


def _cidr_list(app):
    return [c.strip() for c in (app.get("allow_cidr") or "").split(",") if c.strip()]


def apply_firewall(app):
    """„Spezifisch“ = Port nur für erlaubte CIDRs öffnen, sonst offen/geschlossen."""
    port, proto = app["host_port"], "tcp"
    _ufw("--force", "delete", "allow", f"{port}/{proto}")
    for cidr in _cidr_list(app):
        _ufw("--force", "delete", "allow", "from", cidr, "to", "any",
             "port", str(port), "proto", proto)
    if app["exposure"] == "external":
        _ufw("allow", f"{port}/{proto}", "comment", f"weblab {app['slug']}")
    elif app["exposure"] == "specific":
        for cidr in _cidr_list(app):
            _ufw("allow", "from", cidr, "to", "any", "port", str(port),
                 "proto", proto, "comment", f"weblab {app['slug']}")


def install(connector_id, form):
    """Neue App aus dem Katalog installieren."""
    connector = catalog.get(connector_id)
    if not connector:
        raise ValueError("Connector nicht gefunden.")

    values = dict(catalog.field_defaults(connector))
    for field in catalog.all_fields(connector):
        key = field["key"]
        if key in form or field.get("type") == "bool":
            values[key] = coerce(field, form.get(key))
    for field in connector["fields"].get("required", []):
        if field.get("required") and values.get(field["key"]) in (None, ""):
            raise ValueError(f"Pflichtfeld fehlt: {field.get('label', field['key'])}")

    name = (form.get("name") or connector["name"]).strip()
    slug = unique_slug(name)
    exposure = form.get("exposure") or connector.get("default_exposure") or "external"
    container_port = int(connector.get("container_port") or 8080)
    host_port = form.get("host_port")
    host_port = int(host_port) if str(host_port or "").isdigit() else \
        sysinfo.free_port(taken=store.used_host_ports())

    data_root = form.get("data_path") or "/var/lib/weblab/data"
    data_dir = host_data_path(slug, data_root)
    os.makedirs(data_dir, exist_ok=True)

    app = {
        "slug": slug, "name": name, "connector_id": connector["id"],
        "group_id": connector["group"], "version": connector["version"],
        "domain": (form.get("domain") or "").strip().lower(),
        "exposure": exposure, "allow_cidr": form.get("allow_cidr") or "",
        "host_port": host_port, "container_port": container_port,
        "location": form.get("location") or "docker",
        "network": form.get("network") or "bridge",
        "data_path": data_root,
        "cpu": float(form.get("cpu") or 1), "ram_mb": int(float(form.get("ram_mb") or 1024)),
        "values_json": _dumps(values),
    }
    app_id = store.create_app(app)
    app["id"] = app_id

    dockerctl.pull(connector["image"])
    dockerctl.run_container(
        slug=slug, image=connector["image"], env=env_for(connector, values),
        ports=port_binding(exposure, host_port, container_port,
                           connector.get("protocol", "tcp")),
        volumes=[(data_dir, connector.get("data", {}).get("container_path", "/data"))]
        if connector.get("data") else [],
        cpu=app["cpu"], ram_mb=app["ram_mb"], network=app["network"],
    )
    # Nachbereitung: Fehler hier machen die App nicht ungültig (Container läuft bereits).
    app["warnings"] = []
    for label, step in (("Konfiguration", lambda: _post_install(app, connector, values)),
                        ("Firewall", lambda: apply_firewall(app)),
                        ("Reverse-Proxy", sync_proxy)):
        try:
            step()
        except Exception as exc:  # noqa: BLE001 - nur melden, nicht abbrechen
            app["warnings"].append(f"{label}: {exc}")
    return app


def _post_install(app, connector, values):
    """Datei-basierte Felder setzen; App-spezifische Startdateien anlegen."""
    if connector["id"].startswith("website-nginx"):
        index = os.path.join(host_data_path(app, app["data_path"]), "index.html")
        if not os.path.exists(index):
            title = values.get("index_title", app["name"])
            with open(index, "w", encoding="utf-8") as fh:
                fh.write(f"<!doctype html><meta charset=utf-8><title>{title}</title>"
                         f"<h1>{title}</h1><p>Läuft über weblab.</p>\n")
    if file_line_fields(connector):
        # Container schreibt seine Konfigdateien erst beim ersten Start.
        _wait_for_file(app["slug"], file_line_fields(connector)[0]["target"]["file"])
        apply_file_lines(app, connector, values)
        dockerctl.restart(app["slug"])


def _wait_for_file(slug, path, attempts=60, delay=2):
    import time
    for _ in range(attempts):
        out = dockerctl.exec_sh(slug, f"test -f {shlex.quote(path)} && echo yes || true")
        if "yes" in out:
            return True
        time.sleep(delay)
    return False


def update(app_id, form, section="basic"):
    """Bestehende App bearbeiten (basic = Container neu erstellen, specific = Dateien)."""
    app = store.get_app(app_id)
    if not app:
        raise ValueError("App nicht gefunden.")
    connector = catalog.get(app["connector_id"])
    if not connector:
        raise ValueError("Connector nicht gefunden.")

    values = dict(app["values"])
    changes = {}

    if section == "basic":
        if "name" in form and form["name"].strip():
            changes["name"] = form["name"].strip()
        if "domain" in form:
            changes["domain"] = (form.get("domain") or "").strip().lower()
        if "exposure" in form:
            changes["exposure"] = form["exposure"]
        if "allow_cidr" in form:
            changes["allow_cidr"] = form.get("allow_cidr") or ""
        if str(form.get("host_port") or "").isdigit():
            changes["host_port"] = int(form["host_port"])
        if "location" in form:
            changes["location"] = form["location"]
        if "network" in form:
            changes["network"] = form["network"]
        if "data_path" in form and form["data_path"]:
            changes["data_path"] = form["data_path"]
        if form.get("cpu"):
            changes["cpu"] = float(form["cpu"])
        if form.get("ram_mb"):
            changes["ram_mb"] = int(float(form["ram_mb"]))
    else:
        fields = connector["fields"].get("specific", []) if section == "specific" \
            else catalog.all_fields(connector)
        for field in fields:
            key = field["key"]
            if key in form or field.get("type") == "bool":
                values[key] = coerce(field, form.get(key))
        changes["values_json"] = _dumps(values)

    store.update_app(app_id, changes)
    app = store.get_app(app_id)

    if section == "basic":
        # Port/Ressourcen/Netzwerk erfordern einen neuen Container.
        data_dir = host_data_path(app, app["data_path"])
        os.makedirs(data_dir, exist_ok=True)
        dockerctl.run_container(
            slug=app["slug"], image=connector["image"],
            env=env_for(connector, app["values"]),
            ports=port_binding(app["exposure"], app["host_port"], app["container_port"],
                               connector.get("protocol", "tcp")),
            volumes=[(data_dir, connector.get("data", {}).get("container_path", "/data"))]
            if connector.get("data") else [],
            cpu=app["cpu"], ram_mb=app["ram_mb"], network=app["network"],
        )
        apply_firewall(app)
        sync_proxy()
    else:
        env_changed = any((f.get("target") or {}).get("kind") == "env"
                          for f in connector["fields"].get("specific", []))
        applied = apply_file_lines(app, connector, app["values"])
        if env_changed:
            data_dir = host_data_path(app, app["data_path"])
            dockerctl.run_container(
                slug=app["slug"], image=connector["image"],
                env=env_for(connector, app["values"]),
                ports=port_binding(app["exposure"], app["host_port"], app["container_port"],
                                   connector.get("protocol", "tcp")),
                volumes=[(data_dir, connector.get("data", {}).get("container_path", "/data"))]
                if connector.get("data") else [],
                cpu=app["cpu"], ram_mb=app["ram_mb"], network=app["network"],
            )
        elif applied:
            dockerctl.restart(app["slug"])
    return app


def remove(app_id, delete_data=False):
    app = store.get_app(app_id)
    if not app:
        return
    dockerctl.remove(app["slug"], missing_ok=True)
    _ufw("--force", "delete", "allow", f"{app['host_port']}/tcp")
    if delete_data:
        path = host_data_path(app, app["data_path"])
        if path.startswith(("/var/lib/weblab/", "/mnt/", "/srv/", "/data/")) and os.path.isdir(path):
            subprocess.run(["rm", "-rf", path], capture_output=True, text=True)
    store.delete_app(app_id)
    sync_proxy()


# ---------- Advanced: Plugins ----------
def plugin_config(connector):
    return (connector.get("advanced") or {}).get("plugins") or {}


def list_plugins(app, connector):
    config = plugin_config(connector)
    if not config.get("enabled"):
        return []
    path = config.get("path", "/data/plugins")
    out = dockerctl.exec_sh(
        app["slug"],
        f"mkdir -p {shlex.quote(path)}; ls -l {shlex.quote(path)} 2>/dev/null | awk '{{print $5\"|\"$9}}'")
    items = []
    for line in out.splitlines():
        size, _, name = line.partition("|")
        if name.strip().endswith(".jar"):
            items.append({"name": name.strip(),
                          "size": int(size) if size.strip().isdigit() else 0})
    return sorted(items, key=lambda p: p["name"].lower())


def add_plugin(app, connector, source, project_id):
    config = plugin_config(connector)
    if not config.get("enabled"):
        raise ValueError("Diese App unterstützt keine Plugins.")
    source_cfg = next((s for s in config.get("sources", []) if s["id"] == source), {})
    url, filename = integrations.plugin_download_url(
        source, project_id, source_cfg.get("loader"), source_cfg.get("game_versions"))
    if not url:
        raise ValueError("Keine passende Download-Datei gefunden.")
    path = config.get("path", "/data/plugins")
    host_dir = os.path.join(host_data_path(app, app["data_path"]),
                            path.replace(connector.get("data", {}).get("container_path", "/data"), "").strip("/"))
    os.makedirs(host_dir, exist_ok=True)
    target = os.path.join(host_dir, os.path.basename(filename))
    req = urllib.request.Request(url, headers={"User-Agent": integrations.UA})
    with urllib.request.urlopen(req, timeout=120) as resp, open(target, "wb") as fh:
        fh.write(resp.read())
    if config.get("restart_after_change"):
        dockerctl.restart(app["slug"])
    return os.path.basename(filename)


def delete_plugin(app, connector, filename):
    config = plugin_config(connector)
    if "/" in filename or ".." in filename:
        raise ValueError("Ungültiger Dateiname.")
    path = config.get("path", "/data/plugins")
    dockerctl.exec_sh(app["slug"], f"rm -f {shlex.quote(path + '/' + filename)}")
    if config.get("restart_after_change"):
        dockerctl.restart(app["slug"])


def _dumps(values):
    import json
    return json.dumps(values, ensure_ascii=False)
