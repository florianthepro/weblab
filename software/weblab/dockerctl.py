"""Docker-Steuerung über die CLI."""
import json
import shlex
import subprocess
import threading
import time

PREFIX = "weblab-"
LABEL = "weblab.app"


class DockerError(RuntimeError):
    pass


def _run(args, timeout=180, check=True, stdin=None):
    proc = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, input=stdin
    )
    if check and proc.returncode != 0:
        raise DockerError((proc.stderr or proc.stdout or "docker-Fehler").strip())
    return proc.stdout


_AVAIL = {"value": None, "ts": 0.0}
_STATES = {"map": {}, "ts": 0.0, "gen": 0}
_STATS = {"map": {}, "ts": 0.0, "gen": 0}
_CACHE_LOCK = threading.Lock()
STATE_TTL = 2.0
STATS_TTL = 6.0


def available():
    now = time.monotonic()
    with _CACHE_LOCK:
        age = now - _AVAIL["ts"]
        if _AVAIL["value"] is True and age < 60 or _AVAIL["value"] is False and age < 5:
            return _AVAIL["value"]
    try:
        _run(["version", "--format", "{{.Server.Version}}"], timeout=15)
        value = True
    except Exception:
        value = False
    with _CACHE_LOCK:
        _AVAIL.update({"value": value, "ts": now})
    return value


def _invalidate():
    with _CACHE_LOCK:
        _STATES["ts"] = _STATS["ts"] = 0.0
        _STATES["gen"] += 1
        _STATS["gen"] += 1


def container_name(slug):
    return f"{PREFIX}{slug}"


def ps():
    """Alle weblab-Container mit Status."""
    out = _run(["ps", "-a", "--filter", f"label={LABEL}", "--format", "{{json .}}"],
               check=False, timeout=10)
    items = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return items


def status(slug):
    """Exakter Zustand eines Containers (für Steuerungslogik, nie aus dem Cache)."""
    out = _run(["inspect", "-f", "{{.State.Status}}", container_name(slug)],
               check=False, timeout=10).strip()
    return out or "missing"


def states(max_age=STATE_TTL):
    """slug -> Zustand aus EINEM 'docker ps -a' — für Anzeigen statt N Einzelabfragen."""
    now = time.monotonic()
    with _CACHE_LOCK:
        if now - _STATES["ts"] <= max_age:
            return dict(_STATES["map"])
        gen = _STATES["gen"]
    data = {}
    if available():
        for row in ps():
            name = row.get("Names") or row.get("Name") or ""
            if name.startswith(PREFIX):
                data[name[len(PREFIX):]] = (row.get("State") or "").lower() or "missing"
    with _CACHE_LOCK:
        if gen == _STATES["gen"]:      # zwischenzeitliche Aktion schlaegt die alte Abfrage
            _STATES.update({"map": data, "ts": time.monotonic()})
    return dict(data)


def stats(max_age=STATS_TTL):
    """CPU/RAM-Verbrauch je laufendem weblab-Container ('docker stats' braucht ~1-2 s)."""
    now = time.monotonic()
    with _CACHE_LOCK:
        if now - _STATS["ts"] <= max_age:
            return dict(_STATS["map"])
        gen = _STATS["gen"]
    out = _run(["stats", "--no-stream", "--format", "{{json .}}"], check=False, timeout=45)
    result = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = row.get("Name", "")
        if name.startswith(PREFIX):
            result[name[len(PREFIX):]] = {
                "cpu": row.get("CPUPerc", "0%"),
                "mem": row.get("MemUsage", ""),
                "mem_perc": row.get("MemPerc", "0%"),
                "net": row.get("NetIO", ""),
                "block": row.get("BlockIO", ""),
            }
    with _CACHE_LOCK:
        if gen == _STATS["gen"]:
            _STATS.update({"map": result, "ts": time.monotonic()})
    return result


def run_container(slug, image, env=None, ports=None, volumes=None, cpu=None,
                  ram_mb=None, network=None, restart="unless-stopped", hostname=None,
                  cap_add=None, devices=None, network_mode=None):
    """Container starten; ein bestehender gleichen Namens wird ersetzt.

    network_mode: z. B. "container:weblab-vpn-x" — die App teilt sich das Netz eines
    anderen Containers (VPN-Ausgang). Dann keine eigenen Ports/Netzwerke/Hostname.
    """
    remove(slug, missing_ok=True)
    args = ["run", "-d", "--name", container_name(slug),
            "--label", f"{LABEL}={slug}", "--restart", restart]
    if network_mode:
        args += ["--network", network_mode]
    elif hostname:
        args += ["--hostname", hostname]
    for cap in cap_add or []:
        args += ["--cap-add", cap]
    for dev in devices or []:
        args += ["--device", dev]
    for key, value in (env or {}).items():
        args += ["-e", f"{key}={value}"]
    if not network_mode:
        for bind, container_port, proto in (ports or []):
            args += ["-p", f"{bind}:{container_port}/{proto}"]
    for host_path, container_path in (volumes or []):
        args += ["-v", f"{host_path}:{container_path}"]
    if cpu:
        args += ["--cpus", str(cpu)]
    if ram_mb:
        args += ["--memory", f"{int(ram_mb)}m"]
    if network and network != "bridge" and not network_mode:
        args += ["--network", network]
    args.append(image)
    try:
        return _run(args, timeout=600).strip()
    finally:
        _invalidate()


def start(slug):
    try:
        return _run(["start", container_name(slug)]).strip()
    finally:
        _invalidate()


def stop(slug):
    try:
        return _run(["stop", "-t", "20", container_name(slug)], timeout=60).strip()
    finally:
        _invalidate()


def restart(slug):
    try:
        return _run(["restart", "-t", "20", container_name(slug)], timeout=90).strip()
    finally:
        _invalidate()


def remove(slug, missing_ok=False):
    try:
        return _run(["rm", "-f", container_name(slug)], check=not missing_ok, timeout=90).strip()
    finally:
        _invalidate()


def logs(slug, tail=200):
    return _run(["logs", "--tail", str(tail), container_name(slug)], check=False, timeout=30)


def pull(image):
    return _run(["pull", image], timeout=900)


def exec_sh(slug, script, timeout=60):
    """Shell-Kommando im Container ausführen (sh -c)."""
    return _run(["exec", container_name(slug), "sh", "-c", script], timeout=timeout, check=False)


def read_file(slug, path):
    return _run(["exec", container_name(slug), "sh", "-c", f"cat {shlex.quote(path)} 2>/dev/null"],
                check=False, timeout=30)


def set_file_line(slug, path, prefix, value):
    """Zeile, die mit `prefix` beginnt, auf `prefix+value` setzen (oder anhängen)."""
    quoted_path = shlex.quote(path)
    line = f"{prefix}{value}"
    script = (
        f"touch {quoted_path}; "
        f"if grep -q '^{prefix}' {quoted_path} 2>/dev/null; then "
        f"  sed -i \"s|^{prefix}.*|{line}|\" {quoted_path}; "
        f"else echo {shlex.quote(line)} >> {quoted_path}; fi"
    )
    return _run(["exec", container_name(slug), "sh", "-c", script], check=False, timeout=30)


# ---------- Netzwerke / Subnetze ----------
def networks():
    out = _run(["network", "ls", "--format", "{{json .}}"], check=False, timeout=10)
    items = []
    for line in out.splitlines():
        if line.strip():
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return items


def network_map(names=None):
    """Alle Netze in EINEM inspect-Aufruf (statt einem pro Netz)."""
    names = names or [n["Name"] for n in networks()]
    if not names:
        return {}
    out = _run(["network", "inspect", *names], check=False, timeout=10)
    try:
        return {item.get("Name"): item for item in json.loads(out)}
    except (json.JSONDecodeError, TypeError):
        return {}


def create_network(name, subnet=None, gateway=None, internal=False):
    args = ["network", "create"]
    if subnet:
        args += ["--subnet", subnet]
    if gateway:
        args += ["--gateway", gateway]
    if internal:
        args.append("--internal")
    args.append(name)
    return _run(args, timeout=60).strip()


def remove_network(name):
    return _run(["network", "rm", name], timeout=60).strip()
