"""Rechte-Modell für geteilte Apps.

Rollen: 'admin' (Besitzer des Servers, darf alles) und 'user' (eingeschränkt).
Ein eingeschränkter Nutzer sieht und bedient NUR seine eigenen Apps und darin nur
das, was der Connector als Nutzer-Sache vorsieht (plus/minus Freigaben des Admins);
Ressourcen (RAM/CPU) nur bis zu einem vom Admin gesetzten Maximum.

Grundsatz: default-deny. Wer nicht Besitzer der App ist, hat keinen Zugriff — so
kann ein Nutzer weder andere Apps beeinflussen noch fremde Daten sehen.
"""

# Diese Aktionen/Bereiche werden NIE an einen Nutzer delegiert — sie könnten andere
# Apps oder das System betreffen und bleiben immer beim Admin.
NEVER_DELEGATE = {"delete", "transfer", "domain", "exposure", "network",
                  "allow_cidr", "egress", "move", "install"}

# Sichere Grundrechte auf der EIGENEN App (betreffen keine andere App, keine fremden
# Daten): der Nutzer darf seine App steuern, Logs/Dateien seiner App sehen und
# Ressourcen bis zum Limit anpassen. Einstellungen bleiben default-deny.
BASELINE_ACTIONS = {"logs", "start", "stop", "restart", "files", "resources"}
BASELINE_CAPS = {"ram_mb", "cpu"}


def is_admin(user):
    return bool(user) and user.get("role") == "admin"


def owns(user, app):
    return bool(user and app and app.get("owner_id") is not None
                and app.get("owner_id") == user.get("id"))


def _connector_delegate(connector):
    d = (connector or {}).get("delegate") or {}
    return set(d.get("fields") or []), set(d.get("actions") or []), set(d.get("caps") or [])


def effective(user, app, connector):
    """Was DIESER Nutzer bei DIESER App darf. Admin -> alles. Kein Besitzer -> None."""
    if is_admin(user):
        return {"admin": True, "fields": "*", "actions": "*", "caps": {}, "mode": "admin"}
    if not owns(user, app):
        return None
    fields, actions, cap_keys = _connector_delegate(connector)
    actions |= BASELINE_ACTIONS          # sichere Grundrechte auf der eigenen App
    cap_keys |= BASELINE_CAPS
    perms = app.get("perms") or {}
    for grant in perms.get("grant", []):
        kind, _, name = str(grant).partition(":")
        (fields if kind == "field" else actions).add(name)
    for revoke in perms.get("revoke", []):
        kind, _, name = str(revoke).partition(":")
        (fields if kind == "field" else actions).discard(name)
    actions -= NEVER_DELEGATE
    fields -= NEVER_DELEGATE
    return {"admin": False, "fields": fields, "actions": actions,
            "cap_keys": cap_keys, "caps": perms.get("caps") or {},
            "mode": perms.get("mode", "login")}


def can_action(eff, action):
    if not eff:
        return False
    if eff.get("admin"):
        return True
    if action in NEVER_DELEGATE:
        return False
    return action in eff.get("actions", set())


def can_field(eff, field_key):
    if not eff:
        return False
    if eff.get("admin"):
        return True
    if field_key in NEVER_DELEGATE:
        return False
    return eff.get("fields") == "*" or field_key in eff.get("fields", set())


def cap_value(eff, key, requested, current):
    """Ressourcen-Grenze anwenden (RAM/CPU): der Nutzer darf höchstens bis zum vom
    Admin gesetzten Maximum; ohne gesetztes Cap darf er den Wert nicht ändern.
    Admin ist frei. Gibt den erlaubten Wert zurück."""
    if not eff or eff.get("admin"):
        return requested
    if key not in eff.get("cap_keys", set()):
        return current                    # nicht delegiert -> unverändert lassen
    limit = (eff.get("caps") or {}).get(key)
    if limit in (None, ""):
        return current                    # Admin hat kein Limit gesetzt -> nicht änderbar
    try:
        return min(type(current)(requested), type(current)(limit))
    except (TypeError, ValueError):
        return current
