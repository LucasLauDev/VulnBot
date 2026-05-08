"""Docker / docker-compose lifecycle management for VulnBot benchmarks.

Modeled after the PentestGPT runner's ``docker_manager``: the runner builds,
starts, queries the host port, and tears down each benchmark's
``docker-compose.yml``.

The Kali SSH side of VulnBot (``VulnBot/docker-compose.yml`` → ``kali-ssh``)
must be running independently; ``ensure_kali_running`` performs a soft check
and prints a hint if it is missing.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


class DockerManager:
    """Wraps ``docker compose`` for benchmark target containers."""

    BUILD_TIMEOUT = 600
    STARTUP_TIMEOUT = 180
    STOP_TIMEOUT = 180

    _PORT_HOST_PATTERNS = [
        re.compile(r"0\.0\.0\.0:(\d+)->(\d+)/tcp"),
        re.compile(r"127\.0\.0\.1:(\d+)->(\d+)/tcp"),
        re.compile(r":::(\d+)->(\d+)/tcp"),
    ]

    def start_benchmark(self, benchmark_path: Path) -> dict:
        """Build and start the benchmark stack. Returns dict with status."""
        compose = benchmark_path / "docker-compose.yml"
        if not compose.exists():
            return {
                "success": False,
                "target_url": None,
                "host_port": None,
                "ports": [],
                "message": f"No docker-compose.yml in {benchmark_path}",
            }

        build = subprocess.run(
            ["docker", "compose", "build"],
            cwd=str(benchmark_path),
            capture_output=True,
            text=True,
            timeout=self.BUILD_TIMEOUT,
        )
        if build.returncode != 0:
            return {
                "success": False,
                "target_url": None,
                "host_port": None,
                "ports": [],
                "message": f"build failed:\n{build.stderr or build.stdout}",
            }

        up = subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=str(benchmark_path),
            capture_output=True,
            text=True,
            timeout=self.STARTUP_TIMEOUT,
        )
        if up.returncode != 0:
            return {
                "success": False,
                "target_url": None,
                "host_port": None,
                "ports": [],
                "message": f"up -d failed:\n{up.stderr or up.stdout}",
            }

        ports = self.get_exposed_ports(benchmark_path)
        if not ports:
            return {
                "success": True,
                "target_url": None,
                "host_port": None,
                "ports": [],
                "message": (
                    "Containers running but no host-mapped TCP port detected. "
                    "Target will be reached via container name on docker network."
                ),
            }

        host_port = ports[0]
        target_url = f"http://host.docker.internal:{host_port}"
        return {
            "success": True,
            "target_url": target_url,
            "host_port": host_port,
            "ports": ports,
            "message": f"Benchmark started, host ports: {ports}",
        }

    def stop_benchmark(self, benchmark_path: Path) -> dict:
        """Tear down the benchmark stack and remove volumes."""
        if not benchmark_path.exists():
            return {"success": False, "message": f"path missing: {benchmark_path}"}

        result = subprocess.run(
            ["docker", "compose", "down", "-v", "--remove-orphans"],
            cwd=str(benchmark_path),
            capture_output=True,
            text=True,
            timeout=self.STOP_TIMEOUT,
        )
        if result.returncode != 0:
            return {
                "success": False,
                "message": f"down failed:\n{result.stderr or result.stdout}",
            }
        return {"success": True, "message": "stack stopped"}

    def get_exposed_ports(self, benchmark_path: Path) -> list[int]:
        """Return host-mapped TCP ports for the running stack, deduplicated."""
        seen: list[int] = []

        ps = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            cwd=str(benchmark_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if ps.returncode == 0 and ps.stdout.strip():
            for line in ps.stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                pub = rec.get("Publishers") or []
                for entry in pub:
                    host_port = entry.get("PublishedPort")
                    if isinstance(host_port, int) and host_port > 0 and host_port not in seen:
                        seen.append(host_port)
            if seen:
                return seen

        ps_text = subprocess.run(
            ["docker", "compose", "ps", "--format", "{{.Ports}}"],
            cwd=str(benchmark_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if ps_text.returncode != 0:
            return []
        for line in ps_text.stdout.splitlines():
            for pat in self._PORT_HOST_PATTERNS:
                for m in pat.finditer(line):
                    port = int(m.group(1))
                    if port > 0 and port not in seen:
                        seen.append(port)
        return seen


def ensure_kali_running(container_hint: str = "kali-ssh") -> tuple[bool, str]:
    """Best-effort check that VulnBot's Kali SSH container is running.

    Returns ``(ok, message)``. Only emits a warning — the runner continues
    either way because the user might have a stand-alone Kali host.
    """
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"docker ps failed: {e}"

    if result.returncode != 0:
        return False, result.stderr.strip() or "docker ps returned non-zero"

    names = [n.strip() for n in result.stdout.splitlines() if n.strip()]
    for name in names:
        if container_hint in name:
            return True, f"found container: {name}"
    return False, (
        f"No container matching {container_hint!r}. "
        "Start it with `docker compose up -d` from the VulnBot root."
    )
