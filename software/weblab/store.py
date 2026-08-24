"""SQLite-Speicher: Einstellungen, Benutzer, installierte Apps."""
import contextlib
import hashlib
import json
import os
import secrets
import sqlite3
import time

DB_PATH = os.environ.get("WEBLAB_DB", "/var/lib/weblab/weblab.db")


@contextlib.contextmanager
def connect():
    """Verbindung als Kontextmanager: committet bei Erfolg, schließt immer.
    busy_timeout lässt parallele Zugriffe warten statt zu scheitern (Threading-Server)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=8000")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  username   TEXT UNIQUE NOT NULL,
  pw_hash    TEXT NOT NULL,
  pw_salt    TEXT NOT NULL,
  role       TEXT NOT NULL DEFAULT 'admin',
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS apps (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  slug           TEXT UNIQUE NOT NULL,
  name           TEXT NOT NULL,
  connector_id   TEXT NOT NULL,
  group_id       TEXT NOT NULL,
  version        TEXT NOT NULL,
  domain         TEXT NOT NULL DEFAULT '',
  exposure       TEXT NOT NULL DEFAULT 'external',
  allow_cidr     TEXT NOT NULL DEFAULT '',
  host_port      INTEGER NOT NULL,
  container_port INTEGER NOT NULL,
  location       TEXT NOT NULL DEFAULT 'docker',
  network        TEXT NOT NULL DEFAULT 'bridge',
  data_path      TEXT NOT NULL DEFAULT '',
  cpu            REAL NOT NULL DEFAULT 1.0,
  ram_mb         INTEGER NOT NULL DEFAULT 1024,
  manage_host    TEXT NOT NULL DEFAULT '',
  values_json    TEXT NOT NULL DEFAULT '{}',
  owner_id       INTEGER,
  perms_json     TEXT NOT NULL DEFAULT '{}',
  created_at     INTEGER NOT NULL
);
"""

# Nachträglich ergänzte Spalten (Migration bestehender Datenbanken).
_MIGRATIONS = {"apps": {"manage_host": "TEXT NOT NULL DEFAULT ''",
                        "egress_id": "TEXT NOT NULL DEFAULT ''",
                        "owner_id": "INTEGER",
                        "perms_json": "TEXT NOT NULL DEFAULT '{}'"}}


def _migrate(conn):
    for table, columns in _MIGRATIONS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for column, decl in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init():
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        _backfill_app_domains(conn)
        if not _get(conn, "session_secret"):
            _set(conn, "session_secret", secrets.token_hex(32))


def _backfill_app_domains(conn):
    """Alt-Installationen: die getrennte Nextcloud-Trusted-Domain gibt es nicht mehr —
    ihren Wert in die App-Domain uebernehmen, damit bestehende Apps erreichbar bleiben."""
    try:
        rows = conn.execute("SELECT id, group_id, domain, values_json FROM apps").fetchall()
    except sqlite3.OperationalError:
        return
    for row in rows:
        if (row["group_id"] or "") != "nextcloud" or (row["domain"] or "").strip():
            continue
        try:
            vals = json.loads(row["values_json"] or "{}")
        except (ValueError, TypeError):
            vals = {}
        trusted = (vals.get("trusted_domain") or "").strip().split()
        if trusted:
            conn.execute("UPDATE apps SET domain=? WHERE id=?", (trusted[0], row["id"]))


# ---------- settings ----------
def _get(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _set(conn, key, value):
    conn.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def get_setting(key, default=None):
    with connect() as conn:
        return _get(conn, key, default)


def set_setting(key, value):
    with connect() as conn:
        _set(conn, key, value)


def all_settings():
    with connect() as conn:
        return {r["key"]: r["value"] for r in conn.execute("SELECT key,value FROM settings")}


def is_setup_done():
    return get_setting("setup_done") == "1"


# ---------- users ----------
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=32
    ).hex()
    return digest, salt


def create_user(username, password, role="admin"):
    digest, salt = hash_password(password)
    with connect() as conn:
        conn.execute(
            "INSERT INTO users(username,pw_hash,pw_salt,role,created_at) VALUES(?,?,?,?,?)",
            (username, digest, salt, role, int(time.time())),
        )


def verify_user(username, password):
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        # Gleiche Laufzeit wie bei vorhandenem Benutzer.
        hash_password(password, "decoy-salt-000000")
        return None
    digest, _ = hash_password(password, row["pw_salt"])
    if secrets.compare_digest(digest, row["pw_hash"]):
        return dict(row)
    return None


def get_user(uid):
    with connect() as conn:
        row = conn.execute("SELECT id,username,role,created_at FROM users WHERE id=?", (uid,)).fetchone()
        return dict(row) if row else None


def apps_for_owner(owner_id):
    with connect() as conn:
        return [_row_to_app(r) for r in conn.execute(
            "SELECT * FROM apps WHERE owner_id=? ORDER BY name", (owner_id,))]


def set_app_owner(app_id, owner_id, perms):
    with connect() as conn:
        conn.execute("UPDATE apps SET owner_id=?, perms_json=? WHERE id=?",
                     (owner_id, json.dumps(perms or {}), app_id))


def list_users():
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id,username,role,created_at FROM users ORDER BY id")]


def user_count():
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]


def set_password(user_id, password):
    digest, salt = hash_password(password)
    with connect() as conn:
        conn.execute("UPDATE users SET pw_hash=?, pw_salt=? WHERE id=?", (digest, salt, user_id))


def delete_user(user_id):
    with connect() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))


# ---------- apps ----------
APP_COLUMNS = (
    "slug name connector_id group_id version domain exposure allow_cidr host_port "
    "container_port location network data_path cpu ram_mb manage_host egress_id values_json "
    "owner_id perms_json"
).split()


def create_app(data):
    fields = {k: data[k] for k in APP_COLUMNS if k in data}
    fields["created_at"] = int(time.time())
    cols = ",".join(fields)
    marks = ",".join("?" for _ in fields)
    with connect() as conn:
        cur = conn.execute(f"INSERT INTO apps({cols}) VALUES({marks})", tuple(fields.values()))
        return cur.lastrowid


def update_app(app_id, data):
    fields = {k: v for k, v in data.items() if k in APP_COLUMNS}
    if not fields:
        return
    sets = ",".join(f"{k}=?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE apps SET {sets} WHERE id=?", (*fields.values(), app_id))


def _row_to_app(row):
    app = dict(row)
    try:
        app["values"] = json.loads(app.get("values_json") or "{}")
    except json.JSONDecodeError:
        app["values"] = {}
    try:
        app["perms"] = json.loads(app.get("perms_json") or "{}")
    except json.JSONDecodeError:
        app["perms"] = {}
    return app


def list_apps():
    with connect() as conn:
        return [_row_to_app(r) for r in conn.execute("SELECT * FROM apps ORDER BY name")]


def get_app(app_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    return _row_to_app(row) if row else None


def get_app_by_slug(slug):
    with connect() as conn:
        row = conn.execute("SELECT * FROM apps WHERE slug=?", (slug,)).fetchone()
    return _row_to_app(row) if row else None


def delete_app(app_id):
    with connect() as conn:
        conn.execute("DELETE FROM apps WHERE id=?", (app_id,))


def used_host_ports():
    with connect() as conn:
        return {r["host_port"] for r in conn.execute("SELECT host_port FROM apps")}


# ---------- Cloudflare-Konten (mehrere) ----------
def cf_accounts():
    """Liste verknüpfter Cloudflare-Konten: [{id,label,token}]. Migriert Alt-Einzeltoken."""
    raw = get_setting("cf_accounts", "")
    accounts = []
    if raw:
        try:
            accounts = json.loads(raw)
        except json.JSONDecodeError:
            accounts = []
    if not accounts:
        legacy = get_setting("cf_token", "")
        if legacy:
            accounts = [{"id": "legacy", "label": get_setting("cf_account", "") or "Cloudflare",
                         "token": legacy}]
            set_setting("cf_accounts", json.dumps(accounts))
    return accounts


def add_cf_account(label, token):
    accounts = cf_accounts()
    acc_id = hashlib.sha1(token.encode()).hexdigest()[:8]
    accounts = [a for a in accounts if a.get("id") != acc_id]
    accounts.append({"id": acc_id, "label": label or "Cloudflare", "token": token})
    set_setting("cf_accounts", json.dumps(accounts))
    set_setting("cf_token", token)          # Rückwärtskompatibilität (erstes Konto)
    return acc_id


def remove_cf_account(acc_id):
    accounts = [a for a in cf_accounts() if a.get("id") != acc_id]
    set_setting("cf_accounts", json.dumps(accounts))
    set_setting("cf_token", accounts[0]["token"] if accounts else "")


def cf_connected():
    return bool(cf_accounts())


# ---------- VPN-Ausgänge (Mullvad/Proton, via WireGuard) ----------
def vpn_egress():
    """Liste ausgehender VPN-Tunnel: [{id,label,provider,private_key,addresses,location}]."""
    raw = get_setting("vpn_egress", "")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def add_vpn_egress(label, provider, private_key, addresses, location=""):
    items = vpn_egress()
    eid = hashlib.sha1(f"{provider}:{addresses}:{private_key}".encode()).hexdigest()[:8]
    items = [x for x in items if x.get("id") != eid]
    items.append({"id": eid, "label": label or provider, "provider": provider,
                  "private_key": private_key, "addresses": addresses, "location": location})
    set_setting("vpn_egress", json.dumps(items))
    return eid


def remove_vpn_egress(eid):
    set_setting("vpn_egress", json.dumps([x for x in vpn_egress() if x.get("id") != eid]))


def vpn_egress_get(eid):
    return next((x for x in vpn_egress() if x.get("id") == eid), None)
