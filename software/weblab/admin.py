"""Kommandozeilen-Werkzeug für Automatisierung/Wartung.

  python3 admin.py set-domain example.com [IP]   Verwaltungs-Domain setzen + Proxy schreiben
  python3 admin.py set-password BENUTZER PASSWORT Passwort setzen (oder Benutzer anlegen)
  python3 admin.py status                         Kurzstatus ausgeben
"""
import sys

import catalog
import dockerctl
import integrations
import store
import sysinfo


def set_domain(domain, ip=None):
    store.init()
    store.set_setting("manage_domain", domain)
    store.set_setting("server_ip", ip or sysinfo.public_ip())
    routes = []
    for app in store.list_apps():
        connector = catalog.get(app["connector_id"])
        if connector and connector.get("http") and app.get("domain"):
            routes.append({"domain": app["domain"], "port": app["host_port"], "name": app["name"]})
    ok, err = integrations.write_caddyfile_safe(domain, routes)
    print(f"Domain: {domain}")
    print(f"Server-IP: {store.get_setting('server_ip')}")
    print(f"Proxy geschrieben: {ok}{'' if ok else ' — ' + str(err)}")
    return 0 if ok else 1


def set_password(username, password):
    store.init()
    if len(password) < 10:
        print("Passwort zu kurz (min. 10 Zeichen).")
        return 1
    for user in store.list_users():
        if user["username"] == username:
            store.set_password(user["id"], password)
            print(f"Passwort von {username} geändert.")
            return 0
    store.create_user(username, password)
    print(f"Benutzer {username} angelegt.")
    return 0


def status():
    store.init()
    print(f"Setup abgeschlossen: {'ja' if store.is_setup_done() else 'nein'}")
    print(f"Domain: {store.get_setting('manage_domain') or '—'}")
    print(f"Server-IP: {store.get_setting('server_ip') or '—'}")
    print(f"Benutzer: {store.user_count()}")
    print(f"Apps: {len(store.list_apps())}")
    print(f"Connectors: {len(catalog.load_all())}")
    print(f"Docker: {'aktiv' if dockerctl.available() else 'nicht verfügbar'}")
    return 0


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    command = argv[1]
    if command == "set-domain" and len(argv) >= 3:
        return set_domain(argv[2], argv[3] if len(argv) > 3 else None)
    if command == "set-password" and len(argv) >= 4:
        return set_password(argv[2], argv[3])
    if command == "status":
        return status()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
