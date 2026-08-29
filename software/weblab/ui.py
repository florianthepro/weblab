"""Oberflaeche: Design-System, Layout, Formulare, Seitenbausteine."""
import hashlib
import html
import json

ICONS = {
    "start": "M3 10.5 12 4l9 6.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
    "apps": "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
    "domains": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9S14.5 18.4 12 21"
               "c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3",
    "more": "M6 12h.01M12 12h.01M18 12h.01",
}
TABS = [
    ("/", "Start", "start"),
    ("/apps", "Apps", "apps"),
    ("/domains", "Domains", "domains"),
    ("/mehr", "Mehr", "more"),
]
USER_TABS = [("/apps", "Apps", "apps"), ("/mehr", "Mehr", "more")]

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
 --bg:#f2f2f7; --surface:#fff; --surface-2:#f2f2f7; --raised:#fff;
 --ink:#000; --ink-2:rgba(60,60,67,.78); --muted:rgba(60,60,67,.6);
 --line:rgba(60,60,67,.29); --line-2:rgba(60,60,67,.14);
 --accent:#0088ff; --accent-ink:#fff; --accent-soft:rgba(0,136,255,.12);
 --ok:#008932; --warn:#b25000; --bad:#e9152d;
 --ok-soft:rgba(52,199,89,.16); --warn-soft:rgba(255,149,0,.16); --bad-soft:rgba(255,59,48,.14);
 --fill:rgba(118,118,128,.12); --fill-2:rgba(118,118,128,.08);
 --r:13px; --r-sm:10px; --sh:0 1px 2px rgba(0,0,0,.05);
 --sh-2:0 10px 30px -12px rgba(0,0,0,.28);
 --bar:49px;
 --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
 --sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI Variable Text","Segoe UI",
  system-ui,Roboto,"Helvetica Neue",sans-serif;
 color-scheme:light dark;
}
@media (prefers-color-scheme:dark){:root{
 --bg:#000; --surface:#1c1c1e; --surface-2:#2c2c2e; --raised:#2c2c2e;
 --ink:#fff; --ink-2:rgba(235,235,245,.8); --muted:rgba(235,235,245,.6);
 --line:rgba(84,84,88,.6); --line-2:rgba(84,84,88,.4);
 --accent:#0091ff; --accent-ink:#fff; --accent-soft:rgba(0,145,255,.24);
 --ok:#30d158; --warn:#ff9230; --bad:#ff4245;
 --ok-soft:rgba(48,209,88,.2); --warn-soft:rgba(255,159,10,.2); --bad-soft:rgba(255,69,58,.2);
 --fill:rgba(120,120,128,.24); --fill-2:rgba(120,120,128,.16);
 --sh:0 1px 2px rgba(0,0,0,.6); --sh-2:0 12px 34px -10px rgba(0,0,0,.8);}}

html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:17px;
 line-height:1.45;-webkit-font-smoothing:antialiased;overflow-x:clip;
 padding-bottom:env(safe-area-inset-bottom)}
a{color:var(--accent);text-decoration:none}
a,button,.li,.appcard,summary{-webkit-tap-highlight-color:transparent;
 -webkit-touch-callout:none;touch-action:manipulation}
:focus-visible{outline:2.5px solid var(--accent);outline-offset:2px;border-radius:6px}
.mono,code,td,.help,.kv dt,.kv dd,.li-sub,.li-main b,.sub,h1,h2,h3{overflow-wrap:anywhere}

/* Geruest: links Seitenleiste (Desktop), unten Leiste (Telefon) */
.layout{display:grid;grid-template-columns:1fr;min-height:100vh;min-height:100dvh}
.layout>*{min-width:0}
.side{display:none}
.main{min-width:0;padding:18px max(16px,env(safe-area-inset-left)) calc(var(--bar) + 34px + env(safe-area-inset-bottom))
 max(16px,env(safe-area-inset-right));max-width:1080px;width:100%;margin:0 auto}
.topbar{position:sticky;top:0;z-index:30;display:flex;align-items:center;gap:6px;min-height:44px;
 padding:0 max(8px,env(safe-area-inset-right)) 0 max(8px,env(safe-area-inset-left));
 background:var(--bg);
 -webkit-backdrop-filter:saturate(180%) blur(20px);backdrop-filter:saturate(180%) blur(20px);
 border-bottom:.5px solid var(--line-2)}
.topbar .ttl{font-weight:600;font-size:17px;letter-spacing:-.01em;flex:1;text-align:center;
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 4px;opacity:0;
 transition:opacity .2s ease}
.topbar.shown .ttl{opacity:1}
.topbar .back,.topbar .slot{min-width:44px;min-height:44px;display:inline-flex;align-items:center;
 justify-content:center;color:var(--accent);font-size:16px;gap:2px}
.topbar .back{max-width:42%;flex:0 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
 justify-content:flex-start;padding:0 4px}
.tabbar{position:fixed;left:0;right:0;bottom:0;z-index:40;display:flex;background:var(--bg);
 padding:0 env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);
 -webkit-backdrop-filter:saturate(180%) blur(20px);backdrop-filter:saturate(180%) blur(20px);
 border-top:.5px solid var(--line)}
@supports ((-webkit-backdrop-filter:blur(1px)) or (backdrop-filter:blur(1px))){
 .tabbar,.topbar{background:color-mix(in srgb,var(--bg) 88%,transparent)}}
.tabbar a{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;
 min-height:var(--bar);color:var(--muted);font-size:10.5px;font-weight:500;letter-spacing:.01em;
 -webkit-tap-highlight-color:transparent}
.tabbar a.on{color:var(--accent)}
.tabbar svg{width:25px;height:25px;stroke:currentColor;fill:none;stroke-width:1.7;
 stroke-linecap:round;stroke-linejoin:round}
.tabbar a.on svg{stroke-width:2.1}

@media (min-width:900px){
 .layout{grid-template-columns:250px 1fr}
 .side{display:flex;flex-direction:column;gap:2px;padding:22px 12px;background:var(--surface);
  border-right:.5px solid var(--line);position:sticky;top:0;height:100vh;height:100dvh;overflow:auto}
 .tabbar,.topbar{display:none}
 .main{padding:28px 34px 60px}
 body{font-size:15px}
 .brand{display:flex;align-items:center;gap:10px;font-weight:650;font-size:17px;padding:2px 10px 18px;
  letter-spacing:-.02em}
 .brand .mark{width:28px;height:28px;border-radius:8px;flex:0 0 28px}
 .brand small{display:block;font-weight:450;font-size:12px;color:var(--muted)}
 .side a{display:flex;align-items:center;gap:11px;padding:9px 11px;border-radius:var(--r-sm);
  color:var(--ink-2);font-size:14.5px;font-weight:500}
 .side a.on{background:var(--accent-soft);color:var(--accent);font-weight:600}
 .side svg{width:20px;height:20px;stroke:currentColor;fill:none;stroke-width:1.8;
  stroke-linecap:round;stroke-linejoin:round}
 .side .whoami{margin-top:auto;padding:14px 11px 2px;border-top:.5px solid var(--line);
  font-size:13px;color:var(--muted);display:block}

}

/* Typografie */
h1{font-size:34px;line-height:41px;font-weight:700;letter-spacing:-.03em;margin:8px 0 2px}
h2{font-size:13px;line-height:18px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
 color:var(--muted);margin:30px 0 7px;padding:0 16px}
h3{font-size:17px;line-height:22px;font-weight:600;letter-spacing:-.01em;margin:0 0 10px}
.sub{color:var(--muted);font-size:15px;margin:0 0 18px}
.muted{color:var(--muted)}
code,.mono{font-family:var(--mono);font-size:.92em}
@media (min-width:900px){h1{font-size:26px}.sub{font-size:14px}h3{font-size:15.5px}}

/* Flaechen */
.card{background:var(--surface);border-radius:var(--r);padding:16px;box-shadow:var(--sh);
 margin-bottom:12px}
.grid{display:grid;gap:12px;margin-bottom:12px}
.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
.g3{grid-template-columns:repeat(2,minmax(0,1fr))}
.g4{grid-template-columns:repeat(2,minmax(0,1fr))}
@media (min-width:900px){.g3{grid-template-columns:repeat(3,minmax(0,1fr))}
 .g4{grid-template-columns:repeat(4,minmax(0,1fr))}}

/* Liste im iOS-Stil */
.list{background:var(--surface);border-radius:var(--r);box-shadow:var(--sh);overflow:hidden;
 margin-bottom:12px}
.li{display:flex;align-items:center;gap:12px;min-height:52px;padding:10px 16px;color:var(--ink);
 border-bottom:.5px solid var(--line-2);-webkit-tap-highlight-color:transparent;width:100%;
 background:none;border-left:0;border-right:0;border-top:0;font:inherit;text-align:left}
.li:last-child{border-bottom:0}
.li+.li{border-top:0}
a.li,button.li{cursor:pointer}
a.li:active,button.li:active{background:var(--fill-2)}
.li-main{flex:1;min-width:0}
.li-main b{font-weight:500;font-size:16px}
.li-sub{display:block;color:var(--muted);font-size:13.5px;margin-top:1px}
.li-side{color:var(--muted);font-size:15px;white-space:nowrap;display:flex;align-items:center;gap:8px}
.li .ic{width:29px;height:29px;flex:0 0 29px;border-radius:7px;display:grid;place-items:center;
 background:var(--accent-soft);color:var(--accent);font-size:15px}
.chev{width:9px;height:9px;border-right:2px solid var(--line);border-top:2px solid var(--line);
 transform:rotate(45deg);flex:0 0 9px;margin-left:2px}
@media (min-width:900px){.li-main b{font-size:14.5px}.li{min-height:46px}.li-sub{font-size:12.5px}
 .li-side{font-size:13.5px}}

/* Kennzahlen */
.stat{display:block;color:var(--ink)}
.stat .k{color:var(--muted);font-size:13px;font-weight:500}
.stat .v{font-size:clamp(20px,6vw,28px);font-weight:600;letter-spacing:-.02em;margin:2px 0 8px;
 font-variant-numeric:tabular-nums;line-height:1.15;overflow-wrap:anywhere}
.stat .note{font-size:12.5px;color:var(--muted)}
.bar{height:6px;background:var(--fill);border-radius:99px;overflow:hidden;margin-bottom:7px}
.bar>i{display:block;height:100%;background:var(--accent);border-radius:99px;transition:width .4s ease}
.bar.ok>i{background:var(--ok)}.bar.warn>i{background:var(--warn)}.bar.bad>i{background:var(--bad)}
@media (min-width:900px){.stat .v{font-size:24px}}

/* Zustaende */
.pill{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:99px;
 font-size:13px;font-weight:500;background:var(--fill);color:var(--muted);white-space:nowrap}
.pill.run{color:var(--ok);background:var(--ok-soft)}
.pill.warn{color:var(--warn);background:var(--warn-soft)}
.pill.err{color:var(--bad);background:var(--bad-soft)}
.dot{width:7px;height:7px;border-radius:99px;background:currentColor}
.badge{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12.5px;font-weight:600;
 background:var(--accent-soft);color:var(--accent)}

/* Schaltflaechen */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:44px;
 padding:11px 18px;border-radius:var(--r-sm);border:0;background:var(--fill);color:var(--accent);
 font:inherit;font-size:16px;font-weight:600;cursor:pointer;white-space:nowrap;
 -webkit-tap-highlight-color:transparent;transition:opacity .12s,background .12s}
.btn:active{opacity:.55}
.btn.primary{background:var(--accent);color:var(--accent-ink)}
.btn.danger{color:var(--bad);background:var(--bad-soft)}
.btn.sm{min-height:36px;padding:7px 14px;font-size:14.5px}
.btn.wide{width:100%}
.row.equal{gap:8px}
.row.equal>.btn{flex:1}
.btn:disabled{opacity:.5;cursor:progress}
.btn.plain{background:none;padding:11px 6px}
@media (min-width:900px){.btn{min-height:38px;padding:9px 16px;font-size:14.5px}
 .btn.sm{min-height:32px;padding:5px 12px;font-size:13.5px}}
@media (hover:hover) and (pointer:fine){.btn:hover{filter:brightness(1.06)}
 a.li:hover{background:var(--fill-2)}.side a:hover{background:var(--fill-2)}
 .side .whoami:hover{color:var(--accent)}}
.row{display:flex;gap:9px;align-items:center;flex-wrap:wrap}
.row>*{min-width:0}
.between{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}
.between>*{min-width:0}
.danger-zone{margin-top:26px;padding-top:16px;border-top:.5px solid var(--line)}

/* Formulare */
label{display:block;font-size:14px;font-weight:500;margin:0 0 6px;color:var(--ink-2)}
input,select,textarea{width:100%;padding:12px 14px;border:0;border-radius:var(--r-sm);
 background:var(--fill);color:var(--ink);font:inherit;font-size:16px;min-height:44px;
 -webkit-appearance:none;appearance:none}
select{background-image:linear-gradient(45deg,transparent 50%,var(--muted) 50%),
 linear-gradient(135deg,var(--muted) 50%,transparent 50%);
 background-position:calc(100% - 20px) 50%,calc(100% - 14px) 50%;
 background-size:6px 6px,6px 6px;background-repeat:no-repeat;padding-right:38px}
input:focus,select:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:-1px}
input[type=checkbox],input[type=radio]{width:auto;min-height:0;padding:0;background:none;
 accent-color:var(--accent);flex:0 0 auto;width:22px;height:22px}
input[type=file]{padding:10px 12px;font-size:15px}
input[type=number]::-webkit-inner-spin-button{-webkit-appearance:none;margin:0}
textarea{font-family:var(--mono);line-height:1.55;resize:vertical;min-height:180px}
.field{margin-bottom:14px}
.field:last-child{margin-bottom:0}
.check{display:flex;gap:11px;align-items:center;min-height:44px}
.check label{margin:0;font-size:16px;font-weight:400;color:var(--ink)}
.help{font-size:13.5px;color:var(--muted);margin:6px 0 0;line-height:1.45}
.help[hidden]{display:none}
.hint{border:0;background:none;color:var(--accent);font:inherit;font-size:16px;cursor:pointer;
 min-width:44px;min-height:44px;margin:-11px 0;padding:0 6px;line-height:1;vertical-align:middle}
.readonly-val{padding:12px 14px;border-radius:var(--r-sm);background:var(--fill-2);color:var(--ink-2);
 display:flex;justify-content:space-between;align-items:center;gap:8px}
.locktag{font-size:12.5px;color:var(--bad);font-weight:500;white-space:nowrap}
.lockrow{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 0 6px}
.lockrow label{margin:0}
.lockbtn{min-height:36px;padding:4px 12px;border-radius:99px;border:0;background:var(--bad-soft);
 color:var(--bad);font:inherit;font-size:13.5px;font-weight:600;cursor:pointer}
.field.locked input,.field.locked select,.field.locked textarea{color:var(--muted);
 background:var(--bad-soft);cursor:not-allowed}
.field.unlocked input,.field.unlocked select,.field.unlocked textarea{outline:2px solid var(--warn)}

/* Schalter */
.switch{position:relative;display:inline-block;width:51px;height:31px;flex:0 0 51px}
.switch input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;z-index:2;
 cursor:pointer}
.switch i{position:absolute;inset:0;background:var(--fill);border-radius:99px;display:block;
 transition:background .2s ease}
.switch i::after{content:"";position:absolute;top:2px;left:2px;width:27px;height:27px;
 border-radius:99px;background:#fff;box-shadow:0 2px 6px rgba(0,0,0,.25);
 transition:transform .2s ease}
.switch input:checked+i{background:#34c759}
.switch input:checked+i::after{transform:translateX(20px)}
.switch input:disabled+i{opacity:.5}
.switch input:focus-visible+i{outline:2.5px solid var(--accent);outline-offset:2px}

/* Segmentierte Auswahl */
.seg{display:inline-flex;background:var(--fill);border-radius:9px;padding:2px;gap:2px;width:100%}
.seg button,.seg label{flex:1;min-width:0;border:0;background:none;color:var(--ink);font:inherit;
 font-size:14px;font-weight:500;padding:8px 6px;border-radius:7px;cursor:pointer;text-align:center;
 margin:0;min-height:36px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
 -webkit-tap-highlight-color:transparent}
.seg input:focus-visible+label{outline:2.5px solid var(--accent);outline-offset:-2px}
.seg button.on,.seg input:checked+label{background:var(--raised);font-weight:600;box-shadow:var(--sh)}
.seg input{position:absolute;opacity:0;pointer-events:none}
.segwrap{position:relative}

/* Meldungen */
.msg{padding:12px 15px;border-radius:var(--r-sm);margin-bottom:14px;font-size:15px;line-height:1.45}
.msg.ok{background:var(--ok-soft);color:var(--ok)}
.msg.err{background:var(--bad-soft);color:var(--bad)}
.banner{display:flex;align-items:flex-start;gap:10px;padding:12px 15px;border-radius:var(--r-sm);
 margin-bottom:14px;font-size:15px;background:var(--bad-soft);color:var(--bad);line-height:1.45}
.banner .txt{flex:1;min-width:0}
.banner button{background:none;border:0;color:inherit;font-size:20px;line-height:1;cursor:pointer;
 min-width:36px;min-height:36px}

/* Aufklappbereiche */
details.sec{background:var(--surface);border-radius:var(--r);box-shadow:var(--sh);margin-bottom:12px;
 overflow:hidden}
details.sec>summary{list-style:none;cursor:pointer;padding:14px 16px;font-weight:500;font-size:16px;
 display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:52px}
details.sec>summary::-webkit-details-marker{display:none}
details.sec>summary::after{content:"";width:9px;height:9px;border-right:2px solid var(--line);
 border-bottom:2px solid var(--line);transform:rotate(45deg) translate(-2px,-2px);
 transition:transform .18s ease;flex:0 0 9px}
details.sec[open]>summary::after{transform:rotate(-135deg) translate(-3px,-3px)}
details.sec[open]>summary{border-bottom:.5px solid var(--line-2)}
details.sec>.in{padding:14px 16px}
details.sec details.sec{box-shadow:none;border-radius:0;margin:0}
@media (min-width:900px){details.sec>summary{font-size:14.5px;min-height:46px}}

/* Tabellen (Restbestand: schmal gestapelt) */
table{width:100%;border-collapse:collapse;font-size:15px}
th,td{text-align:left;padding:11px 12px;border-bottom:.5px solid var(--line-2)}
th{font-size:13px;color:var(--muted);font-weight:500}
tr:last-child td{border-bottom:0}
.tbl-wrap{overflow-x:auto;min-width:0}
@media (max-width:899px){
 .stacked thead{display:none}
 .stacked tr{display:block;padding:10px 0;border-bottom:.5px solid var(--line-2)}
 .stacked tr:last-child{border-bottom:0}
 .stacked td{display:flex;justify-content:space-between;gap:14px;border:0;padding:4px 0}
 .stacked td::before{content:attr(data-label);color:var(--muted);font-size:13.5px;flex:0 0 auto}
 .stacked td:empty{display:none}
}

/* Katalog */
.apps{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}
.appcard{background:var(--surface);border-radius:var(--r);padding:14px;box-shadow:var(--sh);
 display:flex;flex-direction:column;gap:9px;color:var(--ink);min-width:0;
 -webkit-tap-highlight-color:transparent}
.appcard .row{flex-direction:column;align-items:flex-start;gap:9px}
.appcard:active{background:var(--fill-2)}
.appcard .ico{font-size:24px;width:46px;height:46px;flex:0 0 46px;display:grid;place-items:center;
 background:var(--fill);border-radius:11px}
.appcard .nm{font-weight:600;font-size:15.5px;letter-spacing:-.01em}
.appcard .sm{color:var(--muted);font-size:13.5px;flex:1;line-height:1.4}
.appcard .aud{font-size:12px;color:var(--muted)}
.apps.featured{grid-template-columns:repeat(auto-fill,minmax(160px,1fr))}
.appcard.big .ico{width:52px;height:52px;flex-basis:52px;font-size:28px;border-radius:13px;
 background:var(--accent-soft)}
@media (min-width:600px){.apps,.apps.featured{grid-template-columns:repeat(auto-fill,minmax(230px,1fr))}}
.cat-tools{display:flex;flex-direction:column;gap:10px;margin:0 0 14px}
.cat-tools .row1{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.cat-search{flex:1;min-width:0}
.catchips{display:flex;gap:8px;overflow-x:auto;padding-bottom:2px;scrollbar-width:none;min-width:0;
 -webkit-mask-image:linear-gradient(to right,#000 88%,transparent);
 mask-image:linear-gradient(to right,#000 88%,transparent)}
.catchips::-webkit-scrollbar{display:none}
.catchips button{border:0;background:var(--fill);color:var(--ink-2);font:inherit;font-size:14px;
 font-weight:500;padding:8px 14px;border-radius:99px;cursor:pointer;white-space:nowrap;min-height:38px}
.catchips button.on{background:var(--accent);color:var(--accent-ink)}
.catsec{margin:0 0 4px}
.catsec h3,.cat-head{font-size:13px;text-transform:uppercase;letter-spacing:.02em;color:var(--muted);
 margin:22px 4px 8px;font-weight:600}
.cat-empty{display:none;color:var(--muted);padding:26px 0;text-align:center}

/* Reiter */
.tabs{display:flex;gap:8px;margin:0 0 18px;overflow-x:auto;overflow-y:hidden;scrollbar-width:none;
 min-width:0;
 background:var(--fill);border-radius:9px;padding:2px}
.tabs::-webkit-scrollbar{display:none}
.tabs a{flex:1;text-align:center;padding:9px 12px;font-size:14px;font-weight:500;color:var(--ink);
 border-radius:7px;white-space:nowrap;min-height:38px;display:flex;align-items:center;
 justify-content:center;-webkit-tap-highlight-color:transparent}
.tabs a.on{background:var(--raised);font-weight:600;box-shadow:var(--sh)}

/* Sonstiges */
pre{background:var(--surface);border-radius:var(--r-sm);padding:14px;overflow:auto;
 font-family:var(--mono);font-size:13px;max-height:60dvh;margin:0;line-height:1.5;
 overscroll-behavior:contain}
.kv{display:grid;grid-template-columns:1fr;gap:0;font-size:16px;margin:0}
.kv dt{color:var(--muted);font-size:13.5px;margin-top:12px}
.kv dt:first-child{margin-top:0}
.kv dd{margin:0;min-width:0}
@media (min-width:900px){.kv{font-size:14.5px}}
.copy{border:0;background:var(--fill);color:var(--accent);border-radius:8px;font:inherit;
 font-size:13.5px;font-weight:600;padding:6px 12px;min-height:36px;cursor:pointer}
.secret{display:flex;align-items:center;gap:10px;justify-content:space-between}
.secret code{flex:1;min-width:0}

/* Anmeldung / Einrichtung */
.center{min-height:100vh;min-height:100dvh;display:grid;place-items:center;
 padding:24px max(16px,env(safe-area-inset-left)) calc(24px + env(safe-area-inset-bottom))
 max(16px,env(safe-area-inset-right))}
.box{width:100%;max-width:420px}
.box .card{padding:22px;box-shadow:var(--sh-2)}
.box h1{font-size:26px;margin-bottom:6px}
.steps{display:flex;gap:6px;margin:0 0 18px;font-size:12.5px}
.steps div{flex:1;min-width:0;padding:7px 6px;border-radius:8px;background:var(--fill);
 text-align:center;color:var(--muted);font-weight:500;overflow:hidden;text-overflow:ellipsis;
 white-space:nowrap}
.steps div.on{background:var(--accent);color:var(--accent-ink)}
.steps div.done{color:var(--ok);background:var(--ok-soft)}
.progress{height:8px;background:var(--fill);border-radius:99px;overflow:hidden;margin:18px 0 8px}
.progress>i{display:block;height:100%;width:0;background:var(--accent);border-radius:99px;
 transition:width .5s ease}

/* Dialog: auf dem Telefon ein Blatt von unten */
dialog{border:0;border-radius:var(--r);padding:0;max-width:min(560px,94vw);width:100%;
 background:var(--surface);color:var(--ink);box-shadow:var(--sh-2)}
dialog::backdrop{background:rgba(0,0,0,.4);-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px)}
dialog .dhead{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;
 border-bottom:.5px solid var(--line-2)}
dialog .dhead h3{margin:0}
dialog .dbody{padding:16px;max-height:66dvh;overflow:auto}
dialog .x{background:none;border:0;font-size:22px;line-height:1;cursor:pointer;color:var(--muted);
 min-width:44px;min-height:44px}
@media (max-width:899px){
 dialog{margin:auto auto 0;max-width:100%;border-radius:var(--r) var(--r) 0 0;
  padding-bottom:env(safe-area-inset-bottom)}
 dialog[open]{animation:sheet .22s cubic-bezier(.32,.72,0,1)}
}
.sub-in{max-width:210px}
.checks{display:flex;flex-direction:column;gap:2px}
.checks .check{min-height:40px}
.acctrow{border-radius:var(--r-sm);padding:12px 14px;background:var(--fill-2);margin-bottom:8px}

@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.li,.btn,.appcard{transition:background-color .2s cubic-bezier(.25,.1,.25,1)}
@keyframes sheet{from{transform:translateY(100%)}to{transform:none}}
@keyframes spin{to{transform:rotate(360deg)}}
.main,.box{animation:fadein .18s ease}
.btn .spinner{width:14px;height:14px;border:2px solid currentColor;border-top-color:transparent;
 border-radius:50%;animation:spin .7s linear infinite;display:inline-block}
*{scrollbar-width:thin;scrollbar-color:var(--line) transparent}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-thumb{background:var(--line);border-radius:99px}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;
 transition-duration:.01ms!important}}
"""


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def num(value, decimals=1):
    """Zahl deutsch: Komma als Dezimaltrenner, Punkt als Tausendertrenner."""
    try:
        text = f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return esc(value)
    if decimals == 0:
        text = text.split(".")[0]
    return text.replace(",", "").replace(".", ",").replace("", ".")


def icon(name):
    return (f'<svg viewBox="0 0 24 24" aria-hidden="true">'
            f'<path d="{ICONS.get(name, "")}"/></svg>')


def _bar_class(percent):
    return "bad" if percent >= 90 else "warn" if percent >= 75 else "ok"


def banner_html(text, token=""):
    if not text:
        return ""
    return (f'<div class="banner"><span class="txt">{esc(text)}</span>'
            f'<form method="post" action="/banner"><input type="hidden" name="csrf" '
            f'value="{esc(token)}"><button type="submit" aria-label="Schließen">&times;</button>'
            f'</form></div>')


def section(title, inner, open_=False, note=""):
    tag = f'<span class="muted" style="font-weight:400">{esc(note)}</span>' if note else ""
    return (f'<details class="sec"{" open" if open_ else ""}>'
            f'<summary>{esc(title)}{tag}</summary><div class="in">{inner}</div></details>')


def li(title, href="", sub="", side="", chevron=None, ic=""):
    """Zeile einer Liste im iOS-Stil."""
    chevron = bool(href) if chevron is None else chevron
    body = (f'<span class="li-main"><b>{esc(title)}</b>'
            f'{f"<span class=li-sub>{sub}</span>" if sub else ""}</span>'
            f'{f"<span class=li-side>{side}</span>" if side else ""}'
            f'{"<span class=chev></span>" if chevron else ""}')
    ic_html = f'<span class="ic">{ic}</span>' if ic else ""
    if href:
        return f'<a class="li" href="{esc(href)}">{ic_html}{body}</a>'
    return f'<div class="li">{ic_html}{body}</div>'


def group(rows, title="", note=""):
    head = f"<h2>{esc(title)}</h2>" if title else ""
    tail = f'<p class="help" style="margin:6px 4px 16px">{esc(note)}</p>' if note else ""
    return f'{head}<div class="list">{"".join(rows)}</div>{tail}'


def stat(label, value, percent=None, note="", href="", raw=False):
    bar = ""
    if percent is not None:
        bar = (f'<div class="bar {_bar_class(percent)}">'
               f'<i style="width:{max(0, min(100, percent)):.1f}%"></i></div>')
    sub = f'<div class="note">{esc(note)}</div>' if note else ""
    shown = value if raw else esc(value)
    inner = f'<div class="k">{esc(label)}</div><div class="v">{shown}</div>{bar}{sub}'
    if href:
        return f'<a class="card stat" href="{esc(href)}">{inner}</a>'
    return f'<div class="card stat">{inner}</div>'


STATE_LABELS = {
    "running": ("run", "läuft"),
    "restarting": ("warn", "startet neu"),
    "paused": ("warn", "angehalten"),
    "created": ("", "noch nie gestartet"),
    "exited": ("", "gestoppt"),
    "dead": ("err", "fehlerhaft"),
    "removing": ("warn", "wird entfernt"),
    "missing": ("err", "fehlt"),
    "partial": ("warn", "teilweise gestoppt"),
    "": ("", "unbekannt"),
}

STATE_HINTS = {
    "partial": "Datenbank oder Verwaltung läuft nicht",
    "exited": "gestoppt — starten?",
    "created": "wurde nie gestartet",
    "restarting": "startet immer wieder neu",
    "dead": "Container fehlerhaft",
    "missing": "Container fehlt — neu erstellen",
    "paused": "angehalten",
}


def status_pill(state, note=""):
    cls, label = STATE_LABELS.get(state, ("err", state))
    if note:
        label = f"{label} · {note}"
    return f'<span class="pill {cls}"><span class="dot"></span>{esc(label)}</span>'


def _info_attr(text):
    return f' title="{esc(text)}"' if text else ""


def hint_icon(text):
    """Zeichen neben dem Label; blendet den Hilfetext per Tipp ein."""
    return ('<button type="button" class="hint" data-hint aria-expanded="false" '
            'aria-label="Erklärung">&#9432;</button>' if text else "")


def help_text(text):
    return f'<p class="help" hidden>{esc(text)}</p>' if text else ""


def secret_row(label, value):
    return (f'<div class="li"><span class="li-main"><b>{esc(label)}</b>'
            f'<span class="li-sub secret"><code class="mono">{esc(value)}</code>'
            f'<button type="button" class="copy" data-copy="{esc(value)}">Kopieren</button>'
            f'</span></span></div>')


def segmented(key, label, options, value, option_labels=None, help_hint="", depends=""):
    """Auswahl mit wenigen Optionen als Segmentleiste statt Aufklappliste."""
    option_labels = option_labels or {}
    parts = ""
    known = [str(o) for o in options]
    fallback = known[0] if known and str(value) not in known else None
    for opt in options:
        checked = " checked" if str(value) == str(opt) or str(opt) == fallback else ""
        oid = f"{key}-{opt}"
        parts += (f'<input type="radio" id="{esc(oid)}" name="{esc(key)}" value="{esc(opt)}"{checked}>'
                  f'<label for="{esc(oid)}">{esc(option_labels.get(opt, opt))}</label>')
    head = f'<label>{esc(label)}{hint_icon(help_hint)}</label>' if label else ""
    return (f'<div class="field segwrap"{depends}>{head}<div class="seg">{parts}</div>'
            f'{help_text(help_hint)}</div>')


def switch_row(key, label, checked, help_hint=""):
    return (f'<div class="field"><div class="check" style="justify-content:space-between">'
            f'<label for="{esc(key)}">{esc(label)}{hint_icon(help_hint)}</label>'
            f'<span class="switch"><input type="checkbox" id="{esc(key)}" name="{esc(key)}" '
            f'value="1"{" checked" if checked else ""}><i></i></span></div>'
            f'{help_text(help_hint)}</div>')


TEXT_ATTRS = ' autocapitalize="none" autocorrect="off" spellcheck="false"'


def _label_row(key, label, locked, info=""):
    if locked:
        return (f'<div class="lockrow"><label for="{esc(key)}">{esc(label)} '
                f'<span class="locktag">gesperrt</span></label>'
                f'<button type="button" class="lockbtn" data-unlock="{esc(key)}">'
                f'Freischalten</button></div>')
    return f'<label for="{esc(key)}">{esc(label)}{hint_icon(info)}</label>'


def field_input(field, value, prefix="", locked=False):
    key = prefix + field["key"]
    ftype = field.get("type", "string")
    label = field.get("label", field["key"])
    locked = locked or field.get("locked", False)
    required = "" if locked else (" required" if field.get("required") else "")
    dis = " disabled" if locked else ""
    hint = field.get("help", "")
    ph = f' placeholder="{esc(field["placeholder"])}"' if field.get("placeholder") else ""
    depends = ""
    if field.get("depends_on"):
        depends = f' data-depends=\'{html.escape(json.dumps(field["depends_on"]), quote=True)}\''
    wrap = "field locked" if locked else "field"

    if ftype == "bool":
        lockbtn = (f'<button type="button" class="lockbtn" data-unlock="{esc(key)}">'
                   f'Freischalten</button>') if locked else ""
        control = (f'<div class="check" style="justify-content:space-between">'
                   f'<label for="{esc(key)}">{esc(label)}{hint_icon(hint)}</label>'
                   f'<span class="row" style="flex-wrap:nowrap">{lockbtn}'
                   f'<span class="switch"><input type="checkbox" id="{esc(key)}" name="{esc(key)}" '
                   f'value="1"{" checked" if value else ""}{dis}><i></i></span></span></div>')
        return f'<div class="{wrap}"{depends}>{control}{help_text(hint)}</div>'

    if ftype == "select":
        labels = field.get("option_labels", {})
        options = field.get("options", [])
        if len(options) <= 3 and not locked:
            return segmented(key, label, options, value, labels, hint, depends)
        opts = "".join(
            f'<option value="{esc(opt)}"{" selected" if str(value) == str(opt) else ""}>'
            f'{esc(labels.get(opt, opt))}</option>' for opt in options)
        control = f'<select id="{esc(key)}" name="{esc(key)}"{dis}>{opts}</select>'
    elif ftype == "number":
        attrs = ' inputmode="decimal"' if str(field.get("step", "")).startswith("0.") \
            else ' inputmode="numeric"'
        for attr in ("min", "max", "step"):
            if attr in field:
                attrs += f' {attr}="{esc(field[attr])}"'
        control = (f'<input type="number" id="{esc(key)}" name="{esc(key)}" '
                   f'value="{esc(value)}"{attrs}{required}{dis}{ph}>')
    elif ftype == "password":
        control = (f'<input type="password" id="{esc(key)}" name="{esc(key)}" '
                   f'value="" autocomplete="new-password"{required}{dis}{ph}>')
    elif ftype == "textarea":
        control = (f'<textarea id="{esc(key)}" name="{esc(key)}" rows="10"{TEXT_ATTRS}'
                   f' autocomplete="off"{dis}>{esc(value)}</textarea>')
    else:
        control = (f'<input type="text" id="{esc(key)}" name="{esc(key)}" '
                   f'value="{esc(value)}"{TEXT_ATTRS}{required}{dis}{ph}>')
    return (f'<div class="{wrap}"{depends}>{_label_row(key, label, locked, hint)}'
            f'{control}{help_text(hint)}</div>')


def select_field(key, label, options, value, help_hint="", option_labels=None, locked=False):
    option_labels = option_labels or {}
    if len(options) <= 3 and not locked:
        return segmented(key, label, options, value, option_labels, help_hint)
    opts = "".join(
        f'<option value="{esc(o)}"{" selected" if str(value) == str(o) else ""}>'
        f'{esc(option_labels.get(o, o))}</option>' for o in options)
    dis = " disabled" if locked else ""
    wrap = "field locked" if locked else "field"
    return (f'<div class="{wrap}">{_label_row(key, label, locked, help_hint)}'
            f'<select id="{esc(key)}" name="{esc(key)}"{dis}>{opts}</select>'
            f'{help_text(help_hint)}</div>')


def readonly_field(label, value, note=""):
    tag = f'<span class="locktag">{esc(note)}</span>' if note else ""
    return (f'<div class="field"><label>{esc(label)}</label>'
            f'<div class="readonly-val"><span class="mono">{esc(value)}</span>{tag}</div></div>')


def csrf_input(token):
    return f'<input type="hidden" name="csrf" value="{esc(token)}">'


def modal(dialog_id, title, inner):
    return (f'<dialog id="{esc(dialog_id)}"><div class="dhead"><h3>{esc(title)}</h3>'
            f'<button class="x" type="button" onclick="this.closest(\'dialog\').close()"'
            f' aria-label="Schließen">&times;</button></div>'
            f'<div class="dbody">{inner}</div></dialog>')


def open_button(dialog_id, label, cls="btn primary"):
    return (f'<button type="button" class="{cls}" data-nospin '
            f'onclick="document.getElementById(\'{esc(dialog_id)}\').showModal()">'
            f'{esc(label)}</button>')


def _nav(tabs, active):
    out = ""
    for path, label, name in tabs:
        on = " on" if path == active else ""
        out += (f'<a class="{on.strip()}" href="{path}"'
                f'{" aria-current=page" if on else ""}>{icon(name)}<span>{esc(label)}</span></a>')
    return out


HEAD_META = (
    '<meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
    '<meta name="apple-mobile-web-app-capable" content="yes">'
    '<meta name="mobile-web-app-capable" content="yes">'
    '<meta name="apple-mobile-web-app-title" content="weblab">'
    '<meta name="apple-mobile-web-app-status-bar-style" content="default">'
    '<meta name="theme-color" content="#f2f2f7" media="(prefers-color-scheme:light)">'
    '<meta name="theme-color" content="#000000" media="(prefers-color-scheme:dark)">'
    '<meta name="format-detection" content="telephone=no">'
    '<link rel="icon" href="/static/icon.svg" type="image/svg+xml">'
    '<link rel="apple-touch-icon" href="/static/icon-180.png">'
    '<link rel="manifest" href="/static/app.webmanifest">'
)


def asset_url(kind):
    body = CSS if kind == "css" else GLOBAL_JS
    return f"/static/app.{hashlib.sha1(body.encode()).hexdigest()[:10]}.{kind}"


def _shell(title, inner, head=""):
    return (f'<!doctype html><html lang="de"><head>{HEAD_META}'
            f'<title>{esc(title)} — weblab</title>'
            f'<link rel="stylesheet" href="{asset_url("css")}">{head}</head>'
            f'<body>{inner}<script src="{asset_url("js")}" defer></script></body></html>')


def page(title, body, active="/", user=None, flash=None, head="", banner="", is_admin=True,
         parent=None):
    tabs = TABS if is_admin else USER_TABS
    msg = ""
    if flash:
        kind, text = flash
        msg = f'<div class="msg {esc(kind)}">{esc(text)}</div>'
    who = (f'<a class="whoami" href="/konto">{esc(user)} · Konto</a>' if user else "")
    back = (f'<a class="back" href="{esc(parent[1])}">&#8249; {esc(parent[0])}</a>'
            if parent else '<span class="slot"></span>')
    return _shell(title, f"""<div class="layout">
<aside class="side"><div class="brand">
<img class="mark" src="/static/icon.svg" alt="" width="28" height="28">
<span>weblab<small>Server-Verwaltung</small></span></div>
{_nav(tabs, active)}{who}</aside>
<div><header class="topbar">{back}<span class="ttl">{esc(title)}</span>
<span class="slot"></span></header>
<main class="main">{banner}{msg}{body}</main></div>
<nav class="tabbar">{_nav(tabs, active)}</nav></div>""", head)


def bare(title, body, head="", parent=None):
    back = (f'<header class="topbar"><a class="back" href="{esc(parent[1])}">&#8249; '
            f'{esc(parent[0])}</a><span class="ttl">{esc(title)}</span>'
            f'<span class="slot"></span></header>' if parent else "")
    return _shell(title, f'{back}<div class="center">{body}</div>', head)


GLOBAL_JS = """
(function(){
 function all(sel){return [].slice.call(document.querySelectorAll(sel))}
 all('[data-unlock]').forEach(function(b){
  b.addEventListener('click',function(){
   var f=document.getElementById(b.getAttribute('data-unlock'));if(!f)return;
   var wrap=f.closest('.field');
   if(f.disabled){f.disabled=false;f.focus();
    if(wrap){wrap.classList.remove('locked');wrap.classList.add('unlocked');}
    b.textContent='Sperren';}
   else{f.disabled=true;
    if(wrap){wrap.classList.add('locked');wrap.classList.remove('unlocked');}
    b.textContent='Freischalten';}
  });
 });
 var deps=all('[data-depends]');
 function sync(){deps.forEach(function(el){
   var cond=JSON.parse(el.getAttribute('data-depends')),show=true;
   Object.keys(cond).forEach(function(k){
    var s=document.querySelector('[name="'+k+'"]:checked')||
          document.querySelector('[name="'+k+'"]');
    if(s&&String(s.value)!==String(cond[k]))show=false;});
   el.style.display=show?'':'none';});}
 all('select,input').forEach(function(e){e.addEventListener('change',sync)});
 sync();
 all('[data-hint]').forEach(function(b){
  b.addEventListener('click',function(){
   var field=b.closest('.field'),help=field&&field.querySelector('.help');
   if(!help)return;
   var open=help.hidden;help.hidden=!open;b.setAttribute('aria-expanded',String(open));
  });
 });
 all('[data-copy]').forEach(function(b){
  b.addEventListener('click',function(){
   var text=b.getAttribute('data-copy');
   var done=function(){b.textContent='Kopiert';
    setTimeout(function(){b.textContent='Kopieren'},1400)};
   if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(done,function(){});}
   else{var t=document.createElement('textarea');t.value=text;document.body.appendChild(t);
    t.select();try{document.execCommand('copy');done()}catch(e){}document.body.removeChild(t)}
  });
 });
 all('[data-confirm]').forEach(function(el){
  el.addEventListener('click',function(e){
   if(!window.confirm(el.getAttribute('data-confirm')))e.preventDefault();
  });
 });
 all('[data-domain-widget]').forEach(function(w){
  var sub=w.querySelector('[data-domain-sub]'),zone=w.querySelector('[data-domain-zone]'),
      out=w.querySelector('[data-domain-out]'),prev=w.querySelector('[data-domain-preview]');
  function upd(){if(!out)return;
   var z=zone?zone.value:'';var s=sub?sub.value.trim():'';
   out.value=z?(s?s+'.'+z:z):'';
   if(prev)prev.textContent=out.value?'\\u2192 '+out.value:'';}
  if(sub)sub.addEventListener('input',upd);
  if(zone)zone.addEventListener('change',upd);
  upd();
 });
 all('form').forEach(function(f){
  f.addEventListener('submit',function(e){
   var b=e.submitter||f.querySelector('button[type=submit],button:not([type])');
   if(b&&!b.disabled&&!b.hasAttribute('data-nospin')){
    b.setAttribute('data-label',b.textContent);
    setTimeout(function(){b.disabled=true;
     b.innerHTML='<span class="spinner"></span> '+b.getAttribute('data-label');},0);}
  });
 });
 window.addEventListener('pageshow',function(e){
  if(!e.persisted)return;
  all('.btn:disabled').forEach(function(b){b.disabled=false;
   if(b.getAttribute('data-label'))b.textContent=b.getAttribute('data-label');});
 });
 if(document.querySelector('[data-live]')){
  fetch('/api/stats',{headers:{'Accept':'application/json'}})
  .then(function(r){return r.json()})
  .then(function(d){
   (d.apps||[]).forEach(function(a){
    all('[data-slug="'+a.slug+'"]').forEach(function(el){
     var kind=el.getAttribute('data-metric');
     el.textContent=kind==='mem'?a.mem:(kind==='cpu'?a.cpu:a.net);
    });
   });
   Object.keys(d.system||{}).forEach(function(k){
    all('[data-sys="'+k+'"]').forEach(function(el){el.textContent=d.system[k]});
   });
  }).catch(function(){});
 }
 var big=document.querySelector('.main h1'),bar=document.querySelector('.topbar');
 if(big&&bar&&'IntersectionObserver' in window){
  new IntersectionObserver(function(entries){
   bar.classList.toggle('shown',!entries[0].isIntersecting);
  },{rootMargin:'-46px 0px 0px 0px',threshold:0}).observe(big);
 }else if(bar){bar.classList.add('shown');}
 var tools=document.getElementById('catTools');
 if(tools){
  var q='',aud='',cat='';
  var apply=function(){
   var feat=document.getElementById('catFeatured'),alle=document.getElementById('catAll'),
       leer=document.getElementById('catEmpty'),browsing=!!(q||aud||cat);
   if(feat)feat.style.display=browsing?'none':'';
   if(alle)alle.style.display=browsing?'':'none';
   if(!browsing){if(leer)leer.style.display='none';return;}
   var any=false;
   all('#catAll .catsec').forEach(function(sec){
    var vis=0;
    [].slice.call(sec.querySelectorAll('.appcard')).forEach(function(c){
     var ok=true;
     if(q&&(c.getAttribute('data-name')||'').indexOf(q)<0)ok=false;
     if(aud){var a=c.getAttribute('data-aud')||'beide';if(a!=='beide'&&a!==aud)ok=false;}
     if(cat&&sec.getAttribute('data-cat')!==cat)ok=false;
     c.style.display=ok?'':'none';if(ok)vis++;
    });
    sec.style.display=vis?'':'none';if(vis)any=true;
   });
   if(leer)leer.style.display=any?'none':'block';
  };
  var s=document.getElementById('catSearch');
  if(s)s.addEventListener('input',function(){q=s.value.trim().toLowerCase();apply()});
  [].slice.call(tools.querySelectorAll('.seg button')).forEach(function(b){
   b.addEventListener('click',function(){
    [].slice.call(tools.querySelectorAll('.seg button')).forEach(function(x){
     x.classList.remove('on')});
    b.classList.add('on');aud=b.getAttribute('data-aud')||'';apply();
   });
  });
  [].slice.call(tools.querySelectorAll('.catchips button')).forEach(function(b){
   b.addEventListener('click',function(){
    var was=b.classList.contains('on');
    [].slice.call(tools.querySelectorAll('.catchips button')).forEach(function(x){
     x.classList.remove('on')});
    if(!was){b.classList.add('on');cat=b.getAttribute('data-cat')||'';}else{cat='';}
    apply();
   });
  });
 }
})();
"""

MANIFEST = json.dumps({
    "name": "weblab", "short_name": "weblab", "start_url": "/", "display": "standalone",
    "background_color": "#f2f2f7", "theme_color": "#f2f2f7", "lang": "de",
    "icons": [{"src": "/static/icon-180.png", "sizes": "180x180", "type": "image/png"},
              {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
              {"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
}, ensure_ascii=False)
