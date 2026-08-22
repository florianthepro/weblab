# weblab — sicheres Server-Kontrollzentrum

Ein Kommando macht aus einem frischen **Ubuntu 24.04 LTS** einen gehärteten Server mit
web-basiertem Kontrollzentrum: **Cockpit** (Login mit dem **Linux-User**) hinter **Caddy**
(automatisches HTTPS). Dashboard mit Ressourcen, **Laufwerken**, **Netzwerk/Ports** und
**Software/Containern (Podman)** — auf einer Domain.

## Installation (als root)

```bash
git clone https://github.com/florianthepro/weblab && sudo bash weblab/software/run.sh
```

Das Setup fragt **Domain** und (optional) **Cloudflare-API-Token** ab — oder trage sie
vorab in `software/box.env` ein (`cp software/box.env.example software/box.env`).

Danach **`https://DEINE-DOMAIN`** öffnen und mit dem **Linux-User** einloggen.

Vorgaben & Komponentenwahl: [`anforderungen.md`](anforderungen.md)
