"""Data models for the VulnBot benchmark runner.

Two benchmark "kinds" are supported and auto-detected:

* ``xbow``  — XBOW validation suite. Each benchmark folder is named
  ``XBEN-XXX-24/`` and ships a ``benchmark.json``, a ``.env`` containing
  ``FLAG=...`` and a ``docker-compose.yml`` with ephemeral ports.
* ``vulhub`` — Vulhub vulnerability environments. Each leaf folder is
  ``<app>/<CVE-or-tag>/`` and ships a ``docker-compose.yml`` plus a
  ``README.md``. There is no flag — success is decided by heuristics and
  configurable matchers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class BenchmarkConfig:
    """Configuration for a single VulnBot benchmark run."""

    benchmark_ids: list[str]
    kind: str = "auto"
    benchmarks_dir: Path = field(default_factory=lambda: Path("."))
    timeout_seconds: int = 1800

    max_interactions: int = 10
    benchmark_max_retries: int = 1

    resume: bool = False
    output_dir: Path = field(default_factory=lambda: Path("./logs"))
    state_file: Path | None = None

    any_flag: bool = False
    pattern_flag: bool = False
    success_keywords: list[str] = field(default_factory=list)

    project_root: Path | None = None
    python_executable: str = ""

    skip_infra_check: bool = False

    def __post_init__(self) -> None:
        if self.state_file is None:
            self.state_file = self.output_dir / "state.json"


@dataclass
class BenchmarkInfo:
    """Static metadata about a single benchmark on disk."""

    id: str
    name: str
    kind: str
    path: Path
    description: str = ""
    tags: list[str] = field(default_factory=list)
    cve: list[str] = field(default_factory=list)
    level: int = 0
    expected_flag: str | None = None
    readme_excerpt: str = ""

    @property
    def has_expected_flag(self) -> bool:
        return bool(self.expected_flag)


@dataclass
class BenchmarkResult:
    """Result from executing a single benchmark."""

    benchmark_id: str
    benchmark_name: str
    kind: str
    tags: list[str]
    cve: list[str]
    level: int

    status: str
    success: bool

    expected_flag: str | None
    found_flags: list[str]
    correct_flag: bool

    duration_seconds: float
    session_id: str
    target_url: str
    target_ports: list[int]

    error_message: str | None
    timeout_occurred: bool

    start_time: datetime
    end_time: datetime

    output_log_path: str = ""

    def to_dict(self) -> dict:
        return {
            "benchmark_id": self.benchmark_id,
            "benchmark_name": self.benchmark_name,
            "kind": self.kind,
            "tags": self.tags,
            "cve": self.cve,
            "level": self.level,
            "status": self.status,
            "success": self.success,
            "expected_flag": self.expected_flag,
            "found_flags": self.found_flags,
            "correct_flag": self.correct_flag,
            "duration_seconds": self.duration_seconds,
            "session_id": self.session_id,
            "target_url": self.target_url,
            "target_ports": self.target_ports,
            "error_message": self.error_message,
            "timeout_occurred": self.timeout_occurred,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "output_log_path": self.output_log_path,
        }


@dataclass
class BenchmarkSummary:
    """Aggregate run-level summary."""

    total_benchmarks: int
    successful: int
    failed: int
    timeout: int
    error: int

    total_duration_seconds: float
    average_duration_seconds: float
    success_rate: float
    results: list[BenchmarkResult]

    start_time: datetime
    end_time: datetime

    benchmarks_dir: str = ""
    kind: str = ""

    def to_dict(self) -> dict:
        return {
            "total_benchmarks": self.total_benchmarks,
            "successful": self.successful,
            "failed": self.failed,
            "timeout": self.timeout,
            "error": self.error,
            "total_duration_seconds": self.total_duration_seconds,
            "average_duration_seconds": self.average_duration_seconds,
            "success_rate": self.success_rate,
            "benchmarks_dir": self.benchmarks_dir,
            "kind": self.kind,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "results": [r.to_dict() for r in self.results],
        }
