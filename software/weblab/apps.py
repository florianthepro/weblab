"""App-Lebenszyklus: aus Connector + Formularwerten wird ein laufender Container."""
import html
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


def fixed_ports(connector):
    """Connector-Ports, die 1:1 durchgereicht werden (z. B. Mail: 25/143/465/587/993)."""
    return connector.get("fixed_ports") or []


def port_binding(exposure, host_port, container_port, protocol, connector=None):
    """intern = nur 127.0.0.1, sonst auf allen Interfaces (Firewall regelt „spezifisch“)."""
    host = "127.0.0.1" if exposure == "internal" else "0.0.0.0"
    fixed = fixed_ports(connector or {})
    if fixed:
        # Feste Dienste-Ports (Mail): Host-Port == Container-Port, sonst stimmen MX/Clients nicht.
        return [(f"{host}:{p['port']}", p["port"], p.get("protocol", "tcp")) for p in fixed]
    return [(f"{host}:{host_port}", container_port, protocol)]


def app_ports(app, connector):
    """Alle vom Host belegten Ports dieser App (für Firewall und Anzeige)."""
    fixed = fixed_ports(connector or {})
    if fixed:
        return [(p["port"], p.get("protocol", "tcp")) for p in fixed]
    return [(app["host_port"], (connector or {}).get("protocol", "tcp"))]



def dns_plan(app, connector, values, server_ip):
    """Welche DNS-Einträge diese App braucht (aus dem Connector bzw. der Domain)."""
    context = dict(values)
    context["server_ip"] = server_ip
    context["domain"] = app.get("domain") or ""
    context["app_name"] = app["name"]
    plan = []
    for spec in connector.get("dns_records") or []:
        try:
            plan.append({
                "type": spec.get("type", "A"),
                "name": spec["name"].format(**context),
                "content": spec["content"].format(**context),
                "priority": spec.get("priority"),
                "comment": spec.get("comment", ""),
                "proxied": False,
            })
        except (KeyError, IndexError, ValueError):
            continue
    # Web-Apps: ein A-Record auf die eigene Domain.
    if connector.get("http") and app.get("domain") and server_ip:
        plan.append({"type": "A", "name": app["domain"], "content": server_ip,
                     "priority": None, "comment": f"weblab: {app['name']}", "proxied": False})
    return plan


def apply_dns(app, connector, values):
    """DNS-Einträge der App automatisch anlegen (wenn ein Cloudflare-Konto verknüpft ist)."""
    token = store.get_setting("cf_token", "")
    if not token:
        return [], "Kein Cloudflare-Konto verknüpft — Einträge bitte manuell setzen."
    server_ip = store.get_setting("server_ip", "") or sysinfo.public_ip()
    plan = dns_plan(app, connector, values, server_ip)
    if not plan:
        return [], None
    cloudflare = integrations.Cloudflare(token)
    done, problems = [], []
    for record in plan:
        zone = _zone_for(cloudflare, record["name"])
        if not zone:
            problems.append(f"{record['name']}: keine passende Domain im Cloudflare-Konto")
            continue
        ok, err = cloudflare.set_record(
            zone, record["name"], record["content"], record["type"],
            proxied=record["proxied"], priority=record.get("priority"),
            comment=record.get("comment"))
        if ok:
            done.append(f"{record['type']} {record['name']}")
        else:
            problems.append(f"{record['name']}: {err}")
    return done, ("; ".join(problems) if problems else None)


def _zone_for(cloudflare, hostname):
    """Passende Zone zu einem Hostnamen finden (längste Übereinstimmung)."""
    try:
        zones = [z["name"] for z in cloudflare.zones()]
    except Exception:  # noqa: BLE001
        return None
    matches = [z for z in zones if hostname == z or hostname.endswith("." + z)]
    return max(matches, key=len) if matches else None


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


def apply_firewall(app, connector=None):
    """„Spezifisch“ = Ports nur für erlaubte CIDRs öffnen, sonst offen/geschlossen."""
    connector = connector or catalog.get(app["connector_id"]) or {}
    for port, proto in app_ports(app, connector):
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
    if connector.get("singleton"):
        for existing in store.list_apps():
            if existing["group_id"] == connector["group"]:
                raise ValueError(
                    f"{connector['name']} kann nur einmal installiert werden "
                    f"(bereits vorhanden: {existing['name']}).")

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
    fixed = fixed_ports(connector)
    if fixed:
        host_port = fixed[0]["port"]          # Dienste-Ports stehen fest (z. B. Mail 25)
    else:
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
                           connector.get("protocol", "tcp"), connector),
        volumes=[(data_dir, connector.get("data", {}).get("container_path", "/data"))]
        if connector.get("data") else [],
        cpu=app["cpu"], ram_mb=app["ram_mb"], network=app["network"],
        hostname=container_hostname(connector, values),
    )
    # Nachbereitung: Fehler hier machen die App nicht ungültig (Container läuft bereits).
    app["warnings"] = []
    def dns_step():
        done, problem = apply_dns(app, connector, values)
        app["dns_done"] = done
        if problem:
            raise RuntimeError(problem)

    for label, step in (("Konfiguration", lambda: _post_install(app, connector, values)),
                        ("Firewall", lambda: apply_firewall(app, connector)),
                        ("DNS", dns_step),
                        ("Reverse-Proxy", sync_proxy)):
        try:
            step()
        except Exception as exc:  # noqa: BLE001 - nur melden, nicht abbrechen
            app["warnings"].append(f"{label}: {exc}")
    return app


def container_hostname(connector, values, app_name=None):
    """Connector kann einen Hostnamen vorgeben (Mailserver: mail.example.com)."""
    template = connector.get("hostname_template")
    if not template:
        return None
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return None


def run_post_install_commands(app, connector, values):
    """Connector-Kommandos nach dem ersten Start ausführen (z. B. Postfach anlegen)."""
    commands = (connector.get("post_install") or {}).get("exec") or []
    results = []
    for template in commands:
        try:
            command = template.format(**values)
        except (KeyError, IndexError, ValueError):
            continue
        results.append(dockerctl.exec_sh(app["slug"], command, timeout=180))
    return results


def write_init_files(app, connector, values):
    """Startdateien aus dem Connector anlegen (z. B. index.html einer Webseite).

    Wird nur geschrieben, wenn die Datei noch nicht existiert — vorhandene
    Webseiten-Dateien werden nie überschrieben.
    """
    base = host_data_path(app, app["data_path"])
    written = []
    for spec in connector.get("init_files") or []:
        rel = (spec.get("path") or "").lstrip("/")
        if not rel or ".." in rel:
            continue
        target = os.path.join(base, rel)
        if os.path.exists(target):
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        fields = dict(values)
        fields["app_name"] = app["name"]
        fields["domain"] = app.get("domain") or ""
        if rel.lower().endswith((".html", ".htm", ".php")):
            # Werte landen in Web-Dateien -> maskieren, damit Sonderzeichen nichts zerlegen.
            fields = {k: html.escape(str(v), quote=True) if isinstance(v, str) else v
                      for k, v in fields.items()}
        try:
            content = (spec.get("content") or "").format(**fields)
        except (KeyError, IndexError, ValueError):
            content = spec.get("content") or ""
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(target, 0o644)
        written.append(rel)
    if written:
        # Webserver-Container laufen oft als www-data: Verzeichnis lesbar machen.
        os.chmod(base, 0o755)
    return written


def apply_config_files(app, connector, values, restart=True):
    """file_line-Felder in den Container schreiben (nach Start bzw. Neuerstellung)."""
    fields = file_line_fields(connector)
    if not fields:
        return []
    _wait_for_file(app["slug"], fields[0]["target"]["file"])
    applied = apply_file_lines(app, connector, values)
    if applied and restart:
        dockerctl.restart(app["slug"])
    return applied


def _post_install(app, connector, values):
    """Startdateien anlegen, Konfigfelder setzen, Connector-Kommandos ausführen."""
    write_init_files(app, connector, values)
    apply_config_files(app, connector, values)
    if (connector.get("post_install") or {}).get("exec"):
        ready = (connector.get("post_install") or {}).get("wait_for")
        if ready:
            _wait_for_file(app["slug"], ready)
        run_post_install_commands(app, connector, values)


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
                               connector.get("protocol", "tcp"), connector),
            volumes=[(data_dir, connector.get("data", {}).get("container_path", "/data"))]
            if connector.get("data") else [],
            cpu=app["cpu"], ram_mb=app["ram_mb"], network=app["network"],
        )
        # Konfigdateien im Container gehen beim Neuerstellen verloren -> erneut schreiben.
        write_init_files(app, connector, app["values"])
        apply_config_files(app, connector, app["values"])
        apply_firewall(app, connector)
        sync_proxy()
    else:
        env_changed = any((f.get("target") or {}).get("kind") == "env"
                          for f in connector["fields"].get("specific", []))
        if env_changed:
            data_dir = host_data_path(app, app["data_path"])
            dockerctl.run_container(
                slug=app["slug"], image=connector["image"],
                env=env_for(connector, app["values"]),
                ports=port_binding(app["exposure"], app["host_port"], app["container_port"],
                                   connector.get("protocol", "tcp"), connector),
                volumes=[(data_dir, connector.get("data", {}).get("container_path", "/data"))]
                if connector.get("data") else [],
                cpu=app["cpu"], ram_mb=app["ram_mb"], network=app["network"],
            )
            apply_config_files(app, connector, app["values"])
        else:
            applied = apply_file_lines(app, connector, app["values"])
            if applied:
                dockerctl.restart(app["slug"])
    return app


def remove(app_id, delete_data=False):
    app = store.get_app(app_id)
    if not app:
        return
    dockerctl.remove(app["slug"], missing_ok=True)
    connector = catalog.get(app["connector_id"]) or {}
    for port, proto in app_ports(app, connector):
        _ufw("--force", "delete", "allow", f"{port}/{proto}")
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
