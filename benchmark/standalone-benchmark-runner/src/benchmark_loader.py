"""Detect and load XBOW and Vulhub benchmark sets from disk.

Auto-detection rules
--------------------

* If ``benchmarks_dir`` contains at least one folder matching ``XBEN-*-24``
  with a ``benchmark.json`` inside, the kind is ``xbow``.
* Otherwise, if ``benchmarks_dir`` contains nested folders that each have a
  ``docker-compose.yml`` and a ``README.md`` (the Vulhub layout), the kind is
  ``vulhub``.
* If neither layout is found, ``FileNotFoundError`` is raised so the caller
  can present a helpful error.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import BenchmarkInfo


_README_EXCERPT_LEN = 1500


def detect_kind(benchmarks_dir: Path) -> str:
    """Return ``"xbow"`` or ``"vulhub"`` based on directory layout."""
    if not benchmarks_dir.exists() or not benchmarks_dir.is_dir():
        raise FileNotFoundError(f"Benchmarks directory not found: {benchmarks_dir}")

    if any((benchmarks_dir / p.name / "benchmark.json").exists()
           for p in benchmarks_dir.iterdir()
           if p.is_dir() and p.name.startswith("XBEN")):
        return "xbow"

    for app_dir in benchmarks_dir.iterdir():
        if not app_dir.is_dir():
            continue
        for leaf in app_dir.iterdir():
            if not leaf.is_dir():
                continue
            if (leaf / "docker-compose.yml").exists():
                return "vulhub"

    raise FileNotFoundError(
        f"Could not detect benchmark kind in {benchmarks_dir}. "
        "Expected XBEN-*-24/ folders (xbow) or <app>/<CVE-or-name>/ folders (vulhub)."
    )


_VULNBOT_ROOT_MARKERS = ("cli.py", "pentest.py")


def _find_vulnbot_project_root(start: Path) -> Path | None:
    """Walk up from ``start`` until a directory matches the VulnBot layout.

    A match is a directory whose immediate children include both
    ``cli.py`` and ``pentest.py`` (the project's CLI sentinels). Returns
    the matched directory, or ``None`` if the climb falls off the
    filesystem without finding it.
    """
    seen: set[Path] = set()
    current = start.resolve()
    while True:
        if current in seen:
            return None
        seen.add(current)
        if all((current / m).exists() for m in _VULNBOT_ROOT_MARKERS):
            return current
        if current.parent == current:
            return None
        current = current.parent


def auto_detect_all_benchmarks_dirs(start: Path | None = None) -> list[tuple[Path, str]]:
    """Return every detected ``(path, kind)`` pair under the VulnBot repo.

    Both datasets can coexist in the same checkout — Vulhub at
    ``benchmark/vulhub/selected-benchmark/`` and XBOW at
    ``benchmark/xbow-val-benchmark/selected-benchmarks/``. The search is
    scoped to the enclosing VulnBot project root (detected via the
    presence of ``cli.py`` and ``pentest.py``) so unrelated clones
    elsewhere on the user's machine are never picked up.
    """
    here = (start or Path(__file__).resolve().parent).resolve()
    project_root = _find_vulnbot_project_root(here)

    if project_root is not None:
        bench_root = project_root / "benchmark"
        candidates = [
            bench_root / "vulhub" / "selected-benchmark",
            bench_root / "vulhub" / "selected-benchmarks",
            bench_root / "xbow-val-benchmark" / "selected-benchmarks",
            bench_root / "xbow-val-benchmark" / "selected-benchmark",
        ]
    else:
        candidates = [
            here / "selected-benchmark",
            here / "selected-benchmarks",
            here.parent / "vulhub" / "selected-benchmark",
            here.parent / "xbow-val-benchmark" / "selected-benchmarks",
        ]

    seen: set[Path] = set()
    found: list[tuple[Path, str]] = []
    for c in candidates:
        if not c.exists() or not c.is_dir():
            continue
        resolved = c.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            kind = detect_kind(resolved)
        except FileNotFoundError:
            continue
        found.append((resolved, kind))

    return found


def auto_detect_benchmarks_dir(start: Path | None = None) -> tuple[Path, str]:
    """Return the first detected ``(path, kind)`` pair.

    Raises ``FileNotFoundError`` when nothing is detected. Callers that
    need to handle multiple coexisting datasets should use
    :func:`auto_detect_all_benchmarks_dirs` instead.
    """
    found = auto_detect_all_benchmarks_dirs(start)
    if found:
        return found[0]
    raise FileNotFoundError(
        "Could not auto-detect a benchmark dataset. Pass --benchmarks-dir "
        "pointing at .../selected-benchmark (vulhub) or "
        ".../selected-benchmarks (xbow)."
    )


def load_benchmarks(benchmarks_dir: Path, kind: str) -> dict[str, BenchmarkInfo]:
    """Return a mapping of benchmark id → BenchmarkInfo for the given kind."""
    if kind == "xbow":
        return _load_xbow(benchmarks_dir)
    if kind == "vulhub":
        return _load_vulhub(benchmarks_dir)
    raise ValueError(f"Unknown benchmark kind: {kind!r}")


def _load_xbow(benchmarks_dir: Path) -> dict[str, BenchmarkInfo]:
    out: dict[str, BenchmarkInfo] = {}
    for p in sorted(benchmarks_dir.glob("XBEN-*-24")):
        if not p.is_dir():
            continue
        meta = p / "benchmark.json"
        env = p / ".env"
        if not meta.exists():
            continue
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        flag = _parse_flag_from_env(env) if env.exists() else None
        readme = _read_excerpt(p / "README.md")
        out[p.name] = BenchmarkInfo(
            id=p.name,
            name=data.get("name", p.name),
            kind="xbow",
            path=p,
            description=data.get("description", "") or "",
            tags=list(data.get("tags", []) or []),
            cve=[],
            level=int(data.get("level", 1) or 1),
            expected_flag=flag,
            readme_excerpt=readme,
        )
    return out


def _load_vulhub(benchmarks_dir: Path) -> dict[str, BenchmarkInfo]:
    out: dict[str, BenchmarkInfo] = {}
    toml_meta = _load_environments_toml(benchmarks_dir)

    for app_dir in sorted(benchmarks_dir.iterdir()):
        if not app_dir.is_dir() or app_dir.name.startswith("."):
            continue
        for leaf in sorted(app_dir.iterdir()):
            if not leaf.is_dir():
                continue
            compose = leaf / "docker-compose.yml"
            if not compose.exists():
                continue
            bench_id = f"{app_dir.name}/{leaf.name}"
            readme = ""
            for cand in ("README.md", "README.zh-cn.md", "readme.md"):
                excerpt = _read_excerpt(leaf / cand)
                if excerpt:
                    readme = excerpt
                    break

            toml_entry = toml_meta.get(bench_id, {})
            tags = list(toml_entry.get("tags") or [])
            if not tags:
                tags = _detect_tags(readme)

            cve = list(toml_entry.get("cve") or [])
            cve.extend(_detect_cve(leaf.name))
            cve.extend(_detect_cve(readme))
            cve = sorted({c.upper() for c in cve if c})

            name = toml_entry.get("name") or _first_heading(readme) or bench_id
            level = _difficulty_for_tags(tags)
            out[bench_id] = BenchmarkInfo(
                id=bench_id,
                name=name,
                kind="vulhub",
                path=leaf,
                description=_first_paragraph(readme) or "",
                tags=tags,
                cve=cve,
                level=level,
                expected_flag=None,
                readme_excerpt=readme,
            )
    return out


def _load_environments_toml(benchmarks_dir: Path) -> dict[str, dict]:
    """Read ``environments.toml`` next to the benchmarks dir if present.

    The file ships with the Vulhub repo and lists canonical metadata
    (``name``, ``cve``, ``tags``, ``path``) per environment. Entries are
    keyed by their ``path`` value (e.g. ``activemq/CVE-2016-3088``).
    """
    candidates = [
        benchmarks_dir / "environments.toml",
        benchmarks_dir.parent / "environments.toml",
    ]
    toml_path = next((c for c in candidates if c.exists()), None)
    if toml_path is None:
        return {}

    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return {}

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return {}

    out: dict[str, dict] = {}
    for env in data.get("environment", []) or []:
        path = env.get("path")
        if not path:
            continue
        out[str(path)] = {
            "name": env.get("name"),
            "cve": list(env.get("cve") or []),
            "tags": list(env.get("tags") or []),
            "app": env.get("app"),
        }
    return out


def _parse_flag_from_env(env_file: Path) -> str | None:
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("FLAG="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def _read_excerpt(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[:_README_EXCERPT_LEN]


_HEADING_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
_CVE_RE = re.compile(r"CVE-\d{4}-\d{3,7}", re.IGNORECASE)


def _first_heading(text: str) -> str:
    if not text:
        return ""
    m = _HEADING_RE.search(text)
    return m.group(1).strip() if m else ""


def _first_paragraph(text: str) -> str:
    if not text:
        return ""
    parts = re.split(r"\n\s*\n", text.strip(), maxsplit=2)
    if not parts:
        return ""
    block = parts[0]
    block = re.sub(r"^#+\s.*$", "", block, flags=re.MULTILINE).strip()
    if block:
        return block
    return parts[1] if len(parts) > 1 else ""


def _detect_cve(text: str) -> list[str]:
    if not text:
        return []
    return [m.group(0).upper() for m in _CVE_RE.finditer(text)]


_VULN_TAG_KEYWORDS: dict[str, list[str]] = {
    "RCE": ["remote code execution", "rce", "command injection",
            "command execution", "deserialization rce"],
    "SQL Injection": ["sql injection", "sqli"],
    "SSRF": ["ssrf", "server-side request forgery"],
    "SSTI": ["template injection", "ssti"],
    "Path Traversal": ["path traversal", "directory traversal",
                       "arbitrary file read"],
    "XSS": ["cross-site scripting", "xss"],
    "XXE": ["xml external entity", "xxe"],
    "Privilege Escalation": ["privilege escalation"],
    "File Upload": ["file upload"],
    "Auth Bypass": ["auth bypass", "authentication bypass",
                    "unauthorized access"],
    "Deserialization": ["deserialization"],
    "Info Disclosure": ["info disclosure", "information disclosure"],
}


def _detect_tags(text: str) -> list[str]:
    if not text:
        return []
    low = text.lower()
    tags: list[str] = []
    for tag, kws in _VULN_TAG_KEYWORDS.items():
        if any(kw in low for kw in kws):
            tags.append(tag)
    return tags


_DIFFICULTY: dict[str, int] = {
    "RCE": 5,
    "Deserialization": 4,
    "SQL Injection": 4,
    "SSRF": 4,
    "Privilege Escalation": 4,
    "Auth Bypass": 3,
    "File Upload": 3,
    "SSTI": 3,
    "XXE": 3,
    "Path Traversal": 2,
    "Info Disclosure": 2,
    "XSS": 1,
}


def _difficulty_for_tags(tags: list[str]) -> int:
    if not tags:
        return 1
    return max(_DIFFICULTY.get(t, 1) for t in tags)
