"""Systeminformationen: Leistung, Laufwerke, Netzwerk, offene Ports."""
import json
import os
import re
import shutil
import socket
import subprocess
import time

_prev_cpu = {"total": 0, "idle": 0, "ts": 0}


def _sh(cmd, timeout=20):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def cpu_percent():
    """CPU-Auslastung seit dem letzten Aufruf (Delta aus /proc/stat)."""
    try:
        with open("/proc/stat", encoding="utf-8") as fh:
            parts = fh.readline().split()
    except OSError:
        return 0.0
    values = [int(v) for v in parts[1:] if v.isdigit()]
    if len(values) < 4:
        return 0.0
    total, idle = sum(values), values[3] + (values[4] if len(values) > 4 else 0)
    dt_total = total - _prev_cpu["total"]
    dt_idle = idle - _prev_cpu["idle"]
    _prev_cpu.update({"total": total, "idle": idle, "ts": time.time()})
    if dt_total <= 0:
        return 0.0
    return round(max(0.0, min(100.0, (1 - dt_idle / dt_total) * 100)), 1)


def meminfo():
    info = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                num = rest.strip().split()
                if num and num[0].isdigit():
                    info[key] = int(num[0]) * 1024
    except OSError:
        return {"total": 0, "used": 0, "percent": 0.0}
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", info.get("MemFree", 0))
    used = max(0, total - available)
    return {
        "total": total, "used": used, "available": available,
        "percent": round(used / total * 100, 1) if total else 0.0,
    }


def loadavg():
    try:
        return os.getloadavg()
    except OSError:
        return (0.0, 0.0, 0.0)


def uptime_seconds():
    try:
        with open("/proc/uptime", encoding="utf-8") as fh:
            return float(fh.read().split()[0])
    except (OSError, ValueError):
        return 0.0


def cpu_count():
    return os.cpu_count() or 1


def hostname():
    return socket.gethostname()


def os_pretty():
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "Linux"


def kernel():
    return _sh(["uname", "-r"]).strip()


def mounts():
    """Beschreibbare Dateisysteme mit Belegung — Basis für „Datenlaufwerk“."""
    out = _sh(["df", "-PB1", "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs", "-x", "overlay"])
    rows = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        device, total, used, avail, _, target = parts
        if not total.isdigit():
            continue
        total_i, used_i = int(total), int(used)
        rows.append({
            "device": device, "mount": target,
            "total": total_i, "used": used_i, "available": int(avail),
            "percent": round(used_i / total_i * 100, 1) if total_i else 0.0,
        })
    rows.sort(key=lambda r: r["mount"])
    return rows


def disks():
    """Blockgeräte (lsblk) — physische Sicht auf die Laufwerke."""
    out = _sh(["lsblk", "-J", "-b", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,MODEL,FSTYPE"])
    try:
        return json.loads(out).get("blockdevices", [])
    except (json.JSONDecodeError, AttributeError):
        return []


def data_locations():
    """Auswahlmöglichkeiten für den Speicherort der App-Daten."""
    locations = []
    for mount in mounts():
        if mount["mount"] in ("/boot", "/boot/efi"):
            continue
        base = "/var/lib/weblab/data" if mount["mount"] == "/" else os.path.join(mount["mount"], "weblab")
        locations.append({
            "path": base, "mount": mount["mount"], "device": mount["device"],
            "free": mount["available"], "total": mount["total"],
        })
    return locations


def interfaces():
    out = _sh(["ip", "-j", "addr"])
    try:
        raw = json.loads(out)
    except json.JSONDecodeError:
        return []
    items = []
    for iface in raw:
        addrs = [
            {"family": a.get("family"), "address": a.get("local"), "prefix": a.get("prefixlen")}
            for a in iface.get("addr_info", []) if a.get("local")
        ]
        items.append({
            "name": iface.get("ifname"), "state": iface.get("operstate", "?"),
            "mac": iface.get("address", ""), "mtu": iface.get("mtu"), "addresses": addrs,
        })
    return items


_PORT_RE = re.compile(r'users:\(\("([^"]+)"')


def listening_ports():
    """Offene (lauschende) Ports inkl. Prozess — TCP und UDP."""
    rows = []
    for proto, flag in (("tcp", "-tln"), ("udp", "-uln")):
        out = _sh(["ss", flag, "-p"])
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 5:
                continue
            local = parts[4]
            host, _, port = local.rpartition(":")
            if not port.isdigit():
                continue
            match = _PORT_RE.search(line)
            rows.append({
                "proto": proto, "address": host or "*", "port": int(port),
                "process": match.group(1) if match else "",
                "scope": "intern" if host.strip("[]") in ("127.0.0.1", "::1") else "extern",
            })
    rows.sort(key=lambda r: (r["port"], r["proto"]))
    # Doppelte (IPv4+IPv6 auf gleichem Port/Prozess) zusammenfassen
    seen, unique = set(), []
    for row in rows:
        key = (row["proto"], row["port"], row["process"], row["scope"])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def free_port(start=20000, end=45000, taken=()):
    """Freien Host-Port finden (nicht belegt vom System, nicht von weblab reserviert)."""
    busy = {row["port"] for row in listening_ports()} | set(taken)
    for port in range(start, end):
        if port in busy:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
            except OSError:
                continue
        return port
    raise RuntimeError("Kein freier Port gefunden")


def public_ip():
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        out = _sh(["curl", "-s", "--max-time", "8", url], timeout=12).strip()
        if re.fullmatch(r"[0-9.]{7,15}", out):
            return out
    out = _sh(["hostname", "-I"]).split()
    return out[0] if out else ""


def service_active(name):
    return _sh(["systemctl", "is-active", name]).strip() == "active"


def human_bytes(num):
    num = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(num) < 1024:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} EB"


def human_uptime(seconds):
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days} T {hours} Std"
    if hours:
        return f"{hours} Std {minutes} Min"
    return f"{minutes} Min"


def overview():
    mem = meminfo()
    root = shutil.disk_usage("/")
    return {
        "hostname": hostname(), "os": os_pretty(), "kernel": kernel(),
        "cpu_percent": cpu_percent(), "cpu_count": cpu_count(),
        "load": loadavg(), "mem": mem,
        "disk": {"total": root.total, "used": root.used, "free": root.free,
                 "percent": round(root.used / root.total * 100, 1) if root.total else 0.0},
        "uptime": uptime_seconds(),
    }
