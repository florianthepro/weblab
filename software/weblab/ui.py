"""HTML-Oberfläche: Layout, Formulare aus Connector-Feldern, Seitenbausteine."""
import html
import json

TABS = [
    ("/", "Dashboard", "◧"),
    ("/apps", "Apps", "▦"),
    ("/network", "Netzwerk", "⇄"),
    ("/storage", "Speicher", "▤"),
    ("/users", "Benutzer", "◉"),
]

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
 --bg:#f7f8fa; --panel:#fff; --panel-2:#fbfcfd;
 --ink:#101317; --ink-2:#3d4652; --muted:#6b7480; --line:#e5e8ec; --line-2:#eef0f3;
 --accent:#2563eb; --accent-ink:#fff; --accent-soft:#eff4ff;
 --ok:#0f7a52; --warn:#a86610; --bad:#c0362c;
 --r:10px; --r-sm:7px;
 --sh:0 1px 2px rgba(16,20,28,.05);
 --sh-2:0 1px 3px rgba(16,20,28,.06),0 8px 24px -12px rgba(16,20,28,.18);
 --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
 --bg:#0d1014; --panel:#15191f; --panel-2:#1a1f26;
 --ink:#e9ecf0; --ink-2:#c2c9d3; --muted:#8f99a6; --line:#252b34; --line-2:#1f242c;
 --accent:#6d9bff; --accent-ink:#0d1014; --accent-soft:#182236;
 --ok:#3fca92; --warn:#e2a640; --bad:#f07166;
 --sh:0 1px 2px rgba(0,0,0,.5);
 --sh-2:0 1px 3px rgba(0,0,0,.5),0 10px 28px -14px rgba(0,0,0,.7);}}

html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-size:15px;line-height:1.55;
 font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline;text-underline-offset:2px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}

/* Grundgerüst */
.layout{display:grid;grid-template-columns:230px 1fr;min-height:100vh}
.side{background:var(--panel);border-right:1px solid var(--line);padding:20px 14px;
 position:sticky;top:0;height:100vh;overflow:auto;display:flex;flex-direction:column}
.brand{font-weight:660;font-size:16px;letter-spacing:-.02em;padding:2px 10px 20px}
.brand small{display:block;font-weight:450;font-size:11.5px;color:var(--muted);
 letter-spacing:.02em;margin-top:2px}
.nav{display:flex;flex-direction:column;gap:1px}
.nav a{display:flex;gap:11px;align-items:center;padding:8px 10px;border-radius:var(--r-sm);
 color:var(--ink-2);font-size:14px;font-weight:500;transition:background .12s,color .12s}
.nav a:hover{background:var(--line-2);color:var(--ink);text-decoration:none}
.nav a.on{background:var(--accent-soft);color:var(--accent);font-weight:600}
.nav .ic{width:16px;text-align:center;font-size:13px;opacity:.9}
.whoami{margin-top:auto;padding:12px 10px 2px;border-top:1px solid var(--line);
 font-size:12.5px;color:var(--muted);line-height:1.7}
.whoami b{color:var(--ink-2);font-weight:600}
.main{padding:30px 34px 72px;max-width:1240px}

/* Typografie */
h1{font-size:22px;font-weight:640;margin:0 0 5px;letter-spacing:-.025em}
h2{font-size:13px;font-weight:640;margin:30px 0 11px;letter-spacing:.03em;
 text-transform:uppercase;color:var(--muted)}
h3{font-size:14.5px;font-weight:620;margin:0 0 10px;letter-spacing:-.01em}
.sub{color:var(--muted);margin:0 0 22px;font-size:14px}
.muted{color:var(--muted)}
code,.mono{font-family:var(--mono);font-size:12.5px}

/* Flächen */
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);
 padding:16px 18px;box-shadow:var(--sh)}
.grid{display:grid;gap:13px}
.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
.g3{grid-template-columns:repeat(3,minmax(0,1fr))}
.g4{grid-template-columns:repeat(4,minmax(0,1fr))}
@media(max-width:1080px){.g3,.g4{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:820px){.layout{grid-template-columns:1fr}
 .side{position:static;height:auto;flex-direction:column}
 .g2,.g3,.g4{grid-template-columns:1fr}.main{padding:22px 18px 56px}}

/* Kennzahlen */
.stat .k{color:var(--muted);font-size:11.5px;font-weight:600;letter-spacing:.05em;
 text-transform:uppercase}
.stat .v{font-size:27px;font-weight:640;letter-spacing:-.03em;margin:5px 0 9px;
 font-variant-numeric:tabular-nums;line-height:1.1}
.bar{height:5px;background:var(--line);border-radius:99px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--accent);border-radius:99px;
 transition:width .4s ease}
.bar.ok>i{background:var(--ok)}.bar.warn>i{background:var(--warn)}.bar.bad>i{background:var(--bad)}

/* Tabellen */
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line-2);
 vertical-align:middle}
th{font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
 font-weight:600;border-bottom-color:var(--line)}
tbody tr:last-child td,tr:last-child td{border-bottom:0}
table tr:hover td{background:var(--panel-2)}
.tbl-wrap{overflow-x:auto;margin:0 -18px;padding:0 18px}

/* Zustände */
.pill{display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:99px;
 font-size:11.5px;font-weight:600;background:var(--panel-2);border:1px solid var(--line);
 color:var(--muted);white-space:nowrap}
.pill.run{color:var(--ok);background:color-mix(in srgb,var(--ok) 9%,transparent);
 border-color:color-mix(in srgb,var(--ok) 28%,var(--line))}
.pill.stop{color:var(--muted)}
.pill.err{color:var(--bad);background:color-mix(in srgb,var(--bad) 9%,transparent);
 border-color:color-mix(in srgb,var(--bad) 28%,var(--line))}
.dot{width:6px;height:6px;border-radius:99px;background:currentColor;display:inline-block}

/* Schaltflächen */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;
 padding:8px 14px;border-radius:var(--r-sm);border:1px solid var(--line);
 background:var(--panel);color:var(--ink);font:inherit;font-size:13.5px;font-weight:550;
 cursor:pointer;white-space:nowrap;transition:background .12s,border-color .12s,filter .12s}
.btn:hover{background:var(--panel-2);border-color:var(--muted);text-decoration:none}
.btn:active{transform:translateY(.5px)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.btn.primary:hover{filter:brightness(1.08);background:var(--accent)}
.btn.danger{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 30%,var(--line))}
.btn.danger:hover{background:color-mix(in srgb,var(--bad) 9%,var(--panel))}
.btn.sm{padding:4px 10px;font-size:12.5px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.between{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}

/* Formulare */
label{display:block;font-size:13px;font-weight:600;margin:0 0 6px;color:var(--ink-2)}
.help{font-size:12.5px;color:var(--muted);margin:5px 0 0;font-weight:400;line-height:1.5}
input,select,textarea{width:100%;padding:8px 11px;border:1px solid var(--line);
 border-radius:var(--r-sm);background:var(--panel);color:var(--ink);font:inherit;
 font-size:14px;transition:border-color .12s,box-shadow .12s}
input:hover,select:hover,textarea:hover{border-color:var(--muted)}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--accent);
 box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 16%,transparent)}
input[type=checkbox]{width:auto;margin:0;accent-color:var(--accent)}
input[type=file]{padding:7px 10px;font-size:13px}
select{cursor:pointer}
.field{margin-bottom:15px}
.field:last-child{margin-bottom:0}
.check{display:flex;gap:9px;align-items:center}.check label{margin:0}

/* Meldungen */
.msg{padding:11px 14px;border-radius:var(--r-sm);margin-bottom:18px;font-size:13.5px;
 border:1px solid;line-height:1.5}
.msg.ok{background:color-mix(in srgb,var(--ok) 8%,var(--panel));
 border-color:color-mix(in srgb,var(--ok) 26%,var(--line));color:var(--ok)}
.msg.err{background:color-mix(in srgb,var(--bad) 8%,var(--panel));
 border-color:color-mix(in srgb,var(--bad) 26%,var(--line));color:var(--bad)}

/* Fehler-Banner: bleibt auf allen Seiten, bis es geschlossen wird */
.banner{display:flex;align-items:center;gap:12px;padding:11px 14px;border-radius:var(--r-sm);
 margin-bottom:16px;font-size:13.5px;line-height:1.5;border:1px solid;
 background:color-mix(in srgb,var(--bad) 8%,var(--panel));
 border-color:color-mix(in srgb,var(--bad) 26%,var(--line));color:var(--bad)}
.banner .txt{flex:1;min-width:0}
.banner button{background:none;border:0;color:inherit;font-size:19px;line-height:1;
 cursor:pointer;opacity:.65;padding:0 2px}
.banner button:hover{opacity:1}

/* Aufklappbare Bereiche */
details.sec{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);
 box-shadow:var(--sh);margin-bottom:13px}
details.sec>summary{list-style:none;cursor:pointer;padding:15px 18px;font-weight:600;
 font-size:14px;display:flex;align-items:center;justify-content:space-between;gap:10px}
details.sec>summary::-webkit-details-marker{display:none}
details.sec>summary::after{content:"⌄";color:var(--muted);font-size:15px;line-height:1}
details.sec[open]>summary::after{content:"⌃"}
details.sec[open]>summary{border-bottom:1px solid var(--line)}
details.sec>.in{padding:16px 18px}
.badge{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11.5px;font-weight:600;
 background:color-mix(in srgb,var(--accent) 12%,var(--panel));color:var(--accent);
 border:1px solid color-mix(in srgb,var(--accent) 28%,var(--line))}
.sub-in{max-width:210px}

/* Katalog */
.apps{display:grid;gap:13px;grid-template-columns:repeat(auto-fill,minmax(272px,1fr))}
.appcard{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);
 padding:16px;box-shadow:var(--sh);display:flex;flex-direction:column;gap:11px;
 transition:border-color .14s,box-shadow .14s,transform .14s}
.appcard:hover{border-color:color-mix(in srgb,var(--accent) 34%,var(--line));
 box-shadow:var(--sh-2);transform:translateY(-1px)}
.appcard .ico{font-size:22px;line-height:1;width:38px;height:38px;flex:0 0 38px;
 display:grid;place-items:center;background:var(--panel-2);border:1px solid var(--line);
 border-radius:9px}
.appcard .nm{font-weight:620;font-size:14.5px;letter-spacing:-.01em}
.appcard .sm{color:var(--muted);font-size:13px;flex:1;line-height:1.5}

/* Reiter */
.tabs{display:flex;gap:2px;border-bottom:1px solid var(--line);margin:0 0 22px;
 overflow-x:auto}
.tabs a{padding:9px 13px;font-size:13.5px;font-weight:550;color:var(--muted);
 border-bottom:2px solid transparent;white-space:nowrap;margin-bottom:-1px;
 transition:color .12s,border-color .12s}
.tabs a:hover{color:var(--ink);text-decoration:none}
.tabs a.on{color:var(--accent);border-bottom-color:var(--accent);font-weight:600}

/* Sonstiges */
pre{background:var(--panel-2);border:1px solid var(--line);border-radius:var(--r-sm);
 padding:13px 15px;overflow:auto;font-family:var(--mono);font-size:12.5px;
 max-height:480px;margin:0;line-height:1.6}
textarea{font-family:var(--mono);line-height:1.6;resize:vertical}
.kv{display:grid;grid-template-columns:auto 1fr;gap:9px 20px;font-size:14px;margin:0}
.kv dt{color:var(--muted);font-size:13px}
.kv dd{margin:0;min-width:0;overflow-wrap:anywhere}

/* Anmeldung / Einrichtung */
.center{min-height:100vh;display:grid;place-items:center;padding:28px}
.box{width:100%;max-width:432px}
.box .card{padding:26px 26px 24px;box-shadow:var(--sh-2)}
.box h1{font-size:20px;margin-bottom:4px}
.steps{display:flex;gap:6px;margin:0 0 22px;font-size:12px}
.steps div{flex:1;padding:7px 8px;border-radius:var(--r-sm);background:var(--panel-2);
 border:1px solid var(--line);text-align:center;color:var(--muted);font-weight:550}
.steps div.on{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
.steps div.done{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 30%,var(--line))}
.progress{height:6px;background:var(--line);border-radius:99px;overflow:hidden;margin:20px 0 8px}
.progress>i{display:block;height:100%;width:0;background:var(--accent);border-radius:99px;
 transition:width .5s ease}

/* Gesperrte Felder */
.field.locked > input,.field.locked > select,.field.locked > textarea{
 border-color:var(--bad);background:color-mix(in srgb,var(--bad) 6%,var(--panel));
 color:var(--muted);cursor:not-allowed}
.field.unlocked > input,.field.unlocked > select,.field.unlocked > textarea{
 border-color:var(--warn);box-shadow:0 0 0 3px color-mix(in srgb,var(--warn) 16%,transparent)}
.lockrow{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 0 6px}
.lockrow label{margin:0}
.locktag{font-size:11px;color:var(--bad);font-weight:600;white-space:nowrap}
.lockbtn{font-size:11.5px;font-weight:600;color:var(--bad);background:none;border:1px solid
 color-mix(in srgb,var(--bad) 30%,var(--line));border-radius:99px;padding:1px 9px;cursor:pointer}
.lockbtn:hover{background:color-mix(in srgb,var(--bad) 8%,var(--panel))}
.readonly-val{padding:8px 11px;border:1px solid var(--line);border-radius:var(--r-sm);
 background:var(--panel-2);color:var(--ink-2);font-size:14px;display:flex;
 justify-content:space-between;align-items:center;gap:8px}

/* Info-Overlay */
.infobtn{position:fixed;right:18px;bottom:18px;z-index:60;width:42px;height:42px;
 border-radius:50%;border:1px solid var(--line);background:var(--panel);color:var(--accent);
 font-size:19px;font-weight:700;cursor:pointer;box-shadow:var(--sh-2);line-height:1}
.infobtn:hover{background:var(--panel-2)}
.infopanel{position:fixed;right:18px;bottom:70px;z-index:60;width:310px;
 max-width:calc(100vw - 36px);background:var(--panel);border:1px solid var(--line);
 border-radius:var(--r);box-shadow:var(--sh-2);padding:14px 16px;display:none}
.infopanel.show{display:block}
.infopanel h4{margin:0 0 6px;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;
 color:var(--muted)}
.infopanel .ibody{font-size:13px;line-height:1.55;color:var(--ink-2)}

/* Dialog */
dialog{border:1px solid var(--line);border-radius:var(--r);padding:0;
 max-width:min(720px,94vw);width:100%;background:var(--panel);color:var(--ink);
 box-shadow:var(--sh-2)}
dialog::backdrop{background:rgba(8,11,15,.5)}
dialog .dhead{display:flex;justify-content:space-between;align-items:center;
 padding:15px 18px;border-bottom:1px solid var(--line)}
dialog .dhead h3{margin:0}
dialog .dbody{padding:18px;max-height:76vh;overflow:auto}
dialog .x{background:none;border:0;font-size:22px;line-height:1;cursor:pointer;color:var(--muted)}
dialog .x:hover{color:var(--ink)}
.chip{display:inline-flex;align-items:center;gap:8px;padding:5px 6px 5px 12px;border-radius:99px;
 border:1px solid var(--line);background:var(--panel-2);font-size:13px;margin:0 6px 6px 0}
.acctrow{border:1px solid var(--line);border-radius:var(--r-sm);padding:11px 14px;
 background:var(--panel-2);margin-bottom:8px}
"""


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def _bar_class(percent):
    return "bad" if percent >= 90 else "warn" if percent >= 75 else "ok"


def banner_html(text, token=""):
    """Fehler-Banner, bleibt bis zum Schließen auf jeder Seite."""
    if not text:
        return ""
    return (f'<div class="banner"><span class="txt">{esc(text)}</span>'
            f'<form method="post" action="/banner"><input type="hidden" name="csrf" '
            f'value="{esc(token)}"><button type="submit" aria-label="Schließen">&times;</button>'
            f'</form></div>')


def section(title, inner, open_=False, note=""):
    """Aufklappbarer Bereich."""
    tag = f'<span class="muted" style="font-weight:400">{esc(note)}</span>' if note else ""
    return (f'<details class="sec"{" open" if open_ else ""}>'
            f'<summary>{esc(title)}{tag}</summary><div class="in">{inner}</div></details>')


def page(title, body, active="/", user=None, flash=None, head="", banner="", is_admin=True):
    tabs = TABS if is_admin else [t for t in TABS if t[0] == "/apps"]
    nav = "".join(
        f'<a class="{"on" if path == active else ""}" href="{path}">'
        f'<span class="ic">{icon}</span>{esc(label)}</a>'
        for path, label, icon in tabs)
    msg = ""
    if flash:
        kind, text = flash
        msg = f'<div class="msg {esc(kind)}">{esc(text)}</div>'
    who = ""
    if user:
        who = (f'<div class="whoami">{esc(user)}<br>'
               f'<a href="/logout">Abmelden</a></div>')
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} — weblab</title><style>{CSS}</style>{head}</head>
<body><div class="layout"><aside class="side">
<div class="brand">weblab<small>Server-Verwaltung</small></div>
<nav class="nav">{nav}</nav>{who}</aside>
<main class="main">{banner}{msg}{body}</main></div>{GLOBAL_JS}</body></html>"""


def bare(title, body, head=""):
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} — weblab</title><style>{CSS}</style>{head}</head>
<body><div class="center">{body}</div>{GLOBAL_JS}</body></html>"""


def stat(label, value, percent=None, note=""):
    bar = ""
    if percent is not None:
        bar = (f'<div class="bar {_bar_class(percent)}">'
               f'<i style="width:{max(0, min(100, percent)):.1f}%"></i></div>')
    sub = f'<div class="help">{esc(note)}</div>' if note else ""
    return (f'<div class="card stat"><div class="k">{esc(label)}</div>'
            f'<div class="v">{esc(value)}</div>{bar}{sub}</div>')


def status_pill(state):
    if state == "running":
        return '<span class="pill run"><span class="dot"></span>läuft</span>'
    if state in ("exited", "created", "paused"):
        return '<span class="pill stop"><span class="dot"></span>gestoppt</span>'
    if state == "missing":
        return '<span class="pill err"><span class="dot"></span>fehlt</span>'
    return f'<span class="pill err"><span class="dot"></span>{esc(state)}</span>'


def _info_attr(text):
    return f' data-info="{esc(text)}"' if text else ""


def _label_row(key, label, locked):
    """Label-Zeile; bei gesperrten Feldern mit rotem Hinweis und Freischalten-Knopf."""
    if locked:
        return (f'<div class="lockrow"><label for="{esc(key)}">{esc(label)} '
                f'<span class="locktag">🔒 im Betrieb gesperrt</span></label>'
                f'<button type="button" class="lockbtn" data-unlock="{esc(key)}">'
                f'Freischalten</button></div>')
    return f'<label for="{esc(key)}">{esc(label)}</label>'


def field_input(field, value, prefix="", locked=False):
    """Ein Formularfeld aus der Connector-Definition rendern.

    locked: Feld ist im Betrieb nicht änderbar (gesperrt, rot; erst freischalten).
    Der Hilfetext des Feldes wandert ins Info-Overlay (data-info).
    """
    key = prefix + field["key"]
    ftype = field.get("type", "string")
    label = field.get("label", field["key"])
    locked = locked or field.get("locked", False)
    required = "" if locked else (" required" if field.get("required") else "")
    dis = " disabled" if locked else ""
    info = _info_attr(field.get("help", ""))
    depends = ""
    if field.get("depends_on"):
        depends = f' data-depends=\'{html.escape(json.dumps(field["depends_on"]), quote=True)}\''
    wrap = "field locked" if locked else "field"

    if ftype == "bool":
        checked = " checked" if value else ""
        locktag = '<span class="locktag">🔒</span>' if locked else ""
        lockbtn = (f'<button type="button" class="lockbtn" data-unlock="{esc(key)}">'
                   f'Freischalten</button>') if locked else ""
        control = (f'<div class="check"><input type="checkbox" id="{esc(key)}" '
                   f'name="{esc(key)}" value="1"{checked}{dis}{info}>'
                   f'<label for="{esc(key)}">{esc(label)} {locktag}</label>{lockbtn}'
                   f'</div>')
        return f'<div class="{wrap}"{depends}>{control}</div>'

    if ftype == "select":
        labels = field.get("option_labels", {})
        options = "".join(
            f'<option value="{esc(opt)}"{" selected" if str(value) == str(opt) else ""}>'
            f'{esc(labels.get(opt, opt))}</option>' for opt in field.get("options", []))
        control = f'<select id="{esc(key)}" name="{esc(key)}"{dis}{info}>{options}</select>'
    elif ftype == "number":
        attrs = ""
        for attr in ("min", "max", "step"):
            if attr in field:
                attrs += f' {attr}="{esc(field[attr])}"'
        control = (f'<input type="number" id="{esc(key)}" name="{esc(key)}" '
                   f'value="{esc(value)}"{attrs}{required}{dis}{info}>')
    elif ftype == "password":
        control = (f'<input type="password" id="{esc(key)}" name="{esc(key)}" '
                   f'value="" autocomplete="new-password"{required}{dis}{info}>')
    elif ftype == "textarea":
        control = (f'<textarea id="{esc(key)}" name="{esc(key)}" rows="5"{dis}{info}>'
                   f'{esc(value)}</textarea>')
    else:
        control = (f'<input type="text" id="{esc(key)}" name="{esc(key)}" '
                   f'value="{esc(value)}"{required}{dis}{info}>')
    return f'<div class="{wrap}"{depends}>{_label_row(key, label, locked)}{control}</div>'


def select_field(key, label, options, value, help_text="", option_labels=None, locked=False):
    option_labels = option_labels or {}
    opts = "".join(
        f'<option value="{esc(o)}"{" selected" if str(value) == str(o) else ""}>'
        f'{esc(option_labels.get(o, o))}</option>' for o in options)
    dis = " disabled" if locked else ""
    wrap = "field locked" if locked else "field"
    return (f'<div class="{wrap}">{_label_row(key, label, locked)}'
            f'<select id="{esc(key)}" name="{esc(key)}"{dis}{_info_attr(help_text)}>'
            f'{opts}</select></div>')


def readonly_field(label, value, note=""):
    """Nicht änderbarer Wert (z. B. Version) — nur Anzeige."""
    tag = f'<span class="locktag">🔒 {esc(note)}</span>' if note else ""
    return (f'<div class="field"><label>{esc(label)}</label>'
            f'<div class="readonly-val"><span class="mono">{esc(value)}</span>{tag}</div></div>')


def csrf_input(token):
    return f'<input type="hidden" name="csrf" value="{esc(token)}">'


def modal(dialog_id, title, inner):
    """Ein per Knopf öffnendes Overlay (<dialog>)."""
    return (f'<dialog id="{esc(dialog_id)}"><div class="dhead"><h3>{esc(title)}</h3>'
            f'<button class="x" type="button" onclick="this.closest(\'dialog\').close()"'
            f' aria-label="Schließen">&times;</button></div>'
            f'<div class="dbody">{inner}</div></dialog>')


def open_button(dialog_id, label, cls="btn primary"):
    return (f'<button type="button" class="{cls}" '
            f'onclick="document.getElementById(\'{esc(dialog_id)}\').showModal()">{esc(label)}</button>')


DEPENDS_JS = ""  # Interaktive Logik liegt global in GLOBAL_JS (page/bare).

INFO_OVERLAY = ""  # entfernt: aufgeraeumtes Interface ohne Hinweis-Overlay

GLOBAL_JS = """<script>
(function(){
 // Gesperrte Felder freischalten
 document.querySelectorAll('[data-unlock]').forEach(function(b){
  b.addEventListener('click',function(){
   var f=document.getElementById(b.getAttribute('data-unlock'));if(!f)return;
   var wrap=f.closest('.field');
   if(f.disabled){f.disabled=false;f.focus();if(wrap){wrap.classList.remove('locked');wrap.classList.add('unlocked');}
     b.textContent='Sperren';
   }else{f.disabled=true;if(wrap){wrap.classList.add('locked');wrap.classList.remove('unlocked');}
     b.textContent='Freischalten';}
  });
 });
 // Abhängige Felder (depends_on)
 var deps=[].slice.call(document.querySelectorAll('[data-depends]'));
 function sync(){deps.forEach(function(el){
   var cond=JSON.parse(el.getAttribute('data-depends')),show=true;
   Object.keys(cond).forEach(function(k){var s=document.querySelector('[name="'+k+'"]');
     if(s&&String(s.value)!==String(cond[k]))show=false;});
   el.style.display=show?'':'none';});}
 document.querySelectorAll('select,input').forEach(function(e){e.addEventListener('change',sync);});
 sync();
 // Domain zusammensetzen (Subdomain + Zone -> verstecktes Feld 'domain')
 document.querySelectorAll('[data-domain-widget]').forEach(function(w){
  var sub=w.querySelector('[data-domain-sub]'),zone=w.querySelector('[data-domain-zone]'),
      out=w.querySelector('[data-domain-out]');
  var prev=w.querySelector('[data-domain-preview]');
  function upd(){if(!out)return;var z=zone?zone.value:'';var s=sub?sub.value.trim():'';
   out.value=z?(s?s+'.'+z:z):''; if(prev)prev.textContent=out.value?'→ '+out.value:'';}
  if(sub)sub.addEventListener('input',upd);if(zone)zone.addEventListener('change',upd);upd();
 });
})();
</script>"""
