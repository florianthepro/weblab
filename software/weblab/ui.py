"""HTML-Oberfläche: Layout, Formulare aus Connector-Feldern, Seitenbausteine."""
import html
import json

TABS = [
    ("/", "Dashboard", "◧"),
    ("/apps", "Apps", "▦"),
    ("/network", "Netzwerk", "⇄"),
    ("/dns", "DNS", "◎"),
    ("/storage", "Speicher", "▤"),
    ("/users", "Benutzer", "◉"),
    ("/settings", "Einstellungen", "⚙"),
]

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
 --bg:#f5f6f8; --panel:#fff; --ink:#12151a; --muted:#5f6773; --line:#e3e6ea;
 --accent:#2f6bff; --accent-ink:#fff; --ok:#12855b; --warn:#b06d00; --bad:#c8352b;
 --radius:10px; --shadow:0 1px 2px rgba(16,20,28,.06),0 4px 14px rgba(16,20,28,.05);
 --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
 --bg:#0f1216; --panel:#161a20; --ink:#e8ebef; --muted:#98a2b0; --line:#252b34;
 --accent:#5b8cff; --ok:#35c48b; --warn:#e0a33a; --bad:#ef6d63;
 --shadow:0 1px 2px rgba(0,0,0,.4),0 4px 16px rgba(0,0,0,.3);}}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.layout{display:grid;grid-template-columns:232px 1fr;min-height:100vh}
.side{background:var(--panel);border-right:1px solid var(--line);padding:18px 12px;
 position:sticky;top:0;height:100vh;overflow:auto}
.brand{font-weight:700;font-size:17px;padding:6px 10px 16px;letter-spacing:-.01em}
.brand small{display:block;font-weight:400;font-size:12px;color:var(--muted);letter-spacing:0}
.nav a{display:flex;gap:10px;align-items:center;padding:9px 10px;border-radius:8px;
 color:var(--ink);font-size:14px;margin-bottom:2px}
.nav a:hover{background:var(--bg);text-decoration:none}
.nav a.on{background:var(--accent);color:var(--accent-ink);font-weight:600}
.nav .ic{width:18px;text-align:center;opacity:.85}
.main{padding:26px 30px 60px;max-width:1220px}
h1{font-size:23px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:16px;margin:26px 0 10px;letter-spacing:-.01em}
h3{font-size:14px;margin:0 0 8px}
.sub{color:var(--muted);margin:0 0 20px;font-size:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
 padding:16px 18px;box-shadow:var(--shadow)}
.grid{display:grid;gap:14px}
.g2{grid-template-columns:repeat(2,1fr)}.g3{grid-template-columns:repeat(3,1fr)}
.g4{grid-template-columns:repeat(4,1fr)}
@media(max-width:1000px){.g3,.g4{grid-template-columns:repeat(2,1fr)}
 .layout{grid-template-columns:1fr}.side{position:static;height:auto}}
.stat .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.stat .v{font-size:26px;font-weight:650;letter-spacing:-.02em;margin:4px 0 6px}
.bar{height:6px;background:var(--line);border-radius:99px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--accent);border-radius:99px}
.bar.ok>i{background:var(--ok)}.bar.warn>i{background:var(--warn)}.bar.bad>i{background:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:middle}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600}
tr:last-child td{border-bottom:0}
.tbl-wrap{overflow-x:auto}
.pill{display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:99px;
 font-size:12px;font-weight:600;background:var(--bg);border:1px solid var(--line)}
.pill.run{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 35%,var(--line))}
.pill.stop{color:var(--muted)}
.pill.err{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 35%,var(--line))}
.dot{width:7px;height:7px;border-radius:99px;background:currentColor;display:inline-block}
.btn{display:inline-block;padding:8px 14px;border-radius:8px;border:1px solid var(--line);
 background:var(--panel);color:var(--ink);font:inherit;font-size:14px;font-weight:550;cursor:pointer}
.btn:hover{background:var(--bg);text-decoration:none}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{filter:brightness(1.07)}
.btn.danger{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 35%,var(--line))}
.btn.sm{padding:5px 10px;font-size:13px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.between{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}
label{display:block;font-size:13px;font-weight:600;margin:0 0 5px}
.help{font-size:12px;color:var(--muted);margin:4px 0 0;font-weight:400}
input,select,textarea{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:8px;
 background:var(--panel);color:var(--ink);font:inherit;font-size:14px}
input:focus,select:focus,textarea:focus{outline:2px solid color-mix(in srgb,var(--accent) 45%,transparent);
 outline-offset:1px;border-color:var(--accent)}
input[type=checkbox]{width:auto;margin:0}
.field{margin-bottom:14px}
.check{display:flex;gap:9px;align-items:center}.check label{margin:0}
.msg{padding:11px 14px;border-radius:8px;margin-bottom:16px;font-size:14px;border:1px solid}
.msg.ok{background:color-mix(in srgb,var(--ok) 10%,var(--panel));border-color:color-mix(in srgb,var(--ok) 35%,var(--line));color:var(--ok)}
.msg.err{background:color-mix(in srgb,var(--bad) 10%,var(--panel));border-color:color-mix(in srgb,var(--bad) 35%,var(--line));color:var(--bad)}
.apps{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}
.appcard{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
 padding:16px;box-shadow:var(--shadow);display:flex;flex-direction:column;gap:10px}
.appcard .ico{font-size:26px;line-height:1}
.appcard .nm{font-weight:650;font-size:15px}
.appcard .sm{color:var(--muted);font-size:13px;flex:1}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:0 0 20px;overflow-x:auto}
.tabs a{padding:9px 14px;font-size:14px;font-weight:550;color:var(--muted);
 border-bottom:2px solid transparent;white-space:nowrap}
.tabs a:hover{color:var(--ink);text-decoration:none}
.tabs a.on{color:var(--accent);border-bottom-color:var(--accent)}
code,.mono{font-family:var(--mono);font-size:13px}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;
 overflow:auto;font-family:var(--mono);font-size:12.5px;max-height:460px;margin:0}
.center{min-height:100vh;display:grid;place-items:center;padding:24px}
.box{width:100%;max-width:460px}
.steps{display:flex;gap:8px;margin-bottom:22px;font-size:13px}
.steps div{flex:1;padding:8px 10px;border-radius:8px;background:var(--bg);
 border:1px solid var(--line);text-align:center;color:var(--muted)}
.steps div.on{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
.steps div.done{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 35%,var(--line))}
.progress{height:8px;background:var(--line);border-radius:99px;overflow:hidden;margin:18px 0}
.progress>i{display:block;height:100%;width:0;background:var(--accent);border-radius:99px;
 transition:width .5s ease}
.muted{color:var(--muted)}
.kv{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;font-size:14px}
.kv dt{color:var(--muted)}.kv dd{margin:0}
"""


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def _bar_class(percent):
    return "bad" if percent >= 90 else "warn" if percent >= 75 else "ok"


def page(title, body, active="/", user=None, flash=None, head=""):
    nav = "".join(
        f'<a class="{"on" if path == active else ""}" href="{path}">'
        f'<span class="ic">{icon}</span>{esc(label)}</a>'
        for path, label, icon in TABS)
    msg = ""
    if flash:
        kind, text = flash
        msg = f'<div class="msg {esc(kind)}">{esc(text)}</div>'
    who = ""
    if user:
        who = (f'<div style="margin-top:18px;padding:10px;border-top:1px solid var(--line);'
               f'font-size:13px;color:var(--muted)">Angemeldet: <b>{esc(user)}</b><br>'
               f'<a href="/logout">Abmelden</a></div>')
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} — weblab</title><style>{CSS}</style>{head}</head>
<body><div class="layout"><aside class="side">
<div class="brand">weblab<small>Server-Verwaltung</small></div>
<nav class="nav">{nav}</nav>{who}</aside>
<main class="main">{msg}{body}</main></div></body></html>"""


def bare(title, body, head=""):
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} — weblab</title><style>{CSS}</style>{head}</head>
<body><div class="center">{body}</div></body></html>"""


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


def field_input(field, value, prefix=""):
    """Ein Formularfeld aus der Connector-Definition rendern."""
    key = prefix + field["key"]
    ftype = field.get("type", "string")
    label = field.get("label", field["key"])
    required = " required" if field.get("required") else ""
    help_html = f'<p class="help">{esc(field["help"])}</p>' if field.get("help") else ""
    depends = ""
    if field.get("depends_on"):
        depends = f' data-depends=\'{html.escape(json.dumps(field["depends_on"]), quote=True)}\''

    if ftype == "bool":
        checked = " checked" if value else ""
        control = (f'<div class="check"><input type="checkbox" id="{esc(key)}" '
                   f'name="{esc(key)}" value="1"{checked}>'
                   f'<label for="{esc(key)}">{esc(label)}</label></div>')
        return f'<div class="field"{depends}>{control}{help_html}</div>'

    if ftype == "select":
        labels = field.get("option_labels", {})
        options = "".join(
            f'<option value="{esc(opt)}"{" selected" if str(value) == str(opt) else ""}>'
            f'{esc(labels.get(opt, opt))}</option>' for opt in field.get("options", []))
        control = f'<select id="{esc(key)}" name="{esc(key)}">{options}</select>'
    elif ftype == "number":
        attrs = ""
        for attr in ("min", "max", "step"):
            if attr in field:
                attrs += f' {attr}="{esc(field[attr])}"'
        control = (f'<input type="number" id="{esc(key)}" name="{esc(key)}" '
                   f'value="{esc(value)}"{attrs}{required}>')
    elif ftype == "password":
        control = (f'<input type="password" id="{esc(key)}" name="{esc(key)}" '
                   f'value="" autocomplete="new-password"{required}>')
    elif ftype == "textarea":
        control = f'<textarea id="{esc(key)}" name="{esc(key)}" rows="5">{esc(value)}</textarea>'
    else:
        control = (f'<input type="text" id="{esc(key)}" name="{esc(key)}" '
                   f'value="{esc(value)}"{required}>')
    return (f'<div class="field"{depends}><label for="{esc(key)}">{esc(label)}</label>'
            f'{control}{help_html}</div>')


def select_field(key, label, options, value, help_text="", option_labels=None):
    option_labels = option_labels or {}
    opts = "".join(
        f'<option value="{esc(o)}"{" selected" if str(value) == str(o) else ""}>'
        f'{esc(option_labels.get(o, o))}</option>' for o in options)
    help_html = f'<p class="help">{esc(help_text)}</p>' if help_text else ""
    return (f'<div class="field"><label for="{esc(key)}">{esc(label)}</label>'
            f'<select id="{esc(key)}" name="{esc(key)}">{opts}</select>{help_html}</div>')


def csrf_input(token):
    return f'<input type="hidden" name="csrf" value="{esc(token)}">'


DEPENDS_JS = """<script>
document.addEventListener('DOMContentLoaded',function(){
 var fields=[].slice.call(document.querySelectorAll('[data-depends]'));
 function sync(){fields.forEach(function(el){
   var cond=JSON.parse(el.getAttribute('data-depends'));var show=true;
   Object.keys(cond).forEach(function(k){
     var src=document.querySelector('[name="'+k+'"]');
     if(src&&String(src.value)!==String(cond[k]))show=false;});
   el.style.display=show?'':'none';});}
 document.querySelectorAll('select,input').forEach(function(el){
   el.addEventListener('change',sync);});
 sync();});
</script>"""
