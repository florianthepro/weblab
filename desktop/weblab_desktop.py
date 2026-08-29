"""weblab Desktop: Server-Liste und randloses Fenster fuer die Verwaltung."""
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP = "weblab Desktop"
PING = "weblab-desktop"
PORTS = range(8788, 8799)
WINDOW = "480,900"
PANEL_WINDOW = "1160,860"
INSTALL_CMD = ("curl -fsSL https://raw.githubusercontent.com/florianthepro/weblab/main/install.sh "
               "| sudo bash")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "software", "weblab")]
try:
    import ui
    CSS, ESC = ui.CSS, ui.esc
except Exception:  # noqa: BLE001 - im gebauten exe liegt ui.py daneben, sonst Notlayout
    import html as _html
    CSS = ("body{font:15px -apple-system,'Segoe UI',system-ui,sans-serif;margin:0;"
           "background:#f2f2f7;color:#000}.wrap{padding:20px}")

    def ESC(v):
        return _html.escape("" if v is None else str(v), quote=True)


def config_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, "weblab")
    os.makedirs(path, exist_ok=True)
    return path


def _read(name, default):
    try:
        with open(os.path.join(config_dir(), name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write(name, data, private=False):
    path = os.path.join(config_dir(), name)
    tmp = path + ".tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    with os.fdopen(os.open(tmp, flags, 0o600 if private else 0o644), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def servers():
    data = _read("servers.json", [])
    return data if isinstance(data, list) else []


def normalize(address):
    address = (address or "").strip()
    if not address:
        return ""
    if "://" not in address:
        address = "https://" + address
    parts = urllib.parse.urlsplit(address)
    host = parts.netloc or parts.path
    return f"{parts.scheme or 'https'}://{host.strip('/')}"


# ---------- Erreichbarkeit ----------
_STATUS = {}
_LOCK = threading.Lock()


def probe(url, timeout=3.0):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE      # IP-Zugang nutzt bewusst ein eigenes Zertifikat
    req = urllib.request.Request(url.rstrip("/") + "/login", method="GET",
                                 headers={"User-Agent": APP})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return "online" if resp.status < 500 else "fehler"
    except urllib.error.HTTPError as exc:
        return "online" if exc.code < 500 else "fehler"
    except (urllib.error.URLError, socket.timeout, OSError, ValueError):
        return "offline"


def refresh_status():
    entries = servers()
    threads = []
    for entry in entries:
        def work(url=entry["url"]):
            state = probe(url)
            with _LOCK:
                _STATUS[url] = {"state": state, "ts": time.time()}
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join(timeout=5)
    with _LOCK:
        return {url: dict(val) for url, val in _STATUS.items()}


# ---------- Fenster oeffnen ----------
_WIN_APPS = {"msedge.exe": ("Microsoft", "Edge", "Application", "msedge.exe"),
             "chrome.exe": ("Google", "Chrome", "Application", "chrome.exe"),
             "brave.exe": ("BraveSoftware", "Brave-Browser", "Application", "brave.exe")}


def _from_registry(exe):
    import winreg
    sub = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths" + "\\" + exe
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (0, winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(root, sub, 0, winreg.KEY_READ | view) as key:
                    path = winreg.QueryValueEx(key, None)[0].strip('"')
            except OSError:
                continue
            if path and os.path.exists(path):
                return path
    return ""


def _browser_binary():
    """Edge/Chrome fuer ein randloses Fenster: erst Registry, dann Standardpfade."""
    if os.name == "nt":
        for exe, parts in _WIN_APPS.items():
            found = _from_registry(exe)
            if found:
                return found
            for var in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
                root = os.environ.get(var)
                if root and os.path.exists(os.path.join(root, *parts)):
                    return os.path.join(root, *parts)
        return ""
    for path in ("/usr/bin/microsoft-edge", "/usr/bin/google-chrome",
                 "/usr/bin/chromium", "/usr/bin/chromium-browser"):
        if os.path.exists(path):
            return path
    return ""


def window_dir():
    base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else config_dir()
    return os.path.join(base or config_dir(), "weblab-window" if os.name == "nt" else "window")


def open_window(url, size=WINDOW):
    binary = _browser_binary()
    if binary:
        try:
            subprocess.Popen([binary, f"--app={url}", f"--window-size={size}",
                              f"--user-data-dir={window_dir()}", "--no-first-run",
                              "--no-default-browser-check"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return True
        except OSError:
            pass
    import webbrowser
    try:
        if webbrowser.open(url, new=1):
            return True
    except webbrowser.Error:
        pass
    if os.name == "nt":
        try:
            os.startfile(url)       # noqa: S606 - letzter Ausweg: Standardbrowser
            return True
        except OSError:
            pass
    return False


# ---------- Oberflaeche ----------
def dot(state):
    label = {"online": "erreichbar", "offline": "offline", "fehler": "Fehler"}.get(state, "prüfe …")
    cls = {"online": "run", "offline": "stop", "fehler": "err"}.get(state, "stop")
    return f'<span class="pill {cls}"><span class="dot"></span>{label}</span>'


def page(token, flash=""):
    rows = ""
    with _LOCK:
        known = dict(_STATUS)
    for index, entry in enumerate(servers()):
        state = (known.get(entry["url"]) or {}).get("state", "")
        rows += f"""<form method="post" action="/open?k={token}" class="item">
<input type="hidden" name="index" value="{index}">
<div class="item-main"><button class="linkish" type="submit">{ESC(entry['name'])}</button>
<div class="item-sub mono">{ESC(entry['url'])}</div></div>
<div class="item-side" data-url="{ESC(entry['url'])}">{dot(state)}</div>
</form>"""
    if not rows:
        rows = '<div class="item"><div class="item-main muted">Noch kein Server gespeichert.</div></div>'
    remove = ""
    if servers():
        options = "".join(f'<option value="{i}">{ESC(s["name"])}</option>'
                          for i, s in enumerate(servers()))
        remove = f"""<form method="post" action="/remove?k={token}" class="stack">
<label for="rm">Server entfernen</label>
<select id="rm" name="index">{options}</select>
<button class="btn danger" type="submit">Entfernen</button></form>"""
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{APP}</title><style>{CSS}
body{{background:var(--bg,#f2f2f7)}}
.wrap{{max-width:620px;margin:0 auto;padding:22px 16px 40px}}
.item{{display:flex;align-items:center;gap:12px;padding:12px 16px;min-height:56px;
 border-bottom:1px solid var(--line,#e5e5ea)}}
.item:last-child{{border-bottom:0}}
.item-main{{flex:1;min-width:0}}
.item-sub{{font-size:12.5px;color:var(--muted,#8a8a8e);overflow:hidden;text-overflow:ellipsis}}
.linkish{{background:none;border:0;padding:0;font:inherit;font-weight:600;font-size:16px;
 color:var(--ink,#000);cursor:pointer;text-align:left}}
.stack{{display:flex;flex-direction:column;gap:10px}}
.stack .btn{{align-self:flex-start}}
</style></head><body><div class="wrap">
<h1>Server</h1><p class="sub">Verwaltung im eigenen Fenster öffnen.</p>
{flash}
<div class="card" style="padding:0">{rows}</div>
<h2>Hinzufügen</h2>
<form class="card stack" method="post" action="/add?k={token}">
<div class="field"><label for="name">Name</label>
<input id="name" name="name" placeholder="Mein Server" required></div>
<div class="field"><label for="url">Adresse</label>
<input id="url" name="url" placeholder="kilge.com oder 203.0.113.10" required
 autocapitalize="off" autocorrect="off" spellcheck="false"></div>
<button class="btn primary" type="submit">Speichern</button></form>
{f'<h2>Verwalten</h2><div class="card">{remove}</div>' if remove else ''}
<h2>Neuer Server</h2>
<div class="card"><p class="help" style="margin:0 0 8px">Auf dem Server einmal ausführen:</p>
<pre>{ESC(INSTALL_CMD)}</pre></div>
</div>
<script>
(function(){{
 fetch('/api/status?k={token}').then(function(r){{return r.json()}}).then(function(d){{
  document.querySelectorAll('[data-url]').forEach(function(el){{
   var s=(d[el.getAttribute('data-url')]||{{}}).state;
   if(s)el.innerHTML=({{online:'<span class="pill run"><span class="dot"></span>erreichbar</span>',
    offline:'<span class="pill stop"><span class="dot"></span>offline</span>',
    fehler:'<span class="pill err"><span class="dot"></span>Fehler</span>'}})[s]||'';
  }});
 }}).catch(function(){{}});
}})();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "weblab-desktop"
    token = ""

    def log_message(self, *args):
        pass

    def _ok(self, body, ctype="text/html; charset=utf-8", status=200):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if (query.get("k") or [""])[0] != Handler.token:
            self._ok("verweigert", "text/plain; charset=utf-8", 403)
            return False
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlsplit(origin).hostname not in ("127.0.0.1", "localhost"):
            self._ok("verweigert", "text/plain; charset=utf-8", 403)
            return False
        return True

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/ping":
            return self._ok(PING, "text/plain; charset=utf-8")
        if not self._authorized():
            return None
        if path == "/api/status":
            return self._ok(json.dumps(refresh_status()), "application/json; charset=utf-8")
        return self._ok(page(Handler.token))

    def do_POST(self):
        if not self._authorized():
            return None
        path = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        form = {k: v[0] for k, v in urllib.parse.parse_qs(
            self.rfile.read(length).decode("utf-8", "replace"), keep_blank_values=True).items()}
        entries = servers()
        if path == "/add":
            url = normalize(form.get("url"))
            if url:
                entries.append({"name": (form.get("name") or url).strip(), "url": url})
                _write("servers.json", entries)
        elif path == "/remove":
            index = int(form.get("index") or -1)
            if 0 <= index < len(entries):
                del entries[index]
                _write("servers.json", entries)
        elif path == "/open":
            index = int(form.get("index") or -1)
            if 0 <= index < len(entries):
                open_window(entries[index]["url"], PANEL_WINDOW)
        self.send_response(303)
        self.send_header("Location", f"/?k={Handler.token}")
        self.end_headers()


def _running_instance():
    url = (_read("runtime.json", {}) or {}).get("url", "")
    if not url:
        return ""
    try:
        with urllib.request.urlopen(url.split("?")[0].rstrip("/") + "/ping", timeout=1.5) as resp:
            return url if resp.read().decode().strip() == PING else ""
    except (urllib.error.URLError, OSError, ValueError):
        return ""


def main():
    existing = _running_instance()
    if existing:
        open_window(existing)
        return 0
    Handler.token = secrets.token_urlsafe(16)
    httpd = None
    for port in PORTS:
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if httpd is None:
        print("Kein freier Port für die Oberfläche gefunden.")
        return 1
    url = f"http://127.0.0.1:{httpd.server_port}/?k={Handler.token}"
    _write("runtime.json", {"url": url, "pid": os.getpid()}, private=True)
    threading.Thread(target=refresh_status, daemon=True).start()
    open_window(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
