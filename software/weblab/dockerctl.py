"""Docker-Steuerung über die CLI (keine externen Python-Abhängigkeiten)."""
import json
import shlex
import subprocess

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


def available():
    try:
        _run(["version", "--format", "{{.Server.Version}}"], timeout=15)
        return True
    except Exception:
        return False


def container_name(slug):
    return f"{PREFIX}{slug}"


def ps():
    """Alle weblab-Container mit Status."""
    out = _run(["ps", "-a", "--filter", f"label={LABEL}", "--format", "{{json .}}"], check=False)
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
    out = _run(["inspect", "-f", "{{.State.Status}}", container_name(slug)], check=False).strip()
    return out or "missing"


def stats():
    """CPU/RAM-Verbrauch je laufendem weblab-Container."""
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
    return result


def run_container(slug, image, env=None, ports=None, volumes=None, cpu=None,
                  ram_mb=None, network=None, restart="unless-stopped", hostname=None):
    """Container (neu) starten. Ein bestehender gleichen Namens wird ersetzt."""
    remove(slug, missing_ok=True)
    args = ["run", "-d", "--name", container_name(slug),
            "--label", f"{LABEL}={slug}", "--restart", restart]
    if hostname:
        args += ["--hostname", hostname]
    for key, value in (env or {}).items():
        args += ["-e", f"{key}={value}"]
    for bind, container_port, proto in (ports or []):
        args += ["-p", f"{bind}:{container_port}/{proto}"]
    for host_path, container_path in (volumes or []):
        args += ["-v", f"{host_path}:{container_path}"]
    if cpu:
        args += ["--cpus", str(cpu)]
    if ram_mb:
        args += ["--memory", f"{int(ram_mb)}m"]
    if network and network != "bridge":
        args += ["--network", network]
    args.append(image)
    return _run(args, timeout=600).strip()


def start(slug):
    return _run(["start", container_name(slug)]).strip()


def stop(slug):
    return _run(["stop", "-t", "20", container_name(slug)], timeout=60).strip()


def restart(slug):
    return _run(["restart", "-t", "20", container_name(slug)], timeout=90).strip()


def remove(slug, missing_ok=False):
    return _run(["rm", "-f", container_name(slug)], check=not missing_ok, timeout=90).strip()


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
    out = _run(["network", "ls", "--format", "{{json .}}"], check=False)
    items = []
    for line in out.splitlines():
        if line.strip():
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return items


def network_details(name):
    out = _run(["network", "inspect", name], check=False, timeout=30)
    try:
        data = json.loads(out)
        return data[0] if data else {}
    except (json.JSONDecodeError, IndexError):
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
