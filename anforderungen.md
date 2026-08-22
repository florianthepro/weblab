# Anforderungen & Komponentenwahl — Server-Kontrollzentrum

## Ziel
Ein sicheres, ultra-simples, web-basiertes Kontrollzentrum auf einem frischen Ubuntu-24.04-Server.
Ein Kommando installiert alles; danach Login mit dem **Linux-User** und ein Dashboard, das
Server + Software übersichtlich verwaltet — auf **einer** Domain (keine Subdomain-Wildwuchs).

## Prioritäten
1. **Sicherheit**  2. Features  3. Usability. (Frei/OSS bevorzugt.)

## Komponentenwahl (das „erste Auswählen der Sachen")
Auswahlkriterium Nr. 1 war Sicherheit: ausgereifte, langlebige Software mit sicheren Defaults
statt Eigenbau-Panel. Gewählt:

| Baustein | Produkt | Warum |
|---|---|---|
| Kontrollzentrum | **Cockpit** | In RHEL/Ubuntu integriert, enterprise-erprobt, **Login über PAM = Linux-User**, keine eigene Nutzerdatenbank. |
| Ressourcen/Übersicht | Cockpit Overview | CPU/RAM/Disk/Netz des Geräts auf einen Blick. |
| Laufwerke | **cockpit-storaged** | Datenträger/Partitionen/Mounts sicher verwalten. |
| Netzwerk/Ports | **cockpit-networkmanager** | Interfaces, Verbindungen, Firewall, offene Ports. |
| Software/Container | **cockpit-podman** (Podman) | Docker-kompatibel, **rootless-fähig**, kein Daemon-Root — bessere Isolation. |
| Reverse-Proxy/TLS | **Caddy** | Automatisches HTTPS (Let's Encrypt), minimale, sichere Config. |
| Domain/DNS | **Cloudflare-API** | A-Record der Domain wird beim Setup gesetzt (Token optional). |

## Sicherheit (Prio 1)
- Härtung: sysctl, `unattended-upgrades`, `fail2ban`, `chrony`.
- Firewall (ufw): nur **22/80/443** offen (WireGuard optional).
- Panel nur über **HTTPS** (Caddy); Cockpit lauscht intern auf 9090, **nicht öffentlich**.
- SSH: optional key-only (bei gesetztem `ADMIN_SSH_PUBKEY` wird root-/Passwort-Login gesperrt
  und ein sudo-User `ops` angelegt).

## Ablauf
1. `sudo bash software/run.sh` auf frischem Ubuntu 24.04.
2. Setup fragt **Domain** + optional **Cloudflare-Token** ab (oder `software/box.env`).
3. Härtung → Cockpit + Module + Caddy → DNS (A-Record Apex → Server-IP).
4. `https://DEINE-DOMAIN` öffnen, mit Linux-User einloggen.

## Kontrollzentrum-Bereiche (nach Login)
- **/ (Overview)**: Ressourcenverbrauch des Geräts (CPU/RAM/Disk/Netz).
- **Laufwerke (Storage)**: Datenträger verwalten.
- **Netzwerk/Ports**: Interfaces, Verbindungen, Firewall, offene Ports.
- **Software (Podman)**: Container verwalten — jede Software mit eigenem Port + Domain.

## Ehrliche Abgrenzung (was ein reifes Panel NICHT als Assistenten mitbringt)
- Einen bespoke Onboarding-Wizard „Domain wählen → Cloudflare → Ladebalken" gibt es in Cockpit
  nicht; deshalb erledigt das **Setup-Kommando** die Domain-/Cloudflare-Token-Konfiguration.
- Eine In-Panel-Verwaltung für „DNS-Zone" und „Webseiten" ist nicht Teil von Cockpit; DNS setzt
  das Setup über die Cloudflare-API, Webseiten laufen als Container (cockpit-podman) hinter Caddy.

## Konfiguration
Werte kommen aus `software/box.env` (siehe `box.env.example`) **oder** interaktiver Abfrage —
**keine Secrets im Repo**. Nach dem Setup Token/Passwörter rotieren.
