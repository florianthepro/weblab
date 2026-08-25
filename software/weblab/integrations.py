"""Externe Integrationen: Reverse-Proxy (Caddy), DNS (Cloudflare), Plugin-Quellen."""
import base64
import hashlib
import json
import glob
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

CADDYFILE = os.environ.get("WEBLAB_CADDYFILE", "/etc/caddy/Caddyfile")
PANEL_PORT = int(os.environ.get("WEBLAB_PORT", "8099"))
UA = "weblab/1.0"


def http_json(url, method="GET", headers=None, data=None, timeout=25):
    payload = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=payload, method=method)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"success": False, "errors": [{"message": f"HTTP {exc.code}: {body[:200]}"}]}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"success": False, "errors": [{"message": str(exc)}]}


_HOST_RE = re.compile(
    r"^(\*\.)?([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")


def _valid_host(host):
    """Nur echte Hostnamen (klein, mit Punkt, ohne Schema/Pfad/Port) als Caddy-Site
    zulassen — ein kaputter App-Domainname darf die ganze Konfiguration nicht sprengen."""
    return bool(host) and len(host) <= 253 and bool(_HOST_RE.match(host))


def render_caddyfile(manage_domain, app_routes, email=None, panel_hosts=None,
                     access="both", domain_ok=True, cert_hosts=None, https_ready=False,
                     server_ip=""):
    """app_routes: [{'domain':..., 'port':...}] — nur Apps mit Domain und http=true.
    server_ip: (nur noch informativ, ungenutzt) — der IP-Zugang läuft über einen
    Catch-all-HTTPS-Block mit interner CA (on_demand), der für JEDE angefragte
    IP/Adresse beim Verbinden ein Zertifikat ausstellt. So sind Setup und
    Anmeldung über die IP immer verschlüsselt, auch wenn sich die IP ändert.
    panel_hosts: zusätzliche Hostnamen (App-Verwaltungs-Subdomains), die auf das Panel zeigen.
    access: 'both' | 'domain' | 'ip' — worüber die Verwaltung erreichbar ist.
    domain_ok: zeigt der DNS-Eintrag noch hierher? Steuert NUR das IP-Failover:
               zeigt die Domain nicht mehr hierher, bleibt das Panel zusätzlich
               über die IP erreichbar (kein Aussperren). Der HTTPS-Block für die
               Domain wird trotzdem immer geschrieben, damit Caddy das Zertifikat
               holen/erneuern kann, sobald die Domain (wieder) hierher zeigt.
    cert_hosts: Hostnamen von Diensten (z. B. Mailserver), für die Caddy nur ein
                Zertifikat holen soll — unabhängig vom Zugangsmodus.
    https_ready: hat Caddy für die Domain schon ein Zertifikat? Steuert NUR, ob im
                 reinen Domain-Betrieb die IP schon auf die Domain umleiten darf.
                 Solange kein Zertifikat da ist, bedient die IP das Panel selbst über
                 HTTP — sonst würde die IP auf eine noch zertifikatslose HTTPS-Domain
                 umleiten und der Browser hinge fest ("nicht sicher")."""
    email = email or (f"admin@{manage_domain}" if manage_domain else "")
    panel_hosts = [h for h in (panel_hosts or []) if h]
    app_domains = [r["domain"] for r in app_routes if r.get("domain")]
    # Panel soll über die Domain laufen, wenn gewünscht. Der HTTPS-Block wird IMMER
    # geschrieben (unabhängig von domain_ok) — Caddy holt und erneuert das Zertifikat
    # selbst (Let's Encrypt), sobald die Domain hierher zeigt. Vom domain_ok abhängig
    # zu machen, würde bei einem fragilen DNS-Check die ganze HTTPS-Seite weglassen
    # -> "nur HTTP"/nicht sicher.
    want_domain = bool(manage_domain) and access in ("domain", "both")
    https_on = want_domain
    # Die IP bedient das Panel direkt, außer im reinen Domain-Betrieb, solange die
    # Domain hierher zeigt UND das Zertifikat steht. Failover-Gründe, in denen die IP
    # das Panel weiter selbst über HTTP bedient (kein Aussperren, kein Hängen):
    #  - Zugang ist nicht rein per Domain (both/ip),
    #  - die Domain zeigt nicht mehr hierher (domain_ok=False),
    #  - das Domain-Zertifikat steht noch nicht (https_ready=False) — sonst würde die
    #    IP auf eine zertifikatslose HTTPS-Domain umleiten und der Browser hinge fest.
    ip_serves_panel = (access != "domain") or (not domain_ok) or (not https_ready)
    panel_domain_hosts = ([manage_domain] + panel_hosts) if https_on else []

    out = ["{"]
    if email:
        out.append(f"\temail {email}")
    out.append("\tadmin 127.0.0.1:2019")
    out.append("}")
    out.append("")
    out.append("# HTTP-Ebene: IP-Zugriff und HTTP->HTTPS-Umleitung, sobald Zertifikat steht")
    out.append("http:// {")
    valid_routes = [r for r in app_routes if _valid_host(r.get("domain"))]
    named = list(dict.fromkeys(h for h in (panel_domain_hosts + [r["domain"] for r in valid_routes])
                               if _valid_host(h)))
    if named:
        out.append(f"\t@named host {' '.join(named)}")
        out.append("\thandle @named {")
        out.append("\t\tredir https://{host}{uri} permanent")
        out.append("\t}")
    out.append("\thandle {")
    if not ip_serves_panel:
        # Nur-Domain-Betrieb: IP-Aufruf zur Domain umleiten (temporär, damit der
        # Browser bei Failover/Rückschaltung die IP sofort wieder direkt erreicht).
        out.append(f"\t\tredir https://{manage_domain}{{uri}} temporary")
    else:
        # IP-Zugang immer verschlüsselt: auf HTTPS desselben Hosts umleiten — den
        # Rest übernimmt der Catch-all unten (interne CA, on_demand).
        out.append("\t\tredir https://{host}{uri} temporary")
    out.append("\t}")
    out.append("}")

    # Sicherheitsnetz für alles, was keine benannte Site trifft (IP-Zugriff, alte
    # Namen): HTTPS mit Caddys interner CA. on_demand stellt beim Verbinden ein
    # Zertifikat für GENAU die angefragte Adresse aus — funktioniert daher auch,
    # wenn sich die Server-IP ändert, und leitet im Nur-Domain-Betrieb weiter.
    out.append("")
    out.append("# Panel über IP/unbekannte Namen — HTTPS mit interner CA (self-signed)")
    out.append("https:// {")
    out.append("\ttls internal {")
    out.append("\t\ton_demand")
    out.append("\t}")
    if ip_serves_panel:
        out.append("\tencode gzip zstd")
        out.append(f"\treverse_proxy 127.0.0.1:{PANEL_PORT}")
    else:
        out.append(f"\tredir https://{manage_domain}{{uri}} temporary")
    out.append("}")

    emitted = set()

    def _site(host, body, comment):
        # Ungültige oder doppelte Hosts überspringen: ein kaputter/doppelter Domainname
        # darf nie die ganze Caddy-Konfiguration ungültig machen (sonst SSL/Route weg).
        if not _valid_host(host) or host in emitted:
            return
        emitted.add(host)
        out.extend(["", comment, f"{host} {{", *body, "}"])

    panel_body = ["\tencode gzip zstd", f"\treverse_proxy 127.0.0.1:{PANEL_PORT}"]
    if want_domain:
        _site(manage_domain, panel_body, "# Verwaltungsoberfläche")
        for host in panel_hosts:
            _site(host, panel_body, f"# App-Verwaltung: {host}")
    for route in valid_routes:
        _site(route["domain"], ["\tencode gzip zstd",
                                f"\treverse_proxy 127.0.0.1:{route['port']}"],
              f"# App: {route.get('name', route['domain'])}")
    for host in (cert_hosts or []):
        _site(host, ["\trespond 204"], f"# Zertifikat für Dienst {host}")
    return "\n".join(out) + "\n"


# Cloudflares veröffentlichte Proxy-Netze (www.cloudflare.com/ips, seit Jahren stabil).
# Eine geproxiete Domain löst auf diese IPs auf — das ist KEIN "zeigt woandershin".
_CF_NETS = None


def _cloudflare_ip(addr):
    global _CF_NETS
    import ipaddress
    if _CF_NETS is None:
        _CF_NETS = [ipaddress.ip_network(n) for n in (
            "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
            "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
            "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
            "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
            "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32",
            "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32")]
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in _CF_NETS)


def domain_up(domain, server_ip="", allow_cloudflare=False):
    """True, wenn die Domain (noch) auf DIESEN Server zeigt. Fehlt der Eintrag
    (NXDOMAIN) oder zeigt er woandershin, gilt sie als 'unten' — das Panel bleibt
    dann über die IP erreichbar, damit man sich nicht aussperrt. Ist die eigene IP
    unbekannt, reicht ein beliebiger Eintrag (kein Fehlalarm).
    allow_cloudflare: auch Cloudflare-Proxy-IPs gelten als 'zeigt hierher' — für den
    Betrieb hinter der orangenen Wolke, NACHDEM das Zertifikat steht. Eine auf einen
    fremden Server umgezogene Domain fällt weiterhin durch (kein Aussperren)."""
    if not domain:
        return True
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(domain, None)}
    except (socket.gaierror, OSError):
        return False
    if not addrs:
        return False
    if not server_ip:
        return True
    if server_ip in addrs:
        return True
    return allow_cloudflare and any(_cloudflare_ip(a) for a in addrs)


# --- Let's-Encrypt-Zertifikate von Caddy an Dienste weiterreichen (z. B. Mailserver) ---
CADDY_STORAGE = os.environ.get("WEBLAB_CADDY_STORAGE", "/var/lib/caddy/.local/share/caddy")
CERT_DIR = os.environ.get("WEBLAB_CERT_DIR", "/var/lib/weblab/certs")


def caddy_cert_paths(domain):
    """(crt, key) des von Caddy verwalteten Zertifikats für die Domain — oder (None, None).
    Caddy holt und erneuert diese Zertifikate automatisch (Let's Encrypt/ZeroSSL)."""
    if not domain:
        return None, None
    base = os.path.join(CADDY_STORAGE, "certificates")
    crt = sorted(glob.glob(os.path.join(base, "*", domain, f"{domain}.crt")))
    key = sorted(glob.glob(os.path.join(base, "*", domain, f"{domain}.key")))
    return (crt[0], key[0]) if crt and key else (None, None)


def https_ready(domain):
    """True, wenn Caddy für die Domain schon ein Zertifikat hat. Solange nicht, bleibt
    das Panel über HTTP erreichbar, damit die Anmeldung nicht aufs Zertifikat warten muss."""
    crt, key = caddy_cert_paths(domain)
    return bool(crt and key)


def exported_cert_dir(domain):
    """Pfad mit dem exportierten Zertifikat, falls vorhanden — sonst None."""
    out = os.path.join(CERT_DIR, domain)
    return out if domain and os.path.exists(os.path.join(out, "fullchain.pem")) else None


def export_cert(domain):
    """Kopiert Caddys Zertifikat in einen stabilen Pfad (fullchain.pem/privkey.pem),
    aus dem Dienste wie der Mailserver lesen. Gibt True zurück, wenn sich dabei etwas
    geändert hat (neu oder erneuert). Best-effort: ohne Zertifikat passiert nichts —
    der Dienst nutzt dann sein Selbstsigniertes weiter (kein Ausfall)."""
    crt, key = caddy_cert_paths(domain)
    if not crt or not key:
        return False
    try:                                    # beide zusammen lesen (alles-oder-nichts,
        new_crt = open(crt, "rb").read()    # damit nie ein zusammengewürfeltes Paar
        new_key = open(key, "rb").read()    # aus Zertifikat+altem Schlüssel entsteht)
    except OSError:
        return False
    if not new_crt or not new_key:
        return False
    out = os.path.join(CERT_DIR, domain)
    os.makedirs(out, exist_ok=True)
    changed = False
    for data, name, mode in ((new_crt, "fullchain.pem", 0o644), (new_key, "privkey.pem", 0o600)):
        dst = os.path.join(out, name)
        old = open(dst, "rb").read() if os.path.exists(dst) else None
        if data != old:
            fd, tmp = tempfile.mkstemp(dir=out, prefix="." + name + ".", suffix=".tmp")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.chmod(tmp, mode)
            os.replace(tmp, dst)            # atomar ersetzen
            changed = True
    return changed


_caddy_lock = threading.Lock()


def retry_cert(domain):
    """Caddy dazu bringen, das ACME-Verfahren für die Domain sofort neu zu starten.
    Ohne diese Hilfe kann Caddy nach mehreren Fehlversuchen bis zu einer Stunde
    warten. Wir löschen den zwischengespeicherten (leeren) Certificate-Ordner der
    Domain und laden Caddy neu — das erzwingt eine frische Runde.
    Rückgabe: (ok:bool, hinweis:str)."""
    if not _valid_host(domain) or domain.startswith("*."):
        return False, "keine gültige Domain"   # schützt auch die glob-Pfade unten
    safe = glob.escape(domain)   # Domain darf nie als Glob-Muster wirken
    with _caddy_lock:
        # Leere/fehlgeschlagene Zertifikatsordner der Domain entfernen. Ein gültiges
        # (crt+key) bleibt stehen, damit wir nichts Funktionierendes zerstören.
        base = os.path.join(CADDY_STORAGE, "certificates")
        for issuer_dir in glob.glob(os.path.join(base, "*", safe)):
            has_crt = os.path.exists(os.path.join(issuer_dir, f"{domain}.crt"))
            has_key = os.path.exists(os.path.join(issuer_dir, f"{domain}.key"))
            if not (has_crt and has_key):
                try:
                    shutil.rmtree(issuer_dir)
                except OSError:
                    pass
        # ACME-Locks entfernen, falls Caddy noch in einem Backoff-Zustand steckt.
        for lock in glob.glob(os.path.join(CADDY_STORAGE, "locks", f"issue_cert_{safe}*")):
            try:
                os.unlink(lock)
            except OSError:
                pass
        r = subprocess.run(["systemctl", "reload", "caddy"], capture_output=True,
                           text=True, timeout=60)
        if r.returncode != 0:
            r = subprocess.run(["systemctl", "restart", "caddy"], capture_output=True,
                               text=True, timeout=90)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "caddy reload/restart fehlgeschlagen")[-300:]
    return True, ""


def write_caddy(manage_domain, app_routes, email=None, panel_hosts=None,
                access="both", domain_ok=True, cert_hosts=None, https_ready=False,
                server_ip=""):
    content = render_caddyfile(manage_domain, app_routes, email, panel_hosts,
                               access, domain_ok, cert_hosts, https_ready, server_ip)
    # Ein Schloss, damit Watchdog- und Anfrage-Threads sich nicht in die Quere kommen.
    with _caddy_lock:
        os.makedirs(os.path.dirname(CADDYFILE), exist_ok=True)
        try:
            if os.path.exists(CADDYFILE) and \
                    open(CADDYFILE, encoding="utf-8").read() == content:
                return content          # keine Änderung -> kein Neuladen
        except OSError:
            pass
        # Reste früherer, hart abgebrochener Schreibversuche entfernen (SIGTERM beim
        # Update kann die finally-Aufräumung überspringen).
        for stale in glob.glob(os.path.join(os.path.dirname(CADDYFILE), "Caddyfile.new.*.tmp")):
            try:
                os.unlink(stale)
            except OSError:
                pass
        # Wichtig: Dateiname MUSS mit "Caddyfile" beginnen UND der Adapter explizit
        # angegeben werden. Ohne --adapter rät Caddy das Format aus dem Dateinamen —
        # bei ".Caddyfile.xyz.tmp" (führender Punkt) hielt Caddy die Datei für JSON
        # und die Validierung schlug IMMER fehl. Folge: die Konfiguration wurde nie
        # übernommen, Caddy lief dauerhaft mit der Startkonfiguration -> kein HTTPS.
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(CADDYFILE),
                                   prefix="Caddyfile.new.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            # mkstemp erzeugt 0600 root:root und os.replace übernimmt das — der
            # Caddy-Dienst läuft aber als Nutzer "caddy" und könnte die Datei dann
            # nicht lesen (Reload schlägt fehl, Caddy bleibt ohne Konfiguration).
            os.chmod(tmp, 0o644)
            check = subprocess.run(["caddy", "validate", "--adapter", "caddyfile",
                                    "--config", tmp],
                                   capture_output=True, text=True, timeout=60)
            if check.returncode != 0:
                raise RuntimeError(f"Caddy-Konfiguration ungültig: {check.stderr[-400:]}")
            os.replace(tmp, CADDYFILE)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        reload_proc = subprocess.run(["systemctl", "reload", "caddy"],
                                     capture_output=True, text=True, timeout=60)
        if reload_proc.returncode != 0:
            subprocess.run(["systemctl", "restart", "caddy"], capture_output=True, text=True, timeout=90)
    return content


CF_API = "https://api.cloudflare.com/client/v4"


class Cloudflare:
    def __init__(self, token):
        self.token = (token or "").strip()

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def ok(self):
        return bool(self.token)

    def zone_id(self, domain):
        if not self.ok():
            return None, "Kein Cloudflare-Token hinterlegt."
        resp = http_json(f"{CF_API}/zones?name={urllib.parse.quote(domain)}", headers=self.headers)
        results = resp.get("result") or []
        if results:
            return results[0]["id"], None
        errors = resp.get("errors") or []
        message = errors[0].get("message") if errors else "Zone nicht gefunden."
        return None, message

    def list_records(self, domain):
        zone, err = self.zone_id(domain)
        if not zone:
            return [], err
        resp = http_json(f"{CF_API}/zones/{zone}/dns_records?per_page=200", headers=self.headers)
        return resp.get("result") or [], None

    def set_record(self, domain, name, content, rtype="A", proxied=False, ttl=120,
                   priority=None, comment=None):
        """Record anlegen/ersetzen (gleicher Name+Typ wird überschrieben)."""
        zone, err = self.zone_id(domain)
        if not zone:
            return False, err
        existing = http_json(
            f"{CF_API}/zones/{zone}/dns_records?type={rtype}&name={urllib.parse.quote(name)}",
            headers=self.headers)
        for record in existing.get("result") or []:
            http_json(f"{CF_API}/zones/{zone}/dns_records/{record['id']}",
                      method="DELETE", headers=self.headers)
        payload = {"type": rtype, "name": name, "content": content, "ttl": ttl}
        if rtype in ("A", "AAAA", "CNAME"):
            payload["proxied"] = proxied
        if priority is not None:
            payload["priority"] = int(priority)
        if comment:
            payload["comment"] = comment[:100]
        resp = http_json(f"{CF_API}/zones/{zone}/dns_records", method="POST",
                         headers=self.headers, data=payload)
        if resp.get("success"):
            return True, None
        errors = resp.get("errors") or []
        return False, (errors[0].get("message") if errors else "Unbekannter Fehler")

    def zones(self):
        """Alle Domains (Zonen) des verknüpften Kontos."""
        resp = http_json(f"{CF_API}/zones?per_page=200", headers=self.headers)
        return [{"id": z["id"], "name": z["name"], "status": z.get("status", "")}
                for z in (resp.get("result") or [])]

    def verify(self):
        """Prüft, ob der gespeicherte Token gültig ist."""
        resp = http_json(f"{CF_API}/user/tokens/verify", headers=self.headers)
        if resp.get("success"):
            return True, (resp.get("result") or {}).get("status", "active")
        errors = resp.get("errors") or []
        return False, (errors[0].get("message") if errors else "Token ungültig")

    def delete_record(self, domain, record_id):
        zone, err = self.zone_id(domain)
        if not zone:
            return False, err
        resp = http_json(f"{CF_API}/zones/{zone}/dns_records/{record_id}",
                         method="DELETE", headers=self.headers)
        return bool(resp.get("success")), None


def search_plugins(source, query, loader=None, game_versions=None, limit=20):
    """Suche in einer Plugin-Quelle. Rückgabe: [{id,name,summary,author,downloads,url}]"""
    if source == "modrinth":
        facets = [["project_type:plugin", "project_type:mod"]]
        if loader:
            facets.append([f"categories:{loader}"])
        if game_versions:
            facets.append([f"versions:{v}" for v in game_versions])
        params = urllib.parse.urlencode(
            {"query": query, "limit": limit, "facets": json.dumps(facets)})
        resp = http_json(f"https://api.modrinth.com/v2/search?{params}")
        items = []
        for hit in resp.get("hits", []) or []:
            items.append({
                "id": hit.get("project_id"), "name": hit.get("title"),
                "summary": (hit.get("description") or "")[:180],
                "author": hit.get("author", ""), "downloads": hit.get("downloads", 0),
                "url": f"https://modrinth.com/plugin/{hit.get('slug')}", "source": "modrinth",
            })
        return items
    if source == "spiget":
        params = urllib.parse.urlencode({"size": limit, "fields": "id,name,tag,downloads"})
        resp = http_json(
            f"https://api.spiget.org/v2/search/resources/{urllib.parse.quote(query)}?{params}")
        items = []
        for hit in resp if isinstance(resp, list) else []:
            items.append({
                "id": str(hit.get("id")), "name": hit.get("name"),
                "summary": (hit.get("tag") or "")[:180], "author": "",
                "downloads": hit.get("downloads", 0),
                "url": f"https://www.spigotmc.org/resources/{hit.get('id')}", "source": "spiget",
            })
        return items
    return []


def plugin_download_url(source, project_id, loader=None, game_versions=None):
    """Direkte Download-URL der neuesten passenden Version ermitteln."""
    if source == "modrinth":
        params = {}
        if loader:
            params["loaders"] = json.dumps([loader])
        if game_versions:
            params["game_versions"] = json.dumps(list(game_versions))
        query = ("?" + urllib.parse.urlencode(params)) if params else ""
        versions = http_json(f"https://api.modrinth.com/v2/project/{project_id}/version{query}")
        if not isinstance(versions, list) or not versions:
            versions = http_json(f"https://api.modrinth.com/v2/project/{project_id}/version")
        if isinstance(versions, list):
            for version in versions:
                for file in version.get("files", []):
                    if file.get("filename", "").endswith(".jar"):
                        return file["url"], file["filename"]
        return None, None
    if source == "spiget":
        return (f"https://api.spiget.org/v2/resources/{project_id}/download",
                f"spigot-{project_id}.jar")
    return None, None


def write_caddyfile_safe(manage_domain, app_routes, email=None, panel_hosts=None,
                         access="both", domain_ok=True, cert_hosts=None, https_ready=False,
                         server_ip=""):
    """Wie write_caddy, wirft aber nicht."""
    try:
        write_caddy(manage_domain, app_routes, email, panel_hosts, access, domain_ok,
                    cert_hosts, https_ready, server_ip)
        return True, None
    except Exception as exc:  # noqa: BLE001 - bewusst: Proxy-Fehler nur melden
        return False, str(exc)


# Konto-Anmeldung: erzeugt über die API einen auf DNS begrenzten Token.
# Der Konto-Schlüssel wird nur für diesen Aufruf benutzt und nicht gespeichert.
DNS_PERMISSIONS = ("DNS Write", "Zone Read")
FALLBACK_PERMISSION_IDS = {
    "DNS Write": "4755a26eedb94da69e1066d98aa820be",
    "Zone Read": "c8fed203ed3043cba015a93ad1616f1f",
}


def _account_headers(email, global_key):
    return {"X-Auth-Email": email.strip(), "X-Auth-Key": global_key.strip()}


def permission_group_ids(email, global_key):
    """IDs der benötigten Berechtigungen ermitteln (mit bekannten Werten als Rückfall)."""
    resp = http_json(f"{CF_API}/user/tokens/permission_groups",
                     headers=_account_headers(email, global_key))
    found = {}
    for group in resp.get("result") or []:
        name = group.get("name")
        if name in DNS_PERMISSIONS and "zone" in " ".join(group.get("scopes") or []):
            found[name] = group.get("id")
    for name in DNS_PERMISSIONS:
        found.setdefault(name, FALLBACK_PERMISSION_IDS[name])
    return found, (resp.get("errors") or [])


def _first_account_id(email, global_key):
    """Konto-ID ermitteln, um den Token auf dieses Konto zu begrenzen."""
    resp = http_json(f"{CF_API}/accounts?per_page=5", headers=_account_headers(email, global_key))
    results = resp.get("result") or []
    return results[0].get("id") if results else None


def link_account(email, global_key, label="weblab"):
    """Erzeugt einen auf DNS beschränkten Token. Rückgabe: (token, fehler)."""
    email = (email or "").strip()
    global_key = (global_key or "").strip()
    if not email or not global_key:
        return None, "E-Mail und Konto-Schlüssel werden benötigt."

    groups, errors = permission_group_ids(email, global_key)
    if errors and not groups:
        return None, errors[0].get("message", "Anmeldung fehlgeschlagen.")

    permissions = [{"id": groups[name]} for name in DNS_PERMISSIONS]
    account_id = _first_account_id(email, global_key)
    if account_id:
        # Nur die Zonen DIESES Kontos — nicht alle Konten des Nutzers.
        resources = {f"com.cloudflare.api.account.{account_id}":
                     {"com.cloudflare.api.account.zone.*": "*"}}
    else:
        resources = {"com.cloudflare.api.account.zone.*": "*"}
    expires = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                            time.gmtime(time.time() + 365 * 24 * 3600))
    payload = {
        "name": f"{label}-dns"[:32],
        "policies": [{"effect": "allow", "resources": resources,
                      "permission_groups": permissions}],
        "expires_on": expires,
    }
    resp = http_json(f"{CF_API}/user/tokens", method="POST",
                     headers=_account_headers(email, global_key), data=payload)
    if resp.get("success"):
        token = (resp.get("result") or {}).get("value")
        if token:
            return token, None
        return None, "Cloudflare hat keinen Token zurückgegeben."
    errors = resp.get("errors") or []
    message = errors[0].get("message") if errors else "Token konnte nicht erstellt werden."
    code = errors[0].get("code") if errors else None
    if code == 9103:
        message = "E-Mail oder Konto-Schlüssel stimmen nicht."
    return None, message


# OAuth (Authorization Code + PKCE). Rückleitung:
# https://<verwaltungs-domain>/network/cloudflare/callback
CF_AUTHORIZE = "https://dash.cloudflare.com/oauth2/auth"
CF_TOKEN_URL = "https://dash.cloudflare.com/oauth2/token"
CF_SCOPES = "dns_records:read dns_records:edit zone:read offline_access"


def http_form(url, data, timeout=25):
    """POST mit application/x-www-form-urlencoded (OAuth-Endpunkte erwarten das)."""
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8", "replace"))
        except (json.JSONDecodeError, ValueError):
            return {"error": f"http_{exc.code}"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"error": str(exc)}


def pkce_pair():
    """Zufallsgeheimnis + zugehörige Prüfsumme (S256) für den OAuth-Ablauf."""
    verifier = base64.urlsafe_b64encode(os.urandom(48)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def authorize_url(client_id, redirect_uri, state, challenge, scopes=CF_SCOPES):
    params = urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
        "scope": scopes, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    return f"{CF_AUTHORIZE}?{params}"


def exchange_code(client_id, client_secret, redirect_uri, code, verifier):
    """Autorisierungscode gegen einen Zugang eintauschen. Rückgabe: (token, fehler)."""
    data = {"grant_type": "authorization_code", "code": code,
            "redirect_uri": redirect_uri, "client_id": client_id,
            "code_verifier": verifier}
    if client_secret:
        data["client_secret"] = client_secret
    resp = http_form(CF_TOKEN_URL, data)
    if resp.get("access_token"):
        return resp["access_token"], None
    return None, (resp.get("error_description") or resp.get("error")
                  or "Anmeldung fehlgeschlagen.")


# --------------------------------------------------------------------------
# Mehrere Cloudflare-Konten: Zonen aggregieren, Konto je Zone finden
# --------------------------------------------------------------------------
_DNS_CACHE = {"zones": {}, "records": {}}


def invalidate_dns_cache():
    _DNS_CACHE["zones"].clear()
    _DNS_CACHE["records"].clear()


def cached_records(token, zone_name):
    """DNS-Einträge einer Zone, kurz zwischengespeichert (schnellere Netzwerk-Seite)."""
    key = (token, zone_name)
    ent = _DNS_CACHE["records"].get(key)
    if ent and time.time() - ent[0] < 120:
        return ent[1]
    recs, _err = Cloudflare(token).list_records(zone_name)
    _DNS_CACHE["records"][key] = (time.time(), recs)
    return recs


def all_zones(accounts):
    """Zonen aller Konten: [{name, token, account_label, proxied_default}].
    Kurz zwischengespeichert, damit die Netzwerk-Seite nicht bei jedem Aufruf alle
    Konten neu abfragt."""
    ckey = tuple(sorted(a.get("token", "") for a in (accounts or []) if a.get("token")))
    ent = _DNS_CACHE["zones"].get(ckey)
    if ent and time.time() - ent[0] < 120:
        return ent[1]
    seen, result = set(), []
    for acc in accounts or []:
        token = acc.get("token")
        if not token:
            continue
        for zone in Cloudflare(token).zones():
            name = zone.get("name")
            if name and name not in seen:
                seen.add(name)
                result.append({"name": name, "token": token,
                               "account": acc.get("label", "")})
    result.sort(key=lambda z: z["name"])
    _DNS_CACHE["zones"][ckey] = (time.time(), result)
    return result


def resolve_zone(accounts, hostname, cache=None):
    """Zone + Token zu einem Hostnamen — fragt die Kandidaten-Domains direkt bei
    Cloudflare ab (funktioniert auch, wenn die allgemeine Zonen-Liste leer/dünn ist,
    z. B. bei eng zugeschnittenen Tokens). Längste passende Domain gewinnt."""
    host = (hostname or "").strip(".").lower()
    if not host or "." not in host:
        return None
    labels = host.split(".")
    candidates = [".".join(labels[i:]) for i in range(len(labels) - 1)]
    cache = {} if cache is None else cache
    # Kandidaten von der spezifischsten zur allgemeinsten -> die genaueste (längste)
    # Zone gewinnt, egal in welchem Konto sie liegt.
    for cand in candidates:
        if "." not in cand:
            continue
        for acc in accounts or []:
            token = acc.get("token")
            if not token:
                continue
            key = (token, cand)
            if key not in cache:
                cache[key] = Cloudflare(token).zone_id(cand)[0]
            if cache[key]:
                return {"name": cand, "id": cache[key], "token": token,
                        "account": acc.get("label", "")}
    return None


def ensure_unproxied(accounts, hostname, server_ip=""):
    """Stellt sicher, dass der A-Record von hostname bei Cloudflare NICHT proxied
    (graue Wolke) ist und auf server_ip zeigt. Ohne dies scheitert Let's Encrypt
    (der Cloudflare-Proxy fängt TLS-ALPN ab, und im 'Full (strict)'-Modus zeigt CF
    einen 521-Fehler, solange das Origin-Zertifikat fehlt).
    Rückgabe: (geändert:bool, hinweis:str). geändert=True wenn der Record umgestellt
    wurde. hinweis ist entweder leer, ein Fehlermeldung, oder eine erklärende Info."""
    if not hostname:
        return False, ""
    zone = resolve_zone(accounts or [], hostname)
    if not zone:
        return False, ""      # keine Zone bei einem verknüpften Konto — nichts zu tun
    cf = Cloudflare(zone["token"])
    recs, err = cf.list_records(zone["name"])
    if err:
        return False, err
    hostname = hostname.lower()
    target = None
    for r in recs or []:
        if r.get("type") == "A" and (r.get("name") or "").lower() == hostname:
            target = r
            break
    # Kein passender A-Record → anlegen (dann garantiert unproxied und mit richtiger IP).
    if not target:
        if not server_ip:
            return False, "kein A-Record, IP unbekannt"
        ok, err = cf.set_record(hostname, hostname, server_ip, "A", proxied=False,
                                comment="weblab Verwaltungsoberfläche")
        invalidate_dns_cache()
        return (ok, "" if ok else (err or "Fehler"))
    wrong_ip = server_ip and target.get("content") != server_ip
    is_proxied = bool(target.get("proxied"))
    if not is_proxied and not wrong_ip:
        return False, ""      # alles gut
    ok, err = cf.set_record(hostname, hostname, server_ip or target.get("content"),
                            "A", proxied=False,
                            comment="weblab Verwaltungsoberfläche (auto: unproxied für Zertifikat)")
    invalidate_dns_cache()
    return (ok, "" if ok else (err or "Fehler"))


def token_for_host(accounts, hostname):
    """Token des Kontos, dessen Zone am besten zu hostname passt (längste Übereinstimmung)."""
    best, best_len = None, -1
    for zone in all_zones(accounts):
        z = zone["name"]
        if (hostname == z or hostname.endswith("." + z)) and len(z) > best_len:
            best, best_len = zone["token"], len(z)
    return best
