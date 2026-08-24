"""HTTP-Server, Routing, Sitzungen und alle Seiten der Oberfläche."""
import base64
import hmac
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.parse
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import apps as appsvc
import catalog
import dockerctl
import files
import integrations
import store
import sysinfo
import ui
import vpn

HOST = os.environ.get("WEBLAB_BIND", "127.0.0.1")
PORT = int(os.environ.get("WEBLAB_PORT", "8099"))
COOKIE = "weblab_session"
EXPOSURE_LABELS = {"external": "Extern", "internal": "Intern", "specific": "Spezifisch",
                   "tailscale": "Tailscale (privat)"}
LOCATION_LABELS = {"docker": "Docker", "device": "Gerät"}
SESSION_MAX_AGE = 12 * 3600

# Fortschritt des Setup-Assistenten
SETUP_STATE = {"running": False, "percent": 0, "step": "", "done": False, "error": None}

# Laufende Cloudflare-Anmeldung (OAuth)
CF_LOGIN = {"state": "", "verifier": "", "client_id": "", "client_secret": "",
            "redirect_uri": ""}

# Neue/aktualisierte Connectoren erkennen
CONNECTOR_NEW_DAYS = 14


def connector_news():
    """IDs von Connectoren, die seit Kurzem neu oder in neuer Version da sind."""
    try:
        known = json.loads(store.get_setting("connectors_seen", "") or "{}")
    except (ValueError, json.JSONDecodeError):
        known = {}
    current = {f"{c['id']}@{c['version']}" for c in catalog.load_all()}
    first_run, now, changed = not known, time.time(), False
    for key in current:
        if key not in known:
            known[key] = 0 if first_run else now   # Erstlauf ist der Grundstand
            changed = True
    for key in [k for k in known if k not in current]:
        del known[key]
        changed = True
    if changed:
        store.set_setting("connectors_seen", json.dumps(known))
    return {k.split("@")[0] for k, ts in known.items()
            if ts and now - ts < CONNECTOR_NEW_DAYS * 86400}


# Sitzungen (signierte Cookies) + CSRF
_SECRET = None


def _secret():
    """Sitzungs-Schlüssel einmal laden und im Speicher halten — der Login hängt
    dann nicht mehr an einem DB-Zugriff pro Anfrage."""
    global _SECRET
    if not _SECRET:
        _SECRET = (store.get_setting("session_secret") or "").encode()
    return _SECRET or b"weblab-insecure-fallback"


def sign_session(payload):
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    mac = hmac.new(_secret(), raw.encode(), sha256).hexdigest()[:32]
    return f"{raw}.{mac}"


def read_session(cookie_value):
    if not cookie_value or "." not in cookie_value:
        return None
    raw, _, mac = cookie_value.rpartition(".")
    expected = hmac.new(_secret(), raw.encode(), sha256).hexdigest()[:32]
    if not hmac.compare_digest(mac, expected):
        return None
    try:
        padded = raw + "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


def csrf_for(session):
    return hmac.new(_secret(), f"csrf:{session.get('sid', '')}".encode(), sha256).hexdigest()[:32]


# Setup-Ablauf (Hintergrund, damit der Fortschritt abfragbar bleibt)
def run_setup(username, password, domain, cf_email="", cf_key=""):
    def worker():
        try:
            SETUP_STATE.update({"running": True, "percent": 5, "step": "Benutzer anlegen",
                                "done": False, "error": None})
            if store.user_count() == 0:
                store.create_user(username, password)
            SETUP_STATE.update({"percent": 15, "step": "Domain speichern"})
            store.set_setting("manage_domain", domain)

            SETUP_STATE.update({"percent": 25, "step": "Server-IP ermitteln"})
            server_ip = sysinfo.public_ip()
            store.set_setting("server_ip", server_ip)

            cf_token = ""
            if cf_email and cf_key:
                SETUP_STATE.update({"percent": 40, "step": "Cloudflare-Konto verknüpfen"})
                cf_token, err = integrations.link_account(cf_email, cf_key, label=domain or "weblab")
                if cf_token:
                    store.add_cf_account(cf_email or "Cloudflare", cf_token)
                    store.set_setting("cf_status", "verknüpft")
                else:
                    store.set_setting("cf_status", f"nicht verknüpft: {err or ''}")

            if cf_token and domain:
                SETUP_STATE.update({"percent": 55, "step": "DNS-Eintrag anlegen"})
                ok, err = integrations.Cloudflare(cf_token).set_record(
                    domain, domain, server_ip, "A", proxied=False,
                    comment="weblab Verwaltungsoberfläche")
                store.set_setting("dns_status", "automatisch gesetzt" if ok
                                  else f"manuell nötig: {err or ''}")
            else:
                store.set_setting("dns_status", "manuell")

            SETUP_STATE.update({"percent": 70, "step": "Reverse-Proxy konfigurieren"})
            ok, err = appsvc.sync_proxy()
            if not ok:
                store.set_setting("proxy_status", err or "Fehler")

            SETUP_STATE.update({"percent": 85, "step": "Docker prüfen"})
            store.set_setting("docker_ok", "1" if dockerctl.available() else "0")

            SETUP_STATE.update({"percent": 95, "step": "Zertifikat wird ausgestellt"})
            time.sleep(3)
            store.set_setting("setup_done", "1")
            SETUP_STATE.update({"percent": 100, "step": "Fertig", "done": True, "running": False})
        except Exception as exc:  # noqa: BLE001 - Fehler dem Nutzer zeigen
            SETUP_STATE.update({"error": str(exc), "running": False, "step": "Fehler"})

    threading.Thread(target=worker, daemon=True).start()


# Request-Handler
class Handler(BaseHTTPRequestHandler):
    server_version = "weblab"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # Zugriffe protokolliert Caddy

    def _send(self, body, status=200, ctype="text/html; charset=utf-8", headers=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "same-origin")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload, status=200):
        self._send(json.dumps(payload), status, "application/json; charset=utf-8")

    def _redirect(self, location, flash=None):
        headers = {"Location": location}
        if flash:
            kind, text = flash
            if kind == "err":
                store.set_setting("banner", text)      # bleibt bis zum Schließen
            else:
                value = urllib.parse.quote(f"{kind}|{text}")
                headers["Set-Cookie"] = f"weblab_flash={value}; Path=/; Max-Age=20; SameSite=Strict"
        self._send("", 303, "text/plain", headers)

    @property
    def cookies(self):
        raw = self.headers.get("Cookie", "")
        jar = {}
        for part in raw.split(";"):
            key, _, value = part.strip().partition("=")
            if key:
                jar[key] = urllib.parse.unquote(value)
        return jar

    def _take_flash(self):
        value = self.cookies.get("weblab_flash")
        if not value or "|" not in value:
            return None
        kind, _, text = value.partition("|")
        return (kind, text)

    @property
    def session(self):
        if not hasattr(self, "_session"):
            self._session = read_session(self.cookies.get(COOKIE))
        return self._session

    def _form(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
        return {k: v[0] for k, v in parsed.items()}

    def _query(self):
        query = urllib.parse.urlparse(self.path).query
        parsed = urllib.parse.parse_qs(query, keep_blank_values=True)
        return {k: v[0] for k, v in parsed.items()}

    def _render(self, title, body, active="/", head=""):
        user = (self.session or {}).get("user")
        page = ui.page(title, body, active=active, user=user, flash=self._take_flash(), head=head,
                       banner=ui.banner_html(store.get_setting("banner", ""), self.csrf))
        self._send(page, headers={"Set-Cookie": "weblab_flash=; Path=/; Max-Age=0"})

    def _require_auth(self):
        if not self.session:
            self._redirect("/login")
            return False
        return True

    def _check_csrf(self, form):
        token = form.get("csrf", "")
        return self.session and hmac.compare_digest(token, csrf_for(self.session))

    @property
    def csrf(self):
        return csrf_for(self.session) if self.session else ""

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        try:
            self.route_get(path)
        except Exception as exc:  # noqa: BLE001
            self._send(ui.bare("Fehler", f'<div class="box card"><h1>Fehler</h1>'
                                         f'<p class="sub">{ui.esc(exc)}</p>'
                                         f'<a class="btn" href="/">Zurück</a></div>'), 500)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        try:
            self.route_post(path)
        except Exception as exc:  # noqa: BLE001
            self._redirect(self.headers.get("Referer", "/"), ("err", str(exc)))

    def route_get(self, path):
        if not store.is_setup_done() and not path.startswith(("/setup", "/api/setup", "/static")):
            return self._redirect("/setup")

        if path == "/setup":
            return self.page_setup()
        if path == "/setup/progress":
            return self.page_setup_progress()
        if path == "/api/setup/status":
            return self._json(SETUP_STATE)
        if path == "/login":
            return self.page_login()
        if path == "/logout":
            return self._send("", 303, "text/plain", {
                "Location": "/login",
                "Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"})

        if not self._require_auth():
            return None

        if path == "/":
            host = (self.headers.get("Host") or "").split(":")[0].lower()
            if host:
                for app in store.list_apps():
                    if (app.get("manage_host") or "").lower() == host:
                        return self._redirect(f"/apps/{app['id']}")
            return self.page_dashboard()
        if path == "/apps":
            return self.page_apps()
        if path == "/api/stats":
            return self._json(self.collect_stats())
        if re.fullmatch(r"/apps/catalog/[\w.-]+", path):
            return self.page_catalog_detail(path.rsplit("/", 1)[1])
        match = re.fullmatch(r"/apps/(\d+)", path)
        if match:
            return self.page_app_detail(int(match.group(1)))
        match = re.fullmatch(r"/apps/(\d+)/logs", path)
        if match:
            return self.page_app_logs(int(match.group(1)))
        match = re.fullmatch(r"/apps/(\d+)/files", path)
        if match:
            return self.page_app_files(int(match.group(1)))
        match = re.fullmatch(r"/apps/(\d+)/files/download", path)
        if match:
            return self.download_file(int(match.group(1)))
        match = re.fullmatch(r"/apps/(\d+)/edit", path)
        if match:
            return self.page_app_edit(int(match.group(1)))
        if path == "/network":
            return self.page_network()
        if path == "/storage":
            return self.page_storage()
        if path == "/users":
            return self.page_users()
        if path == "/settings":
            return self._redirect("/network")
        if path == "/network/cloudflare/callback":
            return self.cf_callback()
        return self._send(ui.page("Nicht gefunden", "<h1>404</h1><p class='sub'>Seite gibt es nicht.</p>",
                                  user=(self.session or {}).get("user")), 404)

    def route_post(self, path):
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            match = re.fullmatch(r"/apps/(\d+)/files", path)
            if not match or not self._require_auth():
                return self._redirect("/apps")
            return self.do_upload(int(match.group(1)), content_type)
        form = self._form()

        if path == "/setup":
            return self.do_setup(form)
        if path == "/login":
            return self.do_login(form)

        if not self._require_auth():
            return None
        if not self._check_csrf(form):
            return self._redirect(self.headers.get("Referer", "/"),
                                  ("err", "Sicherheits-Token ungültig — bitte erneut versuchen."))

        if path == "/apps/install":
            return self.do_install(form)
        match = re.fullmatch(r"/apps/(\d+)/edit", path)
        if match:
            return self.do_app_edit(int(match.group(1)), form)
        match = re.fullmatch(r"/apps/(\d+)/action", path)
        if match:
            return self.do_app_action(int(match.group(1)), form)
        match = re.fullmatch(r"/apps/(\d+)/plugins", path)
        if match:
            return self.do_plugins(int(match.group(1)), form)
        match = re.fullmatch(r"/apps/(\d+)/files", path)
        if match:
            return self.do_files(int(match.group(1)), form)
        if path == "/network":
            return self.do_network(form)
        if path == "/users":
            return self.do_users(form)
        if path == "/banner":
            store.set_setting("banner", "")
            return self._redirect(self.headers.get("Referer", "/"))
        return self._redirect("/")

    # Setup + Login
    def page_setup(self):
        if store.is_setup_done():
            return self._redirect("/login")
        server_ip = store.get_setting("server_ip") or ""
        body = f"""<div class="box">
<div class="card">
<h1>weblab einrichten</h1>
<p class="sub">Konto und Domain festlegen.</p>
<div class="steps"><div class="on">1 · Konto &amp; Domain</div><div>2 · Einrichtung</div><div>3 · Fertig</div></div>
<form method="post" action="/setup">
 <div class="field"><label for="username">Admin-Benutzer</label>
  <input id="username" name="username" type="text" value="admin" required autocomplete="username"
   autocapitalize="none" autocorrect="off" spellcheck="false"></div>
 <div class="field"><label for="password">Passwort</label>
  <input id="password" name="password" type="password" required minlength="10"
   autocomplete="new-password" autocapitalize="none" autocorrect="off" spellcheck="false">
  <p class="help">Mindestens 10 Zeichen.</p></div>
 <div class="field"><label for="domain">Verwaltungs-Domain</label>
  <input id="domain" name="domain" placeholder="example.com" required>
  <p class="help">Der A-Record (@) dieser Domain muss auf diesen Server zeigen{f' ({ui.esc(server_ip)})' if server_ip else ''}.</p></div>
 <button class="btn primary" type="submit" style="width:100%">Einrichtung starten</button>
</form></div></div>"""
        self._send(ui.bare("Einrichten", body))

    def do_setup(self, form):
        if store.is_setup_done():
            return self._redirect("/login")
        username = (form.get("username") or "").strip()
        password = form.get("password") or ""
        domain = (form.get("domain") or "").strip().lower().lstrip("@.")
        if not username or len(password) < 10 or not domain:
            return self._redirect("/setup", ("err", "Bitte alle Pflichtfelder korrekt ausfüllen."))
        run_setup(username, password, domain)
        return self._redirect("/setup/progress")

    def page_setup_progress(self):
        body = """<div class="box"><div class="card">
<h1>Einrichtung läuft</h1>
<p class="sub" id="step">Bitte warten …</p>
<div class="steps"><div class="done">1 · Konto &amp; Domain</div><div class="on">2 · Einrichtung</div><div>3 · Fertig</div></div>
<div class="progress"><i id="bar"></i></div>
<p class="help" id="pct">0 %</p>
<div id="err"></div>
</div></div>
<script>
(function(){
 function tick(){
  fetch('/api/setup/status').then(function(r){return r.json()}).then(function(s){
   document.getElementById('bar').style.width=(s.percent||0)+'%';
   document.getElementById('pct').textContent=(s.percent||0)+' %';
   if(s.step)document.getElementById('step').textContent=s.step;
   if(s.error){document.getElementById('err').innerHTML=
     '<div class="msg err">'+s.error+'</div>';return;}
   if(s.done){document.getElementById('step').textContent='Fertig — weiter zur Anmeldung.';
     setTimeout(function(){location.href='/login'},900);return;}
   setTimeout(tick,900);
  }).catch(function(){setTimeout(tick,1500)});
 } tick();})();
</script>"""
        self._send(ui.bare("Einrichtung", body))

    def page_login(self):
        if not store.is_setup_done():
            return self._redirect("/setup")
        flash = self._take_flash()
        msg = f'<div class="msg {ui.esc(flash[0])}">{ui.esc(flash[1])}</div>' if flash else ""
        domain = store.get_setting("manage_domain", "")
        body = f"""<div class="box"><div class="card">
<h1>Anmelden</h1><p class="sub">{ui.esc(domain) or 'weblab'}</p>{msg}
<form method="post" action="/login" id="loginform" name="loginform" autocomplete="on">
 <div class="field"><label for="username">Benutzer</label>
  <input id="username" name="username" type="text" required autocomplete="username"
   autocapitalize="none" autocorrect="off" spellcheck="false" autofocus></div>
 <div class="field"><label for="password">Passwort</label>
  <input id="password" name="password" type="password" required
   autocomplete="current-password" autocapitalize="none" autocorrect="off" spellcheck="false"></div>
 <button class="btn primary" type="submit" style="width:100%">Anmelden</button>
</form></div></div>"""
        self._send(ui.bare("Anmelden", body),
                   headers={"Set-Cookie": "weblab_flash=; Path=/; Max-Age=0"})

    def do_login(self, form):
        user = store.verify_user((form.get("username") or "").strip(), form.get("password") or "")
        if not user:
            time.sleep(1)
            return self._redirect("/login", ("err", "Benutzer oder Passwort falsch."))
        payload = {"user": user["username"], "uid": user["id"],
                   "sid": secrets.token_hex(8), "exp": time.time() + SESSION_MAX_AGE}
        cookie = (f"{COOKIE}={sign_session(payload)}; Path=/; Max-Age={SESSION_MAX_AGE}; "
                  f"HttpOnly; SameSite=Strict")
        if self.headers.get("X-Forwarded-Proto") == "https":
            cookie += "; Secure"
        return self._send("", 303, "text/plain", {"Location": "/", "Set-Cookie": cookie})

    # Dashboard
    def collect_stats(self):
        overview = sysinfo.overview()
        container_stats = dockerctl.stats() if dockerctl.available() else {}
        rows = []
        for app in store.list_apps():
            usage = container_stats.get(app["slug"], {})
            rows.append({"slug": app["slug"], "name": app["name"],
                         "state": dockerctl.status(app["slug"]),
                         "cpu": usage.get("cpu", "—"), "mem": usage.get("mem", "—"),
                         "net": usage.get("net", "—")})
        return {"system": overview, "apps": rows}

    def page_dashboard(self):
        info = sysinfo.overview()
        app_list = store.list_apps()
        stats = dockerctl.stats() if dockerctl.available() else {}
        domain = store.get_setting("manage_domain", "")
        running = sum(1 for a in app_list if dockerctl.status(a["slug"]) == "running")

        cards = "".join([
            ui.stat("CPU", f"{info['cpu_percent']} %", info["cpu_percent"],
                    f"{info['cpu_count']} Kerne · Last {info['load'][0]:.2f}"),
            ui.stat("Arbeitsspeicher", f"{info['mem']['percent']} %", info["mem"]["percent"],
                    f"{sysinfo.human_bytes(info['mem']['used'])} von {sysinfo.human_bytes(info['mem']['total'])}"),
            ui.stat("Speicherplatz", f"{info['disk']['percent']} %", info["disk"]["percent"],
                    f"{sysinfo.human_bytes(info['disk']['free'])} frei"),
            ui.stat("Apps", f"{running}/{len(app_list)}", None, "laufend / installiert"),
        ])

        rows = ""
        for app in app_list:
            usage = stats.get(app["slug"], {})
            state = dockerctl.status(app["slug"])
            if app["domain"]:
                target = f"<a href='https://{ui.esc(app['domain'])}'>{ui.esc(app['domain'])}</a>"
            else:
                target = f"<span class='mono'>Port {ui.esc(app['host_port'])}</span>"
            rows += (f"<tr><td><a href='/apps/{app['id']}'><b>{ui.esc(app['name'])}</b></a></td>"
                     f"<td>{ui.status_pill(state)}</td>"
                     f"<td class='mono'>{ui.esc(usage.get('cpu', '—'))}</td>"
                     f"<td class='mono'>{ui.esc(usage.get('mem', '—'))}</td>"
                     f"<td>{target}</td></tr>")
        if not rows:
            rows = ("<tr><td colspan='5' class='muted'>Noch keine App installiert — "
                    "<a href='/apps'>zum Katalog</a>.</td></tr>")

        body = f"""<h1>Dashboard</h1>
<p class="sub">Läuft seit {ui.esc(sysinfo.human_uptime(info['uptime']))}</p>
<div class="grid g4">{cards}</div>
<h2>Apps</h2>
<div class="card"><div class="tbl-wrap"><table>
<tr><th>App</th><th>Status</th><th>CPU</th><th>Speicher</th><th>Erreichbar über</th></tr>
{rows}</table></div></div>"""
        self._render("Dashboard", body, "/")

    # Apps: Katalog + Liste
    def page_apps(self):
        installed = store.list_apps()
        news = connector_news()
        latest = {g["group"]: g["latest"] for g in catalog.groups()}
        rows = ""
        for app in installed:
            state = dockerctl.status(app["slug"])
            link = (f"<a href='https://{ui.esc(app['domain'])}'>{ui.esc(app['domain'])}</a>"
                    if app["domain"] else f"<span class='mono'>Port {ui.esc(app['host_port'])}</span>")
            top = latest.get(app["group_id"]) or {}
            upd = (' <span class="badge">Update</span>'
                   if top.get("version") and top["version"] != app["version"] else "")
            rows += (f"<tr><td><a href='/apps/{app['id']}'><b>{ui.esc(app['name'])}</b></a></td>"
                     f"<td>{ui.status_pill(state)}</td>"
                     f"<td class='mono'>{ui.esc(app['version'])}{upd}</td>"
                     f"<td>{link}</td>"
                     f"<td><a class='btn sm' href='/apps/{app['id']}/edit'>Einstellungen</a></td></tr>")
        installed_html = (f"<div class='card'><div class='tbl-wrap'><table>"
                          f"<tr><th>Name</th><th>Status</th><th>Version</th><th>Erreichbar</th>"
                          f"<th></th></tr>{rows}</table></div></div>"
                          if rows else
                          "<div class='card muted'>Noch nichts installiert.</div>")

        tiles = ""
        for group in catalog.groups():
            is_new = any(v["id"] in news for v in group["versions"])
            tag = ' <span class="badge">neu</span>' if is_new else ""
            tiles += f"""<div class="appcard">
<div class="row" style="flex-wrap:nowrap"><span class="ico">{ui.esc(group['icon'])}</span>
<div style="min-width:0"><div class="nm">{ui.esc(group['name'])}{tag}</div>
<div class="help" style="margin:1px 0 0">{ui.esc(group['category'])}</div></div></div>
<div class="sm">{ui.esc(group['summary'])}</div>
<a class="btn primary" href="/apps/catalog/{ui.esc(group['group'])}">Installieren</a></div>"""
        if not tiles:
            tiles = "<div class='card muted'>Keine Apps gefunden.</div>"
        count = sum(1 for g in catalog.groups() if any(v["id"] in news for v in g["versions"]))
        news_tag = f' <span class="badge">{count} neu</span>' if count else ""

        body = f"""<h1>Apps</h1>
<h2>Installiert</h2>{installed_html}
<h2>Katalog{news_tag}</h2>
<div class="apps">{tiles}</div>"""
        self._render("Apps", body, "/apps")

    def _domain_field(self, current="", placeholder=""):
        """Domain: mit DNS-Konto Domain auswählen, Subdomain optional. Sonst Freitext."""
        zones = integrations.all_zones(store.cf_accounts())
        if not zones:
            return (f'<div class="field"><label for="domain">Domain</label>'
                    f'<input id="domain" name="domain" value="{ui.esc(current)}" '
                    f'placeholder="{ui.esc(placeholder)}"'
                    f'{ui._info_attr("Ohne DNS-Konto den Eintrag selbst setzen.")}></div>')
        zone_names = [z["name"] for z in zones]
        sub, sel_zone, matched = "", zone_names[0], False
        for z in sorted(zone_names, key=len, reverse=True):
            if current == z:
                sub, sel_zone, matched = "", z, True
                break
            if current.endswith("." + z):
                sub, sel_zone, matched = current[: -(len(z) + 1)], z, True
                break
        # Bestehende Domain außerhalb der verknüpften Zonen behalten.
        extra = ""
        if current and not matched:
            sel_zone = current
            extra = f'<option value="{ui.esc(current)}" selected>{ui.esc(current)}</option>'
        zone_opts = extra + "".join(
            f'<option value="{ui.esc(z)}"{" selected" if z == sel_zone else ""}>{ui.esc(z)}</option>'
            for z in zone_names)
        return (f'<div class="field" data-domain-widget>'
                f'<label for="domain_zone">Domain</label>'
                f'<select id="domain_zone" data-domain-zone'
                f'{ui._info_attr("Domains deiner verbundenen DNS-Konten.")}>{zone_opts}</select>'
                f'<div class="row" style="margin-top:8px">'
                f'<input class="sub-in" id="domain_sub" data-domain-sub value="{ui.esc(sub)}" '
                f'placeholder="Subdomain (optional)"'
                f'{ui._info_attr("Leer = Hauptdomain.")}>'
                f'<span class="muted mono" data-domain-preview></span></div>'
                f'<input type="hidden" name="domain" data-domain-out value="{ui.esc(current)}">'
                f'</div>')

    def _exposure_field(self, current):
        opts = ["external", "internal", "specific"]
        labels = {"external": "Extern (öffentlich)", "internal": "Intern (nur Server)",
                  "specific": "Spezifisch (nur erlaubte IPs)"}
        if current == "tailscale" or vpn.ts_status().get("connected"):
            opts.append("tailscale")
            labels["tailscale"] = "Tailscale (privat)"
        return ui.select_field(
            "exposure", "Erreichbarkeit", opts, current,
            "Intern = nur dieser Server. Spezifisch = nur erlaubte IPs. "
            "Tailscale = nur im privaten VPN.", labels)

    def _egress_field(self, current):
        egresses = store.vpn_egress()
        if not egresses and not current:
            return ""  # nichts konfiguriert -> Feld weglassen
        opts = [""] + [e["id"] for e in egresses]
        labels = {"": "Kein (direkt)"}
        for e in egresses:
            labels[e["id"]] = f'{e["label"]} ({e["provider"]})'
        return ui.select_field(
            "egress_id", "Ausgang über VPN", opts, current,
            "Leitet den ausgehenden Verkehr dieser App durch den gewählten VPN-Ausgang "
            "(Mullvad/Proton).", labels)

    def page_catalog_detail(self, group_id):
        group = catalog.get_group(group_id)
        if not group:
            return self._redirect("/apps", ("err", "Unbekannte App."))
        selected_id = self._query().get("version") or group["latest"]["id"]
        connector = catalog.get(selected_id) or group["latest"]

        version_options = "".join(
            f'<option value="{ui.esc(v["id"])}"{" selected" if v["id"] == connector["id"] else ""}>'
            f'{ui.esc(v["version"])}</option>' for v in group["versions"])

        required_html = "".join(
            ui.field_input(f, f.get("default", "")) for f in connector["fields"].get("required", []))

        locations = sysinfo.data_locations()
        loc_options = "".join(
            f'<option value="{ui.esc(l["path"])}">{ui.esc(l["mount"])} · '
            f'{ui.esc(sysinfo.human_bytes(l["free"]))} frei</option>' for l in locations)
        networks = [n["Name"] for n in dockerctl.networks()] if dockerctl.available() else ["bridge"]
        net_options = "".join(
            f'<option value="{ui.esc(n)}"{" selected" if n == "bridge" else ""}>{ui.esc(n)}</option>'
            for n in networks)
        exposure_default = connector.get("default_exposure", "external")

        manage_field = ""
        if connector.get("manage_subdomain"):
            default_mh = (f"{connector['manage_subdomain']}."
                          f"{store.get_setting('manage_domain', 'example.com')}")
            manage_field = (
                f'<div class="field"><label for="manage_host">Verwaltungs-Adresse</label>'
                f'<input id="manage_host" name="manage_host" value="{ui.esc(default_mh)}"'
                f'{ui._info_attr("Eigenes Dashboard + Dateimanager dieser App unter dieser Adresse. Die Seite selbst läuft unter der Domain darüber.")}>'
                f'</div>')

        body = f"""<a href="/apps" class="muted">← Katalog</a>
<h1>{ui.esc(group['icon'])} {ui.esc(group['name'])}</h1>
<p class="sub">{ui.esc(group['summary'])}</p>
<form method="post" action="/apps/install">
{ui.csrf_input(self.csrf)}
<div class="grid g2">
 <div class="card"><h3>App</h3>
  <div class="field"><label for="connector_id">Version</label>
   <select id="connector_id" name="connector_id"
    onchange="location.href='/apps/catalog/{ui.esc(group_id)}?version='+this.value">{version_options}</select>
</div>
  {required_html}
 </div>
 <div class="card"><h3>Basis</h3>
  <div class="field"><label for="name">Name</label>
   <input id="name" name="name" value="{ui.esc(group['name'])}" required></div>
  {self._domain_field('', f"app.{store.get_setting('manage_domain', 'example.com')}")}
  {manage_field}
  {self._exposure_field(exposure_default)}
  <div class="field" data-depends='{{"exposure":"specific"}}'>
   <label for="allow_cidr">Erlaubte IPs/CIDR</label>
   <input id="allow_cidr" name="allow_cidr" placeholder="203.0.113.5/32"></div>
  {self._egress_field('')}
 </div>
</div>
{ui.section("Erweitert", f'''
<div class="field"><label for="host_port">Port <span class="muted">leer = automatisch</span></label>
 <input id="host_port" name="host_port" type="number" min="1" max="65535"></div>
{ui.select_field('location', 'Ablageort', ['docker', 'device'], 'docker', '',
                 {'docker': 'Docker (Container)', 'device': 'Auf dem Gerät (Host)'})}
<div class="field"><label for="data_path">Datenlaufwerk</label>
 <select id="data_path" name="data_path">{loc_options}</select></div>
<div class="field"><label for="network">Netzwerk / Subnetz</label>
 <select id="network" name="network">{net_options}</select></div>
<div class="row"><div class="field" style="flex:1"><label for="cpu">CPU (Kerne)</label>
 <input id="cpu" name="cpu" type="number" step="0.1" min="0.1" value="1"></div>
 <div class="field" style="flex:1"><label for="ram_mb">RAM (MB)</label>
 <input id="ram_mb" name="ram_mb" type="number" min="128" value="1024"></div></div>''')}
<div class="row" style="margin-top:16px"><button class="btn primary" type="submit">App installieren</button>
<a class="btn" href="/apps">Abbrechen</a></div>
</form>{ui.DEPENDS_JS}"""
        self._render(group["name"], body, "/apps")

    def do_install(self, form):
        try:
            app = appsvc.install(form.get("connector_id", ""), form)
        except Exception as exc:  # noqa: BLE001
            return self._redirect(f"/apps/catalog/{form.get('group', '')}" if form.get("group")
                                  else "/apps", ("err", f"Installation fehlgeschlagen: {exc}"))
        warnings = app.get("warnings") or []
        note = f"{app['name']} wurde installiert."
        dns_done = app.get("dns_done") or []
        if dns_done:
            note += f" DNS gesetzt: {', '.join(dns_done)}."
        if warnings:
            note += " Hinweise: " + "; ".join(warnings)
        return self._redirect(f"/apps/{app['id']}", ("ok", note))

    # App-Detail, Einstellungen, Aktionen
    def _app_and_connector(self, app_id):
        app = store.get_app(app_id)
        if not app:
            return None, None
        return app, catalog.get(app["connector_id"])

    def _app_tabs(self, app, active):
        connector = catalog.get(app["connector_id"]) or {}
        items = [("Übersicht", f"/apps/{app['id']}")]
        if connector.get("manage_subdomain"):  # Dateimanager nur bei Seiten/Diensten
            items.append(("Dateien", f"/apps/{app['id']}/files"))
        items += [("Einstellungen", f"/apps/{app['id']}/edit"),
                  ("Protokoll", f"/apps/{app['id']}/logs")]
        return '<div class="tabs">' + "".join(
            f'<a class="{"on" if label == active else ""}" href="{href}">{label}</a>'
            for label, href in items) + "</div>"

    def page_app_detail(self, app_id):
        app, connector = self._app_and_connector(app_id)
        if not app:
            return self._redirect("/apps", ("err", "App nicht gefunden."))
        state = dockerctl.status(app["slug"])
        usage = dockerctl.stats().get(app["slug"], {}) if dockerctl.available() else {}
        url = f"https://{app['domain']}" if app["domain"] and connector and connector.get("http") \
            else f"{store.get_setting('server_ip', '')}:{app['host_port']}"
        actions = f"""<form method="post" action="/apps/{app['id']}/action" class="row">
{ui.csrf_input(self.csrf)}
<button class="btn" name="action" value="start">Starten</button>
<button class="btn" name="action" value="restart">Neu starten</button>
<button class="btn" name="action" value="stop">Stoppen</button>
<button class="btn danger" name="action" value="delete"
 onclick="return confirm('App „{ui.esc(app['name'])}“ wirklich entfernen?')">Entfernen</button>
<label class="check" style="margin-left:6px"><input type="checkbox" name="delete_data" value="1">
<span class="help" style="margin:0">Daten mitlöschen</span></label>
</form>"""
        secrets_html = ""
        if connector:
            rows = ""
            for field in catalog.all_fields(connector):
                if field.get("type") != "password":
                    continue
                value = app["values"].get(field["key"], "")
                if not value:
                    continue
                rows += (f"<tr><td>{ui.esc(field.get('label', field['key']))}</td>"
                         f"<td><code class='mono'>{ui.esc(value)}</code></td></tr>")
            for note in connector.get("notes") or []:
                rows += f"<tr><td colspan='2' class='help'>ℹ {ui.esc(note)}</td></tr>"
            if rows:
                secrets_html = (f"<h2>Zugangsdaten &amp; Hinweise</h2>"
                                f"<div class='card'><div class='tbl-wrap'><table>{rows}</table></div>"
                                f"<p class='help'>Nur hier sichtbar — bitte notieren.</p></div>")

        body = f"""<a href="/apps" class="muted">← Apps</a>
<div class="between"><div><h1>{ui.esc(app['name'])}</h1>
<p class="sub">{ui.esc(connector['name'] if connector else app['connector_id'])} · Version {ui.esc(app['version'])}</p></div>
<div>{ui.status_pill(state)}</div></div>
{self._app_tabs(app, 'Übersicht')}
<div class="grid g3">
{ui.stat('CPU', usage.get('cpu', '—'), None, 'Limit: ' + str(app['cpu']) + ' Kerne')}
{ui.stat('Speicher', usage.get('mem', '—') or '—', None, 'Limit: ' + str(app['ram_mb']) + ' MB')}
{ui.stat('Netzwerk', usage.get('net', '—') or '—', None, ui.esc(app['network']))}
</div>
<div class="card"><dl class="kv">
<dt>Erreichbar über</dt><dd class="mono">{ui.esc(url)}</dd>
{f'<dt>Verwaltung</dt><dd class="mono"><a href="https://{ui.esc(app["manage_host"])}">{ui.esc(app["manage_host"])}</a></dd>' if app.get('manage_host') else ''}
<dt>Sichtbarkeit</dt><dd>{ui.esc(EXPOSURE_LABELS.get(app['exposure'], app['exposure']))}</dd>
</dl></div>
{secrets_html}
<div class="card" style="margin-top:13px">{actions}</div>
{ui.section("Details", f'''<dl class="kv">
<dt>Port</dt><dd class="mono">{ui.esc(app['host_port'])} → {ui.esc(app['container_port'])}</dd>
<dt>Ablageort</dt><dd>{ui.esc(LOCATION_LABELS.get(app['location'], app['location']))}</dd>
<dt>Datenpfad</dt><dd class="mono">{ui.esc(appsvc.host_data_path(app, app['data_path']))}</dd>
<dt>Container</dt><dd class="mono">{ui.esc(dockerctl.container_name(app['slug']))}</dd>
</dl>''')}"""
        self._render(app["name"], body, "/apps")

    def page_app_logs(self, app_id):
        app, _ = self._app_and_connector(app_id)
        if not app:
            return self._redirect("/apps", ("err", "App nicht gefunden."))
        log_text = dockerctl.logs(app["slug"], 300) if dockerctl.available() else "Docker nicht verfügbar."
        body = (f'<a href="/apps" class="muted">← Apps</a><h1>{ui.esc(app["name"])}</h1>'
                f'<p class="sub">Protokoll (letzte 300 Zeilen)</p>'
                f'{self._app_tabs(app, "Protokoll")}'
                f'<div class="card"><pre>{ui.esc(log_text) or "— leer —"}</pre></div>')
        self._render(app["name"], body, "/apps")

    def page_app_edit(self, app_id):
        app, connector = self._app_and_connector(app_id)
        if not app or not connector:
            return self._redirect("/apps", ("err", "App oder Connector nicht gefunden."))
        section = self._query().get("section", "basic")
        values = app["values"]

        sub_tabs = ""
        has_advanced = bool(appsvc.plugin_config(connector).get("enabled"))
        for key, label in [("basic", "Basis"), ("specific", "Spezifisch")] + \
                          ([("advanced", appsvc.plugin_config(connector).get("label", "Erweitert"))]
                           if has_advanced else []):
            sub_tabs += (f'<a class="{"on" if section == key else ""}" '
                         f'href="/apps/{app["id"]}/edit?section={key}">{ui.esc(label)}</a>')
        sub_tabs = f'<div class="tabs">{sub_tabs}</div>'

        if section == "specific":
            fields = connector["fields"].get("specific", [])
            inner = "".join(ui.field_input(f, values.get(f["key"], f.get("default", "")))
                            for f in fields) or \
                "<p class='muted'>Diese App hat keine spezifischen Einstellungen.</p>"
            content = f"""<form method="post" action="/apps/{app['id']}/edit?section=specific">
{ui.csrf_input(self.csrf)}<input type="hidden" name="section" value="specific">
<div class="card"><h3>App-spezifische Einstellungen</h3>
{inner}
<button class="btn primary" type="submit">Speichern</button></div></form>"""
        elif section == "advanced" and has_advanced:
            content = self._plugins_section(app, connector)
        else:
            locations = sysinfo.data_locations()
            loc_paths = [l["path"] for l in locations]
            if app["data_path"] not in loc_paths:
                loc_paths.append(app["data_path"])
            loc_labels = {l["path"]: f'{l["mount"]} · {sysinfo.human_bytes(l["free"])} frei'
                          for l in locations}
            loc_labels.setdefault(app["data_path"], app["data_path"])
            networks = [n["Name"] for n in dockerctl.networks()] if dockerctl.available() else ["bridge"]
            if app["network"] not in networks:
                networks.append(app["network"])
            content = f"""<form method="post" action="/apps/{app['id']}/edit?section=basic">
{ui.csrf_input(self.csrf)}<input type="hidden" name="section" value="basic">
<div class="card">
{ui.readonly_field('Version', app['version'], 'nur bei Installation wählbar')}
<div class="field"><label for="name">Name</label>
 <input id="name" name="name" value="{ui.esc(app['name'])}" required></div>
{self._domain_field(app['domain'])}
{(f'<div class="field"><label for="manage_host">Verwaltungs-Adresse</label>'
  f'<input id="manage_host" name="manage_host" value="{ui.esc(app.get("manage_host",""))}"'
  f'{ui._info_attr("Dashboard + Dateimanager dieser App. Die Seite selbst läuft unter der Domain darüber.")}></div>')
  if connector.get('manage_subdomain') else ''}
{self._exposure_field(app['exposure'])}
<div class="field" data-depends='{{"exposure":"specific"}}'>
 <label for="allow_cidr">Erlaubte IPs/CIDR</label>
 <input id="allow_cidr" name="allow_cidr" value="{ui.esc(app['allow_cidr'])}"></div>
{self._egress_field(app.get('egress_id',''))}
<button class="btn primary" type="submit">Speichern</button></div>
{ui.section("Erweitert", f'''<p class="help" style="margin:0 0 12px">Rot = erst freischalten.</p>
<div class="field"><label for="host_port">Port</label>
 <input id="host_port" name="host_port" type="number" value="{ui.esc(app['host_port'])}"></div>
{ui.select_field('location', 'Ablageort', ['docker', 'device'], app['location'],
                 'Wechsel setzt die App neu auf.',
                 {'docker': 'Docker (Container)', 'device': 'Auf dem Gerät (Host)'}, locked=True)}
{ui.select_field('data_path', 'Datenlaufwerk', loc_paths, app['data_path'],
                 'Anderes Laufwerk = App wird mit leeren Daten neu aufgesetzt.',
                 loc_labels, locked=True)}
{ui.select_field('network', 'Netzwerk / Subnetz', networks, app['network'], '',
                 {n: n for n in networks})}
<div class="row"><div class="field" style="flex:1"><label for="cpu">CPU (Kerne)</label>
 <input id="cpu" name="cpu" type="number" step="0.1" min="0.1" value="{ui.esc(app['cpu'])}"></div>
<div class="field" style="flex:1"><label for="ram_mb">RAM (MB)</label>
 <input id="ram_mb" name="ram_mb" type="number" min="128" value="{ui.esc(app['ram_mb'])}"></div></div>''')}
</form>"""

        body = (f'<a href="/apps/{app["id"]}" class="muted">← {ui.esc(app["name"])}</a>'
                f'<h1>Einstellungen</h1><p class="sub">{ui.esc(app["name"])} · '
                f'{ui.esc(connector["name"])} {ui.esc(app["version"])}</p>'
                f'{self._app_tabs(app, "Einstellungen")}{sub_tabs}{content}{ui.DEPENDS_JS}')
        self._render(f"{app['name']} — Einstellungen", body, "/apps")

    def _plugins_section(self, app, connector):
        config = appsvc.plugin_config(connector)
        query = self._query()
        term = query.get("q", "")
        source = query.get("source") or (config.get("sources") or [{}])[0].get("id", "modrinth")

        source_options = "".join(
            f'<option value="{ui.esc(s["id"])}"{" selected" if s["id"] == source else ""}>'
            f'{ui.esc(s["name"])}</option>' for s in config.get("sources", []))

        results_html = ""
        if term:
            source_cfg = next((s for s in config.get("sources", []) if s["id"] == source), {})
            try:
                hits = integrations.search_plugins(
                    source, term, source_cfg.get("loader"), source_cfg.get("game_versions"))
            except Exception as exc:  # noqa: BLE001
                hits = []
                results_html = f'<div class="msg err">Suche fehlgeschlagen: {ui.esc(exc)}</div>'
            rows = ""
            for hit in hits:
                rows += f"""<tr><td><b>{ui.esc(hit['name'])}</b>
<div class="help">{ui.esc(hit['summary'])}</div></td>
<td class="mono">{hit['downloads']:,}</td>
<td><form method="post" action="/apps/{app['id']}/plugins">
{ui.csrf_input(self.csrf)}<input type="hidden" name="action" value="add">
<input type="hidden" name="source" value="{ui.esc(hit['source'])}">
<input type="hidden" name="project_id" value="{ui.esc(hit['id'])}">
<button class="btn sm primary" type="submit">Hinzufügen</button></form></td></tr>"""
            if rows:
                results_html += (f'<div class="tbl-wrap"><table><tr><th>Plugin</th>'
                                 f'<th>Downloads</th><th></th></tr>{rows}</table></div>')
            elif not results_html:
                results_html = '<p class="muted">Keine Treffer.</p>'

        installed = appsvc.list_plugins(app, connector) if dockerctl.available() else []
        inst_rows = ""
        for plugin in installed:
            inst_rows += f"""<tr><td class="mono">{ui.esc(plugin['name'])}</td>
<td class="mono">{ui.esc(sysinfo.human_bytes(plugin['size']))}</td>
<td><form method="post" action="/apps/{app['id']}/plugins">
{ui.csrf_input(self.csrf)}<input type="hidden" name="action" value="delete">
<input type="hidden" name="filename" value="{ui.esc(plugin['name'])}">
<button class="btn sm danger" type="submit"
 onclick="return confirm('{ui.esc(plugin['name'])} löschen?')">Löschen</button></form></td></tr>"""
        if not inst_rows:
            inst_rows = "<tr><td colspan='3' class='muted'>Noch keine Plugins installiert.</td></tr>"

        return f"""<div class="card"><h3>{ui.esc(config.get('label', 'Plugins'))} suchen</h3>
<p class="help" style="margin-bottom:12px">Nach jeder Änderung startet die App neu.</p>
<form method="get" action="/apps/{app['id']}/edit" class="row" style="margin-bottom:14px">
<input type="hidden" name="section" value="advanced">
<select name="source" style="max-width:190px">{source_options}</select>
<input name="q" value="{ui.esc(term)}" placeholder="z. B. EssentialsX" style="flex:1;min-width:200px">
<button class="btn primary" type="submit">Suchen</button></form>
{results_html}</div>
<div class="card" style="margin-top:14px"><h3>Installierte {ui.esc(config.get('label', 'Plugins'))}</h3>
<div class="tbl-wrap"><table><tr><th>Datei</th><th>Größe</th><th></th></tr>{inst_rows}</table></div></div>"""

    def do_app_edit(self, app_id, form):
        section = form.get("section", "basic")
        try:
            appsvc.update(app_id, form, section)
        except Exception as exc:  # noqa: BLE001
            return self._redirect(f"/apps/{app_id}/edit?section={section}",
                                  ("err", f"Speichern fehlgeschlagen: {exc}"))
        return self._redirect(f"/apps/{app_id}/edit?section={section}",
                              ("ok", "Einstellungen gespeichert."))

    def do_app_action(self, app_id, form):
        action = form.get("action", "")
        app = store.get_app(app_id)
        if not app:
            return self._redirect("/apps", ("err", "App nicht gefunden."))
        try:
            if action == "start":
                dockerctl.start(app["slug"])
            elif action == "stop":
                dockerctl.stop(app["slug"])
            elif action == "restart":
                dockerctl.restart(app["slug"])
            elif action == "delete":
                appsvc.remove(app_id, delete_data=form.get("delete_data") == "1")
                return self._redirect("/apps", ("ok", f"{app['name']} wurde entfernt."))
        except Exception as exc:  # noqa: BLE001
            return self._redirect(f"/apps/{app_id}", ("err", str(exc)))
        return self._redirect(f"/apps/{app_id}", ("ok", "Aktion ausgeführt."))

    def do_plugins(self, app_id, form):
        app, connector = self._app_and_connector(app_id)
        if not app or not connector:
            return self._redirect("/apps", ("err", "App nicht gefunden."))
        target = f"/apps/{app_id}/edit?section=advanced"
        try:
            if form.get("action") == "add":
                name = appsvc.add_plugin(app, connector, form.get("source", ""),
                                         form.get("project_id", ""))
                return self._redirect(target, ("ok", f"{name} hinzugefügt."))
            if form.get("action") == "delete":
                appsvc.delete_plugin(app, connector, form.get("filename", ""))
                return self._redirect(target, ("ok", "Plugin gelöscht."))
        except Exception as exc:  # noqa: BLE001
            return self._redirect(target, ("err", str(exc)))
        return self._redirect(target)

    # Netzwerk / DNS / Speicher / Benutzer / Einstellungen
    def _cloudflare_block(self):
        accounts = store.cf_accounts()
        connect = ui.open_button("cfDialog", "＋ DNS-Konto verbinden",
                                 "btn primary" if not accounts else "btn")
        if accounts:
            rows = ""
            for acc in accounts:
                cloudflare = integrations.Cloudflare(acc["token"])
                valid, info = cloudflare.verify()
                zones = ", ".join(z["name"] for z in cloudflare.zones()) if valid else ""
                state = ('<span class="pill run"><span class="dot"></span>verknüpft</span>' if valid
                         else f'<span class="pill err"><span class="dot"></span>{ui.esc(info)}</span>')
                zones_html = (f'<p class="help" style="margin:4px 0 0">Domains: '
                              f'<span class="mono">{ui.esc(zones)}</span></p>' if zones else "")
                rows += f"""<div class="between acctrow">
<div>{state} &nbsp;<span class="mono">{ui.esc(acc['label'])}</span>{zones_html}</div>
<form method="post" action="/network">{ui.csrf_input(self.csrf)}
<input type="hidden" name="action" value="cf_unlink">
<input type="hidden" name="account_id" value="{ui.esc(acc['id'])}">
<button class="btn sm danger" type="submit"
 onclick="return confirm('Verknüpfung wirklich lösen?')">Lösen</button></form></div>"""
            head = (f'<div class="between" style="margin-bottom:12px">'
                    f'<span class="muted">Verbundene DNS-Konten</span>{connect}</div>{rows}')
        else:
            head = (f'<div class="between"><div><p class="help" style="margin:0">Noch kein DNS-Konto '
                    f'verbunden. Danach legt weblab die Einträge je App automatisch an.</p></div>'
                    f'{connect}</div>')
        return head + self._cf_dialog()

    def _cf_dialog(self):
        domain = store.get_setting("manage_domain", "")
        client_id = store.get_setting("cf_client_id", "")
        redirect_uri = (f"https://{domain}/network/cloudflare/callback" if domain
                        else "https://<deine-domain>/network/cloudflare/callback")
        other = f"""<form method="post" action="/network">{ui.csrf_input(self.csrf)}
<input type="hidden" name="action" value="cf_link">
<div class="field"><label for="cf_email">Konto-E-Mail</label>
 <input id="cf_email" name="cf_email" type="email" required autocomplete="off"></div>
<div class="field"><label for="cf_key">Global API Key</label>
 <input id="cf_key" name="cf_key" type="password" required autocomplete="off">
 <p class="help">Wird nicht gespeichert — weblab erzeugt daraus einen Token nur für DNS.</p></div>
<button class="btn" type="submit">Verbinden</button></form>
<hr style="border:0;border-top:1px solid var(--line);margin:16px 0">
<form method="post" action="/network">{ui.csrf_input(self.csrf)}
<input type="hidden" name="action" value="cf_oauth">
<div class="field"><label for="cf_client_id">OAuth-Client-ID</label>
 <input id="cf_client_id" name="cf_client_id" value="{ui.esc(client_id)}" required>
 <p class="help">Rückleitung: <span class="mono">{ui.esc(redirect_uri)}</span></p></div>
<div class="field"><label for="cf_client_secret">Client-Secret <span class="muted">optional</span></label>
 <input id="cf_client_secret" name="cf_client_secret" type="password" autocomplete="off"></div>
<button class="btn" type="submit">Mit Cloudflare anmelden</button></form>"""
        inner = f"""<form method="post" action="/network">{ui.csrf_input(self.csrf)}
<input type="hidden" name="action" value="cf_token">
<div class="field"><label for="cf_api_token">API-Token</label>
 <input id="cf_api_token" name="cf_api_token" type="password" required autocomplete="off"
  placeholder="Token einfügen">
 <p class="help">Cloudflare → Profil → API-Tokens → Vorlage „Zone-DNS bearbeiten“,
 alle Zonen auswählen.</p></div>
<button class="btn primary" type="submit">Verbinden</button></form>
{ui.section("Andere Wege", other)}"""
        return ui.modal("cfDialog", "DNS-Konto verbinden", inner)

    def _vpn_block(self):
        st = vpn.ts_status()
        if st.get("connected"):
            ts_html = (f'<div class="between acctrow"><div>'
                       f'<span class="pill run"><span class="dot"></span>verbunden</span> '
                       f'<span class="mono">{ui.esc(st.get("hostname"))}</span>'
                       f'<p class="help" style="margin:4px 0 0">Tailnet-IP: '
                       f'<span class="mono">{ui.esc(st.get("ip"))}</span></p></div>'
                       f'<form method="post" action="/network">{ui.csrf_input(self.csrf)}'
                       f'<input type="hidden" name="action" value="ts_down">'
                       f'<button class="btn sm danger" type="submit">Trennen</button></form></div>')
        else:
            ts_html = (f'<p class="help" style="margin:0 0 10px">Verbinden — danach sind Apps mit '
                       f'Erreichbarkeit „Tailscale (privat)" nur in deinem Tailscale-Netz erreichbar.</p>'
                       f'<form method="post" action="/network" class="row">{ui.csrf_input(self.csrf)}'
                       f'<input type="hidden" name="action" value="ts_up">'
                       f'<input name="authkey" placeholder="tskey-auth-…" required autocomplete="off" '
                       f'style="flex:1;min-width:220px">'
                       f'<button class="btn primary" type="submit">Verbinden</button></form>')
        rows = ""
        for e in store.vpn_egress():
            rows += (f'<div class="between acctrow"><div><span class="mono">{ui.esc(e["label"])}</span>'
                     f'<span class="muted"> · {ui.esc(e["provider"])}</span></div>'
                     f'<form method="post" action="/network">{ui.csrf_input(self.csrf)}'
                     f'<input type="hidden" name="action" value="egress_remove">'
                     f'<input type="hidden" name="egress_id" value="{ui.esc(e["id"])}">'
                     f'<button class="btn sm danger" type="submit" '
                     f'onclick="return confirm(\'Ausgang entfernen?\')">Entfernen</button></form></div>')
        add_btn = ui.open_button("vpnDialog", "＋ VPN-Ausgang hinzufügen", "btn")
        egress_html = (
            f'<div class="between" style="margin:16px 0 10px"><span class="muted">'
            f'Ausgehende Tunnel (Mullvad/Proton)</span>{add_btn}</div>{rows}' if rows else
            f'<div class="between" style="margin:16px 0 0"><p class="help" style="margin:0">'
            f'Ausgehende Tunnel: den Verkehr einer App durch Mullvad/Proton leiten.</p>{add_btn}</div>')
        return (f'<h3>Tailscale — privater Zugriff</h3>{ts_html}{egress_html}{self._vpn_dialog()}')

    def _vpn_dialog(self):
        inner = f"""<p class="help" style="margin-bottom:12px">WireGuard-Zugang von Mullvad oder
ProtonVPN. Privaten Schlüssel und Adresse aus der heruntergeladenen WireGuard-Konfiguration
übernehmen (der Schlüssel wird nur für diesen Ausgang gespeichert).</p>
<form method="post" action="/network">{ui.csrf_input(self.csrf)}
<input type="hidden" name="action" value="egress_add">
<div class="field"><label for="e_label">Name</label>
 <input id="e_label" name="label" placeholder="z. B. Mullvad Zürich" required></div>
{ui.select_field('provider', 'Anbieter', ['mullvad', 'protonvpn'], 'mullvad', '',
                 {'mullvad': 'Mullvad', 'protonvpn': 'ProtonVPN'})}
<div class="field"><label for="e_key">WireGuard privater Schlüssel</label>
 <input id="e_key" name="private_key" type="password" required autocomplete="off"></div>
<div class="field"><label for="e_addr">Adresse(n)</label>
 <input id="e_addr" name="addresses" placeholder="10.64.0.2/32" required autocomplete="off"></div>
<div class="field"><label for="e_loc">Standort <span class="muted">optional</span></label>
 <input id="e_loc" name="location" placeholder="z. B. Zurich"></div>
<button class="btn primary" type="submit">Hinzufügen</button></form>"""
        return ui.modal("vpnDialog", "VPN-Ausgang hinzufügen", inner)

    def _dns_records_html(self):
        accounts = store.cf_accounts()
        server_ip = store.get_setting("server_ip", "")
        zones = integrations.all_zones(accounts) if accounts else []
        if not zones:
            return ""
        sections = ""
        for zone in zones:
            rows, error = integrations.Cloudflare(zone["token"]).list_records(zone["name"])
            rr = ""
            for record in rows:
                mark = (" <span class='pill run'>dieser Server</span>"
                        if record.get("content") == server_ip else "")
                rr += (f"<tr><td class='mono'>{ui.esc(record.get('type'))}</td>"
                       f"<td class='mono'>{ui.esc(record.get('name'))}</td>"
                       f"<td class='mono'>{ui.esc(record.get('content'))}{mark}</td>"
                       f"<td>{'Proxy' if record.get('proxied') else 'DNS only'}</td>"
                       f"<td><form method='post' action='/network' style='display:inline'>"
                       f"{ui.csrf_input(self.csrf)}<input type='hidden' name='action' value='dns_delete'>"
                       f"<input type='hidden' name='zone' value=\"{ui.esc(zone['name'])}\">"
                       f"<input type='hidden' name='record_id' value=\"{ui.esc(record.get('id'))}\">"
                       f"<button class='btn sm danger' type='submit'"
                       f" onclick=\"return confirm('Eintrag löschen?')\">Löschen</button></form></td></tr>")
            if not rr:
                rr = f"<tr><td colspan='5' class='muted'>{ui.esc(error or 'Keine Einträge.')}</td></tr>"
            label = f" <span class='muted'>· {ui.esc(zone['account'])}</span>" if zone.get("account") else ""
            sections += (f"<h3 style='margin-top:18px'><span class='mono'>{ui.esc(zone['name'])}</span>{label}</h3>"
                         f"<div class='tbl-wrap'><table>"
                         f"<tr><th>Typ</th><th>Name</th><th>Ziel</th><th>Modus</th><th></th></tr>"
                         f"{rr}</table></div>")
        return (sections
                + "<p class='help'>Einträge je App (A, MX, SPF …) werden automatisch angelegt.</p>")

    def page_network(self):
        app_by_port = {a["host_port"]: a for a in store.list_apps()}
        ports = sysinfo.listening_ports()

        def port_rows(rows):
            out = ""
            for row in rows:
                app = app_by_port.get(row["port"])
                owner = (f"<a href='/apps/{app['id']}'>{ui.esc(app['name'])}</a>" if app
                         else ui.esc(row["process"] or "—"))
                out += (f"<tr><td class='mono'>{row['port']}</td><td>{ui.esc(row['proto'])}</td>"
                        f"<td>{owner}</td></tr>")
            return out or "<tr><td colspan='3' class='muted'>Keine.</td></tr>"

        def table(head, rows):
            return (f"<div class='tbl-wrap'><table><tr>"
                    + "".join(f"<th>{h}</th>" for h in head) + f"</tr>{rows}</table></div>")

        ext = table(["Port", "Protokoll", "Dienst"],
                    port_rows([r for r in ports if r["scope"] == "extern"]))
        internal = table(["Port", "Protokoll", "Dienst"],
                         port_rows([r for r in ports if r["scope"] != "extern"]))

        iface_rows = ""
        for iface in sysinfo.interfaces():
            addresses = ", ".join(f"{a['address']}/{a['prefix']}"
                                  for a in iface["addresses"]) or "—"
            iface_rows += (f"<tr><td class='mono'><b>{ui.esc(iface['name'])}</b></td>"
                           f"<td>{ui.esc(iface['state'])}</td>"
                           f"<td class='mono'>{ui.esc(addresses)}</td></tr>")
        iface_html = table(["Schnittstelle", "Status", "Adressen"],
                           iface_rows or "<tr><td colspan='3' class='muted'>—</td></tr>")

        net_rows = ""
        if dockerctl.available():
            app_networks = {}
            for app in store.list_apps():
                app_networks.setdefault(app["network"], []).append(app["name"])
            for net in dockerctl.networks():
                details = dockerctl.network_details(net["Name"])
                configs = (details.get("IPAM") or {}).get("Config") or []
                subnet = ", ".join(c.get("Subnet", "") for c in configs) or "—"
                used_by = ", ".join(app_networks.get(net["Name"], [])) or "—"
                del_btn = "" if net["Name"] in ("bridge", "host", "none") else (
                    f'<form method="post" action="/network" style="display:inline">'
                    f'{ui.csrf_input(self.csrf)}'
                    f'<input type="hidden" name="action" value="delete_network">'
                    f'<input type="hidden" name="name" value="{ui.esc(net["Name"])}">'
                    f'<button class="btn sm danger" type="submit">Löschen</button></form>')
                net_rows += (f"<tr><td class='mono'><b>{ui.esc(net['Name'])}</b></td>"
                             f"<td class='mono'>{ui.esc(subnet)}</td>"
                             f"<td>{ui.esc(used_by)}</td><td>{del_btn}</td></tr>")
        subnet_html = table(["Subnetz", "Bereich", "Genutzt von", ""],
                            net_rows or "<tr><td colspan='4' class='muted'>—</td></tr>")
        subnet_html += f"""<form method="post" action="/network" class="row" style="margin-top:14px">
{ui.csrf_input(self.csrf)}<input type="hidden" name="action" value="create_network">
<input name="name" placeholder="Name" required style="flex:1;min-width:140px">
<input name="subnet" placeholder="10.80.0.0/24" style="flex:1;min-width:140px">
<label class="check"><input type="checkbox" name="internal" value="1">
<span class="help" style="margin:0">ohne Internet</span></label>
<button class="btn" type="submit">Anlegen</button></form>"""

        body = f"""<h1>Netzwerk</h1>
<div class="card"><form method="post" action="/network" class="row">{ui.csrf_input(self.csrf)}
<input type="hidden" name="action" value="general">
<div class="field" style="flex:1;min-width:190px;margin:0"><label for="manage_domain">Domain</label>
 <input id="manage_domain" name="manage_domain" value="{ui.esc(store.get_setting('manage_domain',''))}"></div>
<div class="field" style="flex:1;min-width:160px;margin:0"><label for="server_ip">Server-IP</label>
 <input id="server_ip" name="server_ip" value="{ui.esc(store.get_setting('server_ip',''))}"></div>
<button class="btn" type="submit" style="margin-top:22px">Speichern</button></form></div>
<h2>DNS</h2>
<div class="card">{self._cloudflare_block()}</div>
{ui.section("DNS-Einträge", self._dns_records_html() or "<p class='muted'>Kein Konto verbunden.</p>")}
{ui.section("VPN", self._vpn_block())}
{ui.section("Offene Ports", ext + ui.section("Intern", internal))}
{ui.section("Erweitert", iface_html + ui.section("Subnetze", subnet_html))}"""
        self._render("Netzwerk", body, "/network")

    def do_network(self, form):
        action = form.get("action")
        try:
            if action == "create_network":
                dockerctl.create_network(form.get("name", "").strip(),
                                         form.get("subnet", "").strip() or None,
                                         internal=form.get("internal") == "1")
                return self._redirect("/network", ("ok", "Subnetz angelegt."))
            if action == "delete_network":
                dockerctl.remove_network(form.get("name", ""))
                return self._redirect("/network", ("ok", "Subnetz gelöscht."))
            if action == "dns_delete":
                zone = form.get("zone", "") or store.get_setting("manage_domain", "")
                token = integrations.token_for_host(store.cf_accounts(), zone)
                if not token:
                    return self._redirect("/network", ("err", "Kein Konto für diese Domain."))
                ok, err = integrations.Cloudflare(token).delete_record(zone, form.get("record_id", ""))
                return self._redirect("/network", ("ok", "Eintrag gelöscht.") if ok
                                      else ("err", err or "Fehler"))
            if action == "cf_oauth":
                return self._cf_oauth_start(form)
            if action == "general":
                store.set_setting("manage_domain",
                                  (form.get("manage_domain") or "").strip().lower().lstrip("@."))
                store.set_setting("server_ip",
                                  (form.get("server_ip") or "").strip() or sysinfo.public_ip())
                ok, err = appsvc.sync_proxy()
                return self._redirect("/network", ("ok", "Gespeichert.") if ok
                                      else ("err", f"Proxy: {err}"))
            if action == "cf_token":
                token = (form.get("cf_api_token") or "").strip()
                ok, info = integrations.Cloudflare(token).verify() if token else (False, "leer")
                if not ok:
                    return self._redirect("/network", ("err", f"Token ungültig: {info}"))
                store.add_cf_account("API-Token", token)
                store.set_setting("cf_status", "verknüpft")
                return self._redirect("/network", ("ok", "DNS-Konto verbunden."))
            if action == "cf_link":
                email = form.get("cf_email", "").strip()
                token, err = integrations.link_account(
                    email, form.get("cf_key", ""),
                    label=store.get_setting("manage_domain", "weblab"))
                if not token:
                    return self._redirect("/network", ("err", f"Verknüpfung fehlgeschlagen: {err}"))
                store.add_cf_account(email or "Cloudflare", token)
                store.set_setting("cf_status", "verknüpft")
                return self._redirect("/network", ("ok", "DNS-Konto verbunden."))
            if action == "cf_unlink":
                store.remove_cf_account(form.get("account_id", ""))
                if not store.cf_accounts():
                    store.set_setting("cf_status", "nicht verknüpft")
                return self._redirect("/network", ("ok", "Verknüpfung gelöst."))
            if action == "ts_up":
                authkey = (form.get("authkey") or "").strip()
                if not authkey:
                    return self._redirect("/network", ("err", "Bitte einen Tailscale-Auth-Key eingeben."))
                host = store.get_setting("manage_domain", "weblab").split(".")[0] or "weblab"
                ok, err = vpn.ts_up(authkey, hostname=host)
                if ok:
                    # Tailnet-Schnittstelle in der Firewall zulassen (privater Zugriff).
                    subprocess.run(["ufw", "allow", "in", "on", "tailscale0"],
                                   capture_output=True, text=True, timeout=15)
                    return self._redirect("/network", ("ok", "Tailscale verbunden."))
                return self._redirect("/network", ("err", f"Tailscale: {err}"))
            if action == "ts_down":
                vpn.ts_down()
                return self._redirect("/network", ("ok", "Tailscale getrennt."))
            if action == "egress_add":
                pk = (form.get("private_key") or "").strip()
                addr = (form.get("addresses") or "").strip()
                if not pk or not addr:
                    return self._redirect("/network", ("err", "Schlüssel und Adresse sind nötig."))
                store.add_vpn_egress(form.get("label", ""), form.get("provider", "mullvad"),
                                     pk, addr, (form.get("location") or "").strip())
                return self._redirect("/network", ("ok", "VPN-Ausgang hinzugefügt."))
            if action == "egress_remove":
                store.remove_vpn_egress(form.get("egress_id", ""))
                return self._redirect("/network", ("ok", "VPN-Ausgang entfernt."))
        except Exception as exc:  # noqa: BLE001
            return self._redirect("/network", ("err", str(exc)))
        return self._redirect("/network")

    def _cf_oauth_start(self, form):
        client_id = (form.get("cf_client_id") or store.get_setting("cf_client_id", "")).strip()
        if not client_id:
            return self._redirect("/network", ("err", "Bitte die OAuth-Client-ID eintragen."))
        store.set_setting("cf_client_id", client_id)
        domain = store.get_setting("manage_domain", "")
        if not domain:
            return self._redirect("/network", ("err", "Bitte zuerst die Verwaltungs-Domain setzen."))
        redirect_uri = f"https://{domain}/network/cloudflare/callback"
        verifier, challenge = integrations.pkce_pair()
        state = secrets.token_urlsafe(24)
        CF_LOGIN.update({"state": state, "verifier": verifier, "client_id": client_id,
                         "client_secret": (form.get("cf_client_secret") or "").strip(),
                         "redirect_uri": redirect_uri})
        return self._send("", 303, "text/plain",
                          {"Location": integrations.authorize_url(client_id, redirect_uri,
                                                                  state, challenge)})

    def page_storage(self):
        import subprocess
        disks = sysinfo.storage()
        default_disk = disks[0]["name"] if disks else "?"
        apps_by_disk = {}
        for app in store.list_apps():
            path = appsvc.host_data_path(app, app["data_path"])
            size = None
            try:
                out = subprocess.run(["du", "-sb", path], capture_output=True, text=True, timeout=20)
                if out.returncode == 0:
                    size = int(out.stdout.split()[0])
            except Exception:  # noqa: BLE001
                size = None
            disk = sysinfo.disk_for_path(path) or default_disk
            apps_by_disk.setdefault(disk, []).append({"app": app, "size": size})

        total_size = sum(d["size"] for d in disks)
        total_used = sum(d["used"] for d in disks)
        total_pct = round(total_used / total_size * 100, 1) if total_size else 0.0
        summary = ui.stat("Gesamtspeicher", sysinfo.human_bytes(total_size), total_pct,
                          f"{sysinfo.human_bytes(total_used)} belegt · "
                          f"{len(disks)} Laufwerk{'e' if len(disks) != 1 else ''}")

        def bar_class(pct):
            return "bad" if pct >= 90 else "warn" if pct >= 75 else "ok"

        disk_cards = ""
        for disk in disks:
            apps = apps_by_disk.get(disk["name"], [])
            app_rows = "".join(
                f"<tr><td><a href='/apps/{a['app']['id']}'>{ui.esc(a['app']['name'])}</a></td>"
                f"<td class='mono'>{ui.esc(sysinfo.human_bytes(a['size']) if a['size'] is not None else '—')}</td>"
                f"</tr>" for a in apps) or \
                "<tr><td colspan='2' class='muted'>Keine App auf diesem Laufwerk.</td></tr>"
            model = f' <span class="muted">· {ui.esc(disk["model"])}</span>' if disk["model"] else ""
            disk_cards += f"""<div class="card">
<div class="between"><h3 style="margin:0">🖴 <span class="mono">{ui.esc(disk['name'])}</span>{model}</h3>
<span class="mono">{ui.esc(sysinfo.human_bytes(disk['size']))}</span></div>
<div class="bar {bar_class(disk['percent'])}" style="margin:11px 0 4px"><i style="width:{disk['percent']:.1f}%"></i></div>
<div class="help">{disk['percent']} % belegt · {ui.esc(sysinfo.human_bytes(disk['used']))} von {ui.esc(sysinfo.human_bytes(disk['total']))}</div>
<div class="tbl-wrap"><table style="margin-top:12px">
<tr><th>App</th><th>Belegt</th></tr>{app_rows}</table></div></div>"""
        disk_cards = disk_cards or "<div class='card muted'>Keine Laufwerke erkannt.</div>"

        body = f"""<h1>Speicher</h1>

<div class="grid g4">{summary}</div>
<h2>Laufwerke</h2>{disk_cards}"""
        self._render("Speicher", body, "/storage")

    def page_users(self):
        rows = ""
        for user in store.list_users():
            created = time.strftime("%d.%m.%Y", time.localtime(user["created_at"]))
            is_me = user["username"] == (self.session or {}).get("user")
            me_badge = ' <span class="pill">du</span>' if is_me else ""
            delete_btn = "" if is_me else f"""<form method="post" action="/users">
{ui.csrf_input(self.csrf)}<input type="hidden" name="action" value="delete">
<input type="hidden" name="user_id" value="{user['id']}">
<button class="btn sm danger" type="submit"
 onclick="return confirm('Benutzer löschen?')">Löschen</button></form>"""
            rows += (f"<tr><td><b>{ui.esc(user['username'])}</b>"
                     f"{me_badge}</td>"
                     f"<td>{ui.esc(user['role'])}</td><td class='mono'>{created}</td>"
                     f"<td>{delete_btn}</td></tr>")

        body = f"""<h1>Benutzer</h1>

<div class="card"><div class="tbl-wrap"><table>
<tr><th>Benutzer</th><th>Rolle</th><th>Angelegt</th><th></th></tr>{rows}</table></div></div>
<div class="grid g2" style="margin-top:14px">
<div class="card"><h3>Benutzer anlegen</h3>
<form method="post" action="/users">{ui.csrf_input(self.csrf)}
<input type="hidden" name="action" value="create">
<div class="field"><label for="nu">Benutzername</label><input id="nu" name="username" required></div>
<div class="field"><label for="np">Passwort</label>
 <input id="np" name="password" type="password" required minlength="10"></div>
<button class="btn primary" type="submit">Anlegen</button></form></div>
<div class="card"><h3>Eigenes Passwort ändern</h3>
<form method="post" action="/users">{ui.csrf_input(self.csrf)}
<input type="hidden" name="action" value="password">
<div class="field"><label for="pw">Neues Passwort</label>
 <input id="pw" name="password" type="password" required minlength="10"></div>
<button class="btn primary" type="submit">Ändern</button></form></div></div>"""
        self._render("Benutzer", body, "/users")

    def do_users(self, form):
        action = form.get("action")
        try:
            if action == "create":
                password = form.get("password") or ""
                if len(password) < 10:
                    return self._redirect("/users", ("err", "Passwort zu kurz (min. 10 Zeichen)."))
                store.create_user((form.get("username") or "").strip(), password)
                return self._redirect("/users", ("ok", "Benutzer angelegt."))
            if action == "password":
                password = form.get("password") or ""
                if len(password) < 10:
                    return self._redirect("/users", ("err", "Passwort zu kurz (min. 10 Zeichen)."))
                store.set_password((self.session or {}).get("uid"), password)
                return self._redirect("/users", ("ok", "Passwort geändert."))
            if action == "delete":
                user_id = int(form.get("user_id") or 0)
                if user_id == (self.session or {}).get("uid"):
                    return self._redirect("/users", ("err", "Eigenes Konto nicht löschbar."))
                if store.user_count() <= 1:
                    return self._redirect("/users", ("err", "Der letzte Benutzer bleibt bestehen."))
                store.delete_user(user_id)
                return self._redirect("/users", ("ok", "Benutzer gelöscht."))
        except Exception as exc:  # noqa: BLE001
            return self._redirect("/users", ("err", str(exc)))
        return self._redirect("/users")

    # Cloudflare-Anmeldung (OAuth-Rückleitung)
    def cf_callback(self):
        query = self._query()
        if query.get("error"):
            return self._redirect("/network",
                                  ("err", f"Cloudflare: {query.get('error_description') or query['error']}"))
        if not CF_LOGIN.get("state") or query.get("state") != CF_LOGIN["state"]:
            return self._redirect("/network", ("err", "Anmeldung abgelaufen — bitte erneut starten."))
        token, err = integrations.exchange_code(
            CF_LOGIN["client_id"], CF_LOGIN["client_secret"], CF_LOGIN["redirect_uri"],
            query.get("code", ""), CF_LOGIN["verifier"])
        CF_LOGIN.update({"state": "", "verifier": "", "client_secret": ""})
        if not token:
            return self._redirect("/network", ("err", f"Anmeldung fehlgeschlagen: {err}"))
        store.add_cf_account("Cloudflare-Anmeldung", token)
        store.set_setting("cf_status", "verknüpft")
        return self._redirect("/network", ("ok", "DNS-Konto verbunden."))

    # Dateien einer App
    def _app_base(self, app):
        return appsvc.host_data_path(app, app["data_path"])

    def page_app_files(self, app_id):
        app, connector = self._app_and_connector(app_id)
        if not app:
            return self._redirect("/apps", ("err", "App nicht gefunden."))
        if not (connector or {}).get("manage_subdomain"):
            return self._redirect(f"/apps/{app_id}")
        base = self._app_base(app)
        query = self._query()
        current = query.get("p", "")
        edit_file = query.get("edit")

        if edit_file:
            try:
                content = files.read_text(base, edit_file)
            except files.FileError as exc:
                return self._redirect(f"/apps/{app_id}/files", ("err", str(exc)))
            parent = "/".join(edit_file.split("/")[:-1])
            body = f"""<a href="/apps/{app_id}/files?p={ui.esc(parent)}" class="muted">← Dateien</a>
<h1>{ui.esc(edit_file.split('/')[-1])}</h1>
<p class="sub">{ui.esc(app['name'])} · <span class="mono">{ui.esc(edit_file)}</span></p>
{self._app_tabs(app, 'Dateien')}
<form method="post" action="/apps/{app_id}/files">
{ui.csrf_input(self.csrf)}<input type="hidden" name="action" value="save">
<input type="hidden" name="path" value="{ui.esc(edit_file)}">
<div class="card"><textarea name="content" rows="24" spellcheck="false"
 style="font-family:var(--mono);font-size:13px">{ui.esc(content)}</textarea>
<div class="row" style="margin-top:12px">
<button class="btn primary" type="submit">Speichern</button>
<a class="btn" href="/apps/{app_id}/files?p={ui.esc(parent)}">Abbrechen</a></div></div></form>"""
            return self._render(f"{app['name']} — {edit_file}", body, "/apps")

        try:
            entries = files.listing(base, current)
        except files.FileError as exc:
            return self._redirect(f"/apps/{app_id}/files", ("err", str(exc)))

        crumbs = " / ".join(
            f'<a href="/apps/{app_id}/files?p={ui.esc(p)}">{ui.esc(label)}</a>'
            for label, p in files.breadcrumbs(current))

        rows = ""
        if current:
            parent = "/".join(current.split("/")[:-1])
            rows += (f'<tr><td colspan="5"><a href="/apps/{app_id}/files?p={ui.esc(parent)}">'
                     f'⬆ eine Ebene höher</a></td></tr>')
        for entry in entries:
            if entry["dir"]:
                name_html = (f'📁 <a href="/apps/{app_id}/files?p={ui.esc(entry["path"])}">'
                             f'<b>{ui.esc(entry["name"])}</b></a>')
                size = "—"
                actions = ""
            else:
                name_html = f'📄 {ui.esc(entry["name"])}'
                size = sysinfo.human_bytes(entry["size"])
                actions = (f'<a class="btn sm" href="/apps/{app_id}/files/download?p='
                           f'{ui.esc(entry["path"])}">Herunterladen</a> ')
                if entry["text"]:
                    actions = (f'<a class="btn sm" href="/apps/{app_id}/files?edit='
                               f'{ui.esc(entry["path"])}">Bearbeiten</a> ') + actions
            rows += f"""<tr><td>{name_html}</td><td class="mono">{ui.esc(size)}</td>
<td class="mono">{ui.esc(entry['modified'])}</td><td class="row">{actions}
<form method="post" action="/apps/{app_id}/files" style="display:inline">
{ui.csrf_input(self.csrf)}<input type="hidden" name="action" value="delete">
<input type="hidden" name="path" value="{ui.esc(entry['path'])}">
<button class="btn sm danger" type="submit"
 onclick="return confirm('{ui.esc(entry['name'])} wirklich löschen?')">Löschen</button>
</form></td></tr>"""
        if not entries and not current:
            rows += '<tr><td colspan="4" class="muted">Noch keine Dateien.</td></tr>'

        used = files.usage(base)
        docroot = (connector or {}).get("data", {}).get("container_path", "/data")
        body = f"""<a href="/apps/{app_id}" class="muted">← {ui.esc(app['name'])}</a>
<h1>Dateien</h1>
<p class="sub">{used['files']} {'Datei' if used['files'] == 1 else 'Dateien'} ·
{ui.esc(sysinfo.human_bytes(used['bytes']))}</p>
{self._app_tabs(app, 'Dateien')}
<div class="card" style="margin-bottom:14px"><dl class="kv">
<dt>Im Container</dt><dd class="mono">{ui.esc(docroot)}</dd>
<dt>Auf dem Server</dt><dd class="mono">{ui.esc(base)}</dd>
</dl></div>
<div class="card"><div class="between" style="margin-bottom:10px">
<div class="mono">{crumbs}</div></div>
<div class="tbl-wrap"><table>
<tr><th>Name</th><th>Größe</th><th>Geändert</th><th></th></tr>{rows}</table></div></div>
<div class="grid g3" style="margin-top:14px">
<div class="card"><h3>Datei hochladen</h3>
<form method="post" action="/apps/{app_id}/files" enctype="multipart/form-data">
{ui.csrf_input(self.csrf)}<input type="hidden" name="path" value="{ui.esc(current)}">
<div class="field"><input type="file" name="file" required></div>
<button class="btn primary" type="submit">Hochladen</button></form></div>
<div class="card"><h3>Ordner anlegen</h3>
<form method="post" action="/apps/{app_id}/files">
{ui.csrf_input(self.csrf)}<input type="hidden" name="action" value="mkdir">
<input type="hidden" name="path" value="{ui.esc(current)}">
<div class="field"><input name="name" placeholder="z. B. bilder" required></div>
<button class="btn" type="submit">Anlegen</button></form></div>
<div class="card"><h3>Datei anlegen</h3>
<form method="post" action="/apps/{app_id}/files">
{ui.csrf_input(self.csrf)}<input type="hidden" name="action" value="touch">
<input type="hidden" name="path" value="{ui.esc(current)}">
<div class="field"><input name="name" placeholder="z. B. seite.html" required></div>
<button class="btn" type="submit">Anlegen &amp; bearbeiten</button></form></div>
</div>"""
        self._render(f"{app['name']} — Dateien", body, "/apps")

    def download_file(self, app_id):
        app, _ = self._app_and_connector(app_id)
        if not app:
            return self._redirect("/apps", ("err", "App nicht gefunden."))
        try:
            data, name = files.read_bytes(self._app_base(app), self._query().get("p", ""))
        except files.FileError as exc:
            return self._redirect(f"/apps/{app_id}/files", ("err", str(exc)))
        return self._send(data, 200, "application/octet-stream",
                          {"Content-Disposition": f'attachment; filename="{name}"'})

    def do_files(self, app_id, form):
        app, _ = self._app_and_connector(app_id)
        if not app:
            return self._redirect("/apps", ("err", "App nicht gefunden."))
        base = self._app_base(app)
        action = form.get("action", "")
        current = form.get("path", "")
        target = f"/apps/{app_id}/files?p={urllib.parse.quote(current)}"
        try:
            if action == "save":
                files.write_text(base, form.get("path", ""), form.get("content", ""))
                parent = "/".join(form.get("path", "").split("/")[:-1])
                return self._redirect(f"/apps/{app_id}/files?p={urllib.parse.quote(parent)}",
                                      ("ok", "Datei gespeichert."))
            if action == "delete":
                files.delete(base, current)
                parent = "/".join(current.split("/")[:-1])
                return self._redirect(f"/apps/{app_id}/files?p={urllib.parse.quote(parent)}",
                                      ("ok", "Gelöscht."))
            if action == "mkdir":
                files.make_dir(base, current, form.get("name", ""))
                return self._redirect(target, ("ok", "Ordner angelegt."))
            if action == "touch":
                name = os.path.basename((form.get("name") or "").strip())
                if not name:
                    return self._redirect(target, ("err", "Ungültiger Dateiname."))
                rel = f"{current}/{name}" if current else name
                if not os.path.exists(files.resolve(base, rel)):
                    files.write_text(base, rel, "")
                return self._redirect(f"/apps/{app_id}/files?edit={urllib.parse.quote(rel)}")
        except files.FileError as exc:
            return self._redirect(target, ("err", str(exc)))
        return self._redirect(target)

    def do_upload(self, app_id, content_type):
        app, _ = self._app_and_connector(app_id)
        if not app:
            return self._redirect("/apps", ("err", "App nicht gefunden."))
        length = int(self.headers.get("Content-Length") or 0)
        if length > files.MAX_UPLOAD_BYTES + 8192:
            return self._redirect(f"/apps/{app_id}/files", ("err", "Datei zu groß (max. 200 MB)."))
        body = self.rfile.read(length) if length else b""
        try:
            fields, uploads = files.parse_multipart(body, content_type)
        except files.FileError as exc:
            return self._redirect(f"/apps/{app_id}/files", ("err", str(exc)))
        if not self._check_csrf(fields):
            return self._redirect(f"/apps/{app_id}/files",
                                  ("err", "Sicherheits-Token ungültig."))
        current = fields.get("path", "")
        target = f"/apps/{app_id}/files?p={urllib.parse.quote(current)}"
        if not uploads:
            return self._redirect(target, ("err", "Keine Datei ausgewählt."))
        try:
            saved = [files.save_upload(self._app_base(app), current, name, data)
                     for _field, name, data in uploads if name]
        except files.FileError as exc:
            return self._redirect(target, ("err", str(exc)))
        return self._redirect(target, ("ok", f"Hochgeladen: {', '.join(saved)}"))


def serve():
    store.init()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.daemon_threads = True
    print(f"weblab läuft auf http://{HOST}:{PORT}", flush=True)
    httpd.serve_forever()
