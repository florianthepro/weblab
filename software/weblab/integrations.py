"""Externe Integrationen: Reverse-Proxy (Caddy), DNS (Cloudflare), Plugin-Quellen."""
import json
import os
import subprocess
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


# --------------------------------------------------------------------------
# Reverse-Proxy (Caddy): Panel auf der Manage-Domain, je App eine Domain
# --------------------------------------------------------------------------
def render_caddyfile(manage_domain, app_routes, email=None):
    """app_routes: [{'domain':..., 'port':...}] — nur Apps mit Domain und http=true."""
    email = email or (f"admin@{manage_domain}" if manage_domain else "")
    out = ["{"]
    if email:
        out.append(f"\temail {email}")
    out.append("\tadmin 127.0.0.1:2019")
    out.append("}")
    out.append("")
    out.append("# Zugriff über die IP (vor/ohne Domain) und HTTP->HTTPS-Umleitung")
    out.append("http:// {")
    if manage_domain:
        hosts = " ".join([manage_domain] + [r["domain"] for r in app_routes if r.get("domain")])
        out.append(f"\t@named host {hosts}")
        out.append("\thandle @named {")
        out.append("\t\tredir https://{host}{uri} permanent")
        out.append("\t}")
    out.append("\thandle {")
    out.append(f"\t\treverse_proxy 127.0.0.1:{PANEL_PORT}")
    out.append("\t}")
    out.append("}")
    if manage_domain:
        out += ["", "# Verwaltungsoberfläche", f"{manage_domain} {{",
                "\tencode gzip zstd", f"\treverse_proxy 127.0.0.1:{PANEL_PORT}", "}"]
    for route in app_routes:
        if not route.get("domain"):
            continue
        out += ["", f"# App: {route.get('name', route['domain'])}", f"{route['domain']} {{",
                "\tencode gzip zstd", f"\treverse_proxy 127.0.0.1:{route['port']}", "}"]
    return "\n".join(out) + "\n"


def write_caddy(manage_domain, app_routes, email=None):
    content = render_caddyfile(manage_domain, app_routes, email)
    tmp = CADDYFILE + ".tmp"
    os.makedirs(os.path.dirname(CADDYFILE), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
    check = subprocess.run(["caddy", "validate", "--config", tmp],
                           capture_output=True, text=True, timeout=60)
    if check.returncode != 0:
        os.unlink(tmp)
        raise RuntimeError(f"Caddy-Konfiguration ungültig: {check.stderr[-400:]}")
    os.replace(tmp, CADDYFILE)
    reload_proc = subprocess.run(["systemctl", "reload", "caddy"],
                                 capture_output=True, text=True, timeout=60)
    if reload_proc.returncode != 0:
        subprocess.run(["systemctl", "restart", "caddy"], capture_output=True, text=True, timeout=90)
    return content


# --------------------------------------------------------------------------
# Cloudflare-DNS
# --------------------------------------------------------------------------
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

    def set_record(self, domain, name, content, rtype="A", proxied=False, ttl=120):
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
        resp = http_json(f"{CF_API}/zones/{zone}/dns_records", method="POST", headers=self.headers,
                         data={"type": rtype, "name": name, "content": content,
                               "ttl": ttl, "proxied": proxied})
        if resp.get("success"):
            return True, None
        errors = resp.get("errors") or []
        return False, (errors[0].get("message") if errors else "Unbekannter Fehler")

    def delete_record(self, domain, record_id):
        zone, err = self.zone_id(domain)
        if not zone:
            return False, err
        resp = http_json(f"{CF_API}/zones/{zone}/dns_records/{record_id}",
                         method="DELETE", headers=self.headers)
        return bool(resp.get("success")), None


# --------------------------------------------------------------------------
# Plugin-Quellen (Advanced-Bereich einer App)
# --------------------------------------------------------------------------
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


def write_caddyfile_safe(manage_domain, app_routes, email=None):
    """Wie write_caddy, wirft aber nicht — eine Proxy-Störung darf keine App-Aktion abbrechen."""
    try:
        write_caddy(manage_domain, app_routes, email)
        return True, None
    except Exception as exc:  # noqa: BLE001 - bewusst: Proxy-Fehler nur melden
        return False, str(exc)
