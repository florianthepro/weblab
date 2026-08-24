"""App-Lebenszyklus: aus Connector + Formularwerten wird ein laufender Container."""
import html
import os
import shutil
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
import vpn

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


def env_for(connector, values, domain="", server_ip="", manage_host=""):
    """Feste Connector-Env + alle Felder mit target.kind == 'env'. In der festen Env
    werden {domain}/{server_ip}/{manage_host} eingesetzt — so muss z. B. die
    Nextcloud-Trusted-Domain nicht extra angegeben werden (nur die eine App-Domain)."""
    env = dict(connector.get("env") or {})
    ctx = {"domain": domain or "", "server_ip": server_ip or "", "manage_host": manage_host or ""}
    for key, val in list(env.items()):
        if isinstance(val, str) and "{" in val:
            for name, value in ctx.items():
                val = val.replace("{" + name + "}", value)
            env[key] = val.strip()
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


def default_manage_host(connector, manage_domain):
    """Verwaltungs-Subdomain einer App (z. B. apache.<domain>) — nur wenn der
    Connector eine vorgibt und eine Verwaltungs-Domain gesetzt ist."""
    sub = (connector or {}).get("manage_subdomain")
    if not sub or not manage_domain:
        return ""
    return f"{sub}.{manage_domain}"


def fixed_ports(connector):
    """Connector-Ports, die 1:1 durchgereicht werden (z. B. Mail: 25/143/465/587/993)."""
    return connector.get("fixed_ports") or []


def port_binding(exposure, host_port, container_port, protocol, connector=None):
    """intern = nur 127.0.0.1; tailscale = nur Tailnet-IP; sonst alle Interfaces."""
    if exposure == "internal":
        host = "127.0.0.1"
    elif exposure == "tailscale":
        host = vpn.ts_ip() or "127.0.0.1"   # ohne Tailnet-IP sicher intern binden
    else:
        host = "0.0.0.0"
    fixed = fixed_ports(connector or {})
    if fixed:
        # Feste Dienst-Ports (Host==Container), z. B. Mail 25 oder DNS 53.
        bindings = [(f"{host}:{p['port']}", p["port"], p.get("protocol", "tcp")) for p in fixed]
        # http-Apps brauchen zusätzlich die Weboberfläche am Proxy-Port (nur lokal, Caddy davor).
        if (connector or {}).get("http") and container_port not in [p["port"] for p in fixed]:
            bindings.append((f"127.0.0.1:{host_port}", container_port, "tcp"))
        return bindings
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
    if (connector.get("http") and app.get("domain") and server_ip
            and app.get("exposure") == "external"):
        plan.append({"type": "A", "name": app["domain"], "content": server_ip,
                     "priority": None, "comment": f"weblab: {app['name']}", "proxied": False})
    # Verwaltungs-Subdomain (Dashboard/Dateimanager der App) auf den Server zeigen.
    if app.get("manage_host") and server_ip:
        plan.append({"type": "A", "name": app["manage_host"], "content": server_ip,
                     "priority": None, "comment": f"weblab Verwaltung: {app['name']}",
                     "proxied": False})
    return plan


def apply_dns(app, connector, values):
    """DNS-Einträge der App automatisch anlegen — über alle verknüpften Konten hinweg."""
    accounts = store.cf_accounts()
    if not accounts:
        return [], "Kein Cloudflare-Konto verknüpft — Einträge bitte manuell setzen."
    server_ip = store.get_setting("server_ip", "") or sysinfo.public_ip()
    plan = dns_plan(app, connector, values, server_ip)
    if not plan:
        return [], None
    zones = integrations.all_zones(accounts)
    done, problems, zone_cache = [], [], {}
    for record in plan:
        match = _zone_match(zones, record["name"])
        if not match:
            # Zonen-Liste war leer/dünn -> Domain direkt bei Cloudflare auflösen und anlegen.
            match = integrations.resolve_zone(accounts, record["name"], zone_cache)
        if not match:
            problems.append(f"{record['name']}: keine passende Domain im Konto")
            continue
        ok, err = integrations.Cloudflare(match["token"]).set_record(
            match["name"], record["name"], record["content"], record["type"],
            proxied=record["proxied"], priority=record.get("priority"),
            comment=record.get("comment"))
        if ok:
            done.append(f"{record['type']} {record['name']}")
        else:
            problems.append(f"{record['name']}: {err}")
    return done, ("; ".join(problems) if problems else None)


def _zone_match(zones, hostname):
    """Zone (mit Token) zu einem Hostnamen — längste Übereinstimmung."""
    best, best_len = None, -1
    for zone in zones:
        z = zone["name"]
        if (hostname == z or hostname.endswith("." + z)) and len(z) > best_len:
            best, best_len = zone, len(z)
    return best


def sync_proxy():
    """Caddy-Konfiguration aus Manage-Domain, HTTP-Apps mit Domain und den
    App-Verwaltungs-Subdomains neu schreiben."""
    manage_domain = store.get_setting("manage_domain", "")
    routes = []
    panel_hosts = []
    cert_hosts = []
    for app in store.list_apps():
        if app.get("manage_host"):
            panel_hosts.append(app["manage_host"])
        connector = catalog.get(app["connector_id"])
        if not connector:
            continue
        if connector.get("tls_cert"):
            # Dienste mit eigenem TLS (Mailserver): Caddy soll ihr Zertifikat holen,
            # auch wenn ihre Domain nicht die Verwaltungs-Domain ist.
            fqdn = container_hostname(connector, app.get("values") or {})
            if fqdn:
                cert_hosts.append(fqdn)
        if (not connector.get("http") or not app.get("domain")
                or app.get("exposure") != "external"):
            continue        # nur öffentlich erreichbare Apps bekommen eine öffentliche Route
        routes.append({"domain": app["domain"], "port": app["host_port"], "name": app["name"]})
    access = store.get_setting("manage_access", "both")
    domain_ok = store.get_setting("domain_ok", "1") != "0"
    https_ready = integrations.https_ready(manage_domain) if manage_domain else False
    return integrations.write_caddyfile_safe(manage_domain, routes, panel_hosts=panel_hosts,
                                             access=access, domain_ok=domain_ok,
                                             cert_hosts=cert_hosts, https_ready=https_ready)


def _ufw(*args):
    """ufw aufrufen; ein Fehlschlag ist kein Abbruchgrund."""
    try:
        subprocess.run(["ufw", *args], capture_output=True, text=True, timeout=30)
        return True
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False


def _cidr_list(app):
    return [c.strip() for c in (app.get("allow_cidr") or "").split(",") if c.strip()]


def apply_firewall(app, connector=None):
    """Ports je nach Erreichbarkeit freigeben."""
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


def _run_app_container(app, connector):
    """Container der App starten. Bei gesetztem egress_id läuft die App durch einen
    gluetun-Ausgang (Mullvad/Proton); sonst normal am gewählten Netz."""
    data_dir = host_data_path(app, app["data_path"])
    if connector.get("data"):
        os.makedirs(data_dir, exist_ok=True)
    volumes = ([(data_dir, connector.get("data", {}).get("container_path", "/data"))]
               if connector.get("data") else [])
    env = env_for(connector, app["values"], app.get("domain", ""),
                  store.get_setting("server_ip", "") or sysinfo.public_ip(),
                  app.get("manage_host", ""))
    env.update(app.get("import_env") or {})     # z. B. LEVEL fuer eine uebernommene Welt
    ports = port_binding(app["exposure"], app["host_port"], app["container_port"],
                         connector.get("protocol", "tcp"), connector)
    hostname = container_hostname(connector, app["values"])
    # Dienste mit eigenem TLS (z. B. Mailserver): das von Caddy automatisch geholte
    # Let's-Encrypt-Zertifikat einbinden. Fehlt es noch, bleibt es beim Selbstsignierten
    # des Dienstes (kein Ausfall); der Watchdog liefert es nach, sobald Caddy es hat.
    if connector.get("tls_cert") and hostname:
        try:
            certdir = os.path.join(integrations.CERT_DIR, hostname)
            os.makedirs(certdir, exist_ok=True)
            integrations.export_cert(hostname)
            volumes.append((certdir, f"/etc/letsencrypt/live/{hostname}:ro"))
            env["SSL_DOMAIN"] = hostname
        except Exception:  # noqa: BLE001 - Zertifikat ist optional, niemals Abbruch
            pass
    egress = store.vpn_egress_get(app.get("egress_id")) if app.get("egress_id") else None
    if egress:
        input_ports = [cp for (_bind, cp, _proto) in ports]
        gluetun_name = vpn.egress_up(app["slug"], egress, ports, input_ports)
        return dockerctl.run_container(
            slug=app["slug"], image=connector["image"], env=env,
            volumes=volumes, cpu=app["cpu"], ram_mb=app["ram_mb"], hostname=hostname,
            network_mode=f"container:{gluetun_name}")
    vpn.egress_down(app["slug"])   # evtl. früheren Ausgang entfernen
    return dockerctl.run_container(
        slug=app["slug"], image=connector["image"], env=env,
        ports=ports, volumes=volumes, cpu=app["cpu"], ram_mb=app["ram_mb"],
        network=app["network"], hostname=hostname)


def _gen_credential(kind):
    """Zugangsdaten automatisch erzeugen: Benutzer -> 'admin', Passwort -> stark & zufaellig."""
    if kind == "user":
        return "admin"
    return secrets.token_urlsafe(15)


def install(connector_id, form, seed_dir=None, extra_env=None):
    """Neue App aus dem Katalog installieren. seed_dir: vorhandene Daten (Backup einer
    Alt-Installation), die vor dem ersten Start ins Datenverzeichnis gelegt werden.
    extra_env: zusaetzliche Container-Env (z. B. LEVEL fuer eine uebernommene Welt)."""
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
    for field in catalog.all_fields(connector):
        # Zugangsdaten (admin/Passwort) automatisch erzeugen, wenn nichts angegeben wurde.
        if field.get("auto") and not str(values.get(field["key"]) or "").strip():
            values[field["key"]] = _gen_credential(field["auto"])
    for field in connector["fields"].get("required", []):
        if field.get("required") and values.get(field["key"]) in (None, ""):
            raise ValueError(f"Pflichtfeld fehlt: {field.get('label', field['key'])}")

    name = (form.get("name") or connector["name"]).strip()
    slug = unique_slug(name)
    exposure = form.get("exposure") or connector.get("default_exposure") or "external"
    container_port = int(connector.get("container_port") or 8080)
    fixed = fixed_ports(connector)
    if fixed and not connector.get("http"):
        host_port = fixed[0]["port"]          # Dienste-Ports stehen fest (z. B. Mail 25)
    else:
        # http-Apps (auch mit festen Dienst-Ports) bekommen einen freien Proxy-Port.
        host_port = form.get("host_port")
        host_port = int(host_port) if str(host_port or "").isdigit() else \
            sysinfo.free_port(taken=store.used_host_ports())

    data_root = form.get("data_path") or "/var/lib/weblab/data"
    data_dir = host_data_path(slug, data_root)
    os.makedirs(data_dir, exist_ok=True)
    if seed_dir and os.path.isdir(seed_dir):
        # Backup der Alt-Installation vor dem ersten Start einspielen.
        shutil.copytree(seed_dir, data_dir, symlinks=True, dirs_exist_ok=True)

    manage_domain = store.get_setting("manage_domain", "")
    manage_host = (form.get("manage_host") or "").strip().lower() \
        or default_manage_host(connector, manage_domain)
    app_domain = (form.get("domain") or "").strip().lower()
    app_domain = app_domain.split("://")[-1].split("/")[0].split(":")[0].strip(". ")

    app = {
        "slug": slug, "name": name, "connector_id": connector["id"],
        "group_id": connector["group"], "version": connector["version"],
        "domain": app_domain,
        "exposure": exposure, "allow_cidr": form.get("allow_cidr") or "",
        "host_port": host_port, "container_port": container_port,
        "location": form.get("location") or "docker",
        "network": form.get("network") or "bridge",
        "data_path": data_root, "manage_host": manage_host,
        "egress_id": (form.get("egress_id") or "").strip(),
        "cpu": float(form.get("cpu") or 1), "ram_mb": int(float(form.get("ram_mb") or 1024)),
        "values_json": _dumps(values),
    }
    app_id = store.create_app(app)
    app["id"] = app_id
    app["values"] = values          # fuer _run_app_container/_post_install (nicht in der DB-Spalte)
    app["import_env"] = dict(extra_env or {})

    dockerctl.pull(connector["image"])
    _run_app_container(app, connector)
    # Der Container läuft bereits — Fehler hier werden gemeldet, nicht geworfen.
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
    """Startdateien aus dem Connector anlegen. Vorhandene Dateien bleiben unberührt."""
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
            # Werte landen in Web-Dateien -> maskieren.
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


def update(app_id, form, section="basic", allow_keys=None):
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
        if "manage_host" in form:
            changes["manage_host"] = (form.get("manage_host") or "").strip().lower()
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
        if "egress_id" in form:
            changes["egress_id"] = (form.get("egress_id") or "").strip()
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
            if allow_keys is not None and key not in allow_keys:
                continue          # eingeschraenkter Nutzer: nur erlaubte Felder anfassen
            if key in form or field.get("type") == "bool":
                values[key] = coerce(field, form.get(key))
        changes["values_json"] = _dumps(values)

    store.update_app(app_id, changes)
    app = store.get_app(app_id)

    if section == "basic":
        # Port/Ressourcen/Netzwerk erfordern einen neuen Container.
        _run_app_container(app, connector)
        # Konfigdateien im Container gehen beim Neuerstellen verloren.
        write_init_files(app, connector, app["values"])
        apply_config_files(app, connector, app["values"])
        apply_firewall(app, connector)
        if app.get("domain"):
            apply_dns(app, connector, app["values"])
        sync_proxy()
    else:
        env_changed = any((f.get("target") or {}).get("kind") == "env"
                          for f in connector["fields"].get("specific", []))
        if env_changed:
            _run_app_container(app, connector)
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
    vpn.egress_down(app["slug"])
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
