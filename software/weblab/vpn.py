"""VPN: privater Zugriff über Tailscale (eingehend) und ausgehende Tunnel
(Mullvad/ProtonVPN via gluetun). Alles nur aktiv, wenn eine App es ausdrücklich nutzt."""
import json
import subprocess

import dockerctl

GLUETUN_IMAGE = "qmcgaw/gluetun:v3"
EGRESS_PREFIX = "vpn-"


def _run(args, timeout=60):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------- Tailscale ---
def ts_installed():
    result = _run(["sh", "-c", "command -v tailscale"])
    return bool(result and result.returncode == 0 and result.stdout.strip())


def ts_install():
    if ts_installed():
        return True, None
    result = _run(["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"], timeout=240)
    if result and result.returncode == 0:
        return True, None
    return False, (result.stderr.strip() if result else "Installation fehlgeschlagen")


def ts_up(authkey, hostname="weblab"):
    ok, err = ts_install()
    if not ok:
        return False, err
    _run(["systemctl", "enable", "--now", "tailscaled"], timeout=30)
    result = _run(["tailscale", "up", "--authkey", authkey, "--hostname", hostname,
                   "--accept-dns=false"], timeout=60)
    if result and result.returncode == 0:
        return True, None
    return False, (result.stderr.strip() if result else "tailscale up fehlgeschlagen")


def ts_down():
    _run(["tailscale", "down"], timeout=30)
    return True


def ts_ip():
    result = _run(["tailscale", "ip", "-4"], timeout=15)
    if result and result.returncode == 0:
        return result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    return ""


def ts_status():
    """{'connected':bool,'ip':str,'hostname':str,'tailnet':str}."""
    if not ts_installed():
        return {"connected": False, "installed": False, "ip": "", "hostname": "", "tailnet": ""}
    result = _run(["tailscale", "status", "--json"], timeout=15)
    if not result or result.returncode != 0:
        return {"connected": False, "installed": True, "ip": "", "hostname": "", "tailnet": ""}
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return {"connected": False, "installed": True, "ip": "", "hostname": "", "tailnet": ""}
    self_node = data.get("Self") or {}
    ips = self_node.get("TailscaleIPs") or []
    ipv4 = next((ip for ip in ips if ":" not in ip), "")
    return {
        "connected": data.get("BackendState") == "Running",
        "installed": True,
        "ip": ipv4,
        "hostname": (self_node.get("HostName") or ""),
        "tailnet": (data.get("CurrentTailnet") or {}).get("Name", ""),
    }


# ------------------------------------------------- Ausgehende Tunnel (gluetun) -
def egress_name(app_slug):
    """Container-Name des VPN-Ausgangs einer App."""
    return f"{EGRESS_PREFIX}{app_slug}"


def egress_env(egress):
    """gluetun-Env aus einer gespeicherten Ausgang-Konfiguration."""
    env = {
        "VPN_SERVICE_PROVIDER": egress.get("provider", "custom"),
        "VPN_TYPE": "wireguard",
        "WIREGUARD_PRIVATE_KEY": egress.get("private_key", ""),
        "WIREGUARD_ADDRESSES": egress.get("addresses", ""),
    }
    if egress.get("location"):
        env["SERVER_CITIES"] = egress["location"]
    return env


def egress_up(app_slug, egress, ports, input_ports):
    """gluetun-Sidecar für eine App starten; er veröffentlicht die App-Ports und
    führt den ausgehenden Verkehr durch Mullvad/ProtonVPN.

    ports: Liste (bind, container_port, proto) — wie sonst die App-Ports.
    input_ports: Container-Ports, die gluetun eingehend zulassen soll.
    """
    env = egress_env(egress)
    if input_ports:
        env["FIREWALL_INPUT_PORTS"] = ",".join(str(p) for p in input_ports)
    slug = egress_name(app_slug)
    dockerctl.run_container(
        slug=slug, image=GLUETUN_IMAGE, env=env, ports=ports,
        cap_add=["NET_ADMIN"], devices=["/dev/net/tun"],
    )
    return dockerctl.container_name(slug)


def egress_down(app_slug):
    dockerctl.remove(egress_name(app_slug), missing_ok=True)
