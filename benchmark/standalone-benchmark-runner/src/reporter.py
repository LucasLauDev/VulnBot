"""Reporter — per-benchmark log paths, aggregate JSON / text summaries."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import BenchmarkResult, BenchmarkSummary


def _safe_id(benchmark_id: str) -> str:
    return benchmark_id.replace("/", "__").replace("\\", "__")


class Reporter:
    """Writes per-run logs and summaries under ``output_dir/benchmark_run_*/``."""

    def __init__(self, output_dir: Path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = output_dir / f"benchmark_run_{timestamp}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.benchmarks_dir = self.run_dir / "benchmarks"
        self.benchmarks_dir.mkdir(exist_ok=True)
        self.detailed_log = self.run_dir / "detailed.log"
        self.summary_txt = self.run_dir / "summary.txt"
        self.summary_json = self.run_dir / "summary.json"
        print(f"\nLogs directory: {self.run_dir}\n", flush=True)

    def get_benchmark_log_path(self, benchmark_id: str) -> Path:
        return self.benchmarks_dir / f"{_safe_id(benchmark_id)}.log"

    def log_start(self, benchmark_id: str, index: int, total: int) -> None:
        ts = datetime.now().isoformat()
        with open(self.detailed_log, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] START {benchmark_id}\n")
        print(f"\n[{index}/{total}] {benchmark_id}", flush=True)

    def log_result(self, result: BenchmarkResult) -> None:
        ts = datetime.now().isoformat()
        m = int(result.duration_seconds // 60)
        s = int(result.duration_seconds % 60)
        msg = (
            f"[{ts}] COMPLETE {result.benchmark_id} "
            f"({result.status}, {m}m {s}s)"
        )
        with open(self.detailed_log, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

        icon = "OK " if result.success else (
            "TO " if result.timeout_occurred else (
                "ERR" if result.status == "ERROR" else "FAIL"
            )
        )
        line = f"  [{icon}] {result.status} ({m}m {s}s)"
        if result.error_message:
            line += f"\n        error: {result.error_message[:160]}"
        print(line, flush=True)

    def generate_summary(
        self,
        results: list[BenchmarkResult],
        start_time: datetime,
        end_time: datetime,
        benchmarks_dir: str = "",
        kind: str = "",
    ) -> BenchmarkSummary:
        total = len(results)
        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if (not r.success) and r.status == "FAILURE")
        timeout = sum(1 for r in results if r.timeout_occurred)
        error = sum(1 for r in results if r.status == "ERROR")

        total_dur = sum(r.duration_seconds for r in results)
        avg_dur = total_dur / total if total else 0.0
        success_rate = (successful / total * 100) if total else 0.0

        summary = BenchmarkSummary(
            total_benchmarks=total,
            successful=successful,
            failed=failed,
            timeout=timeout,
            error=error,
            total_duration_seconds=total_dur,
            average_duration_seconds=avg_dur,
            success_rate=success_rate,
            results=results,
            start_time=start_time,
            end_time=end_time,
            benchmarks_dir=benchmarks_dir,
            kind=kind,
        )

        with open(self.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary.to_dict(), f, indent=2)
        self._write_text_summary(summary)
        self._print_console_summary(summary)
        return summary

    def _write_text_summary(self, s: BenchmarkSummary) -> None:
        lines: list[str] = []
        bar = "=" * 70
        lines.append(bar)
        lines.append("VulnBot Benchmark Results")
        lines.append(bar)
        lines.append(f"Run Date: {s.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Kind:     {s.kind}")
        lines.append(f"Path:     {s.benchmarks_dir}")
        h = int(s.total_duration_seconds // 3600)
        m = int((s.total_duration_seconds % 3600) // 60)
        lines.append(f"Duration: {h}h {m}m")
        lines.append("")
        lines.append(f"Total Benchmarks : {s.total_benchmarks}")
        lines.append(f"Successful       : {s.successful} ({s.success_rate:.1f}%)")
        lines.append(f"Failed           : {s.failed}")
        lines.append(f"Timeout          : {s.timeout}")
        lines.append(f"Errors           : {s.error}")
        lines.append("")

        groups = [
            ("Success", [r for r in s.results if r.success]),
            ("Failures", [r for r in s.results
                          if (not r.success) and r.status == "FAILURE"]),
            ("Timeouts", [r for r in s.results if r.timeout_occurred]),
            ("Errors", [r for r in s.results if r.status == "ERROR"]),
        ]
        for title, rs in groups:
            if not rs:
                continue
            lines.append(f"{title}:")
            for r in rs:
                m = int(r.duration_seconds // 60)
                sec = int(r.duration_seconds % 60)
                lines.append(
                    f"  - {r.benchmark_id}  ({m}m {sec}s)"
                    + (f"  flags={r.found_flags}" if r.found_flags else "")
                )
            lines.append("")
        lines.append(bar)
        self.summary_txt.write_text("\n".join(lines), encoding="utf-8")

    def _print_console_summary(self, s: BenchmarkSummary) -> None:
        bar = "=" * 70
        print("", flush=True)
        print(bar, flush=True)
        print("VulnBot Benchmark Run Complete", flush=True)
        print(bar, flush=True)
        print(f"  Total       : {s.total_benchmarks}", flush=True)
        print(f"  Successful  : {s.successful} ({s.success_rate:.1f}%)", flush=True)
        print(f"  Failed      : {s.failed}", flush=True)
        print(f"  Timeout     : {s.timeout}", flush=True)
        print(f"  Errors      : {s.error}", flush=True)
        h = s.total_duration_seconds / 3600
        print(f"  Total Time  : {h:.2f}h", flush=True)
        print(f"\n  Detailed results: {self.run_dir}", flush=True)
        print(bar, flush=True)
