"""Top-level orchestrator for VulnBot benchmark runs.

Mirrors the structure of the PentestGPT runner: load benchmarks, filter by
selection, for each benchmark spin up Docker → run VulnBot → parse output
→ tear down Docker → log result. Supports resume, retries, dry-run and
graceful Ctrl-C.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path

from .benchmark_loader import load_benchmarks
from .docker_manager import DockerManager, ensure_kali_running
from .models import BenchmarkConfig, BenchmarkInfo, BenchmarkResult
from .output_parser import OutputParser
from .reporter import Reporter
from .state_manager import StateManager
from .vulnbot_executor import VulnBotExecutor, _emit


def _section(title: str, width: int = 70) -> None:
    bar = "=" * width
    print(f"\n{bar}", flush=True)
    print(f"  {title}", flush=True)
    print(bar, flush=True)


def _phase(label: str, detail: str = "") -> None:
    suffix = f"  ->  {detail}" if detail else ""
    print(f"\n  +- PHASE: {label}{suffix}", flush=True)


def _phase_done(label: str, elapsed_s: float, status: str = "done") -> None:
    print(f"  +- {label}: {status.upper()} ({elapsed_s:.1f}s)\n", flush=True)


class BenchmarkRunner:
    """Runs a list of benchmark IDs end-to-end against VulnBot."""

    def __init__(
        self,
        config: BenchmarkConfig,
        executor: VulnBotExecutor,
    ):
        self.config = config
        self.executor = executor
        self.docker = DockerManager()
        self.parser = OutputParser()
        self.reporter = Reporter(config.output_dir)
        self.state = StateManager(config.state_file)

        self.interrupted = False
        self.current_benchmark_path: Path | None = None
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        def _handle(signum, frame):
            print("\n\nInterrupt received. Cleaning up…", flush=True)
            self.interrupted = True
            if self.current_benchmark_path:
                try:
                    self.docker.stop_benchmark(self.current_benchmark_path)
                except Exception as e:
                    print(f"warn: stop_benchmark failed: {e!r}", flush=True)
            self.state.save()
            print("State saved. Re-run with --resume to continue.", flush=True)
            sys.exit(130)

        signal.signal(signal.SIGINT, _handle)
        try:
            signal.signal(signal.SIGTERM, _handle)
        except (ValueError, AttributeError):
            pass

    async def run_all(self) -> dict:
        start = datetime.now()
        _section(f"VulnBot Benchmark Runner — {start.strftime('%Y-%m-%d %H:%M:%S')}")
        _emit(f"Benchmarks dir : {self.config.benchmarks_dir}", prefix="  ")
        _emit(f"Kind           : {self.config.kind}", prefix="  ")
        _emit(f"Output dir     : {self.config.output_dir}", prefix="  ")
        _emit(f"Timeout/bench  : {self.config.timeout_seconds}s", prefix="  ")
        _emit(f"Max interactions: {self.config.max_interactions}", prefix="  ")
        _emit(f"Max retries    : {self.config.benchmark_max_retries}", prefix="  ")
        _emit(
            "Flag mode      : "
            f"{'pattern' if self.config.pattern_flag else 'any' if self.config.any_flag else 'exact'}",
            prefix="  ",
        )

        if not self.config.skip_infra_check:
            ok, msg = ensure_kali_running()
            if ok:
                _emit(f"Kali container : {msg}", prefix="  ")
            else:
                _emit(f"Kali container : WARNING — {msg}", prefix="  ")
                _emit(
                    "VulnBot will fail when it tries to SSH into Kali. "
                    "Run `docker compose up -d` from the VulnBot project root.",
                    prefix="  ",
                )

        _phase("Loading benchmarks", str(self.config.benchmarks_dir))
        load_start = datetime.now()
        all_benchmarks = load_benchmarks(self.config.benchmarks_dir, self.config.kind)
        _phase_done(
            "Loading",
            (datetime.now() - load_start).total_seconds(),
            f"found {len(all_benchmarks)}",
        )

        selected: list[BenchmarkInfo] = []
        for bench_id in self.config.benchmark_ids:
            info = all_benchmarks.get(bench_id)
            if info is None:
                _emit(f"Warning: benchmark not found: {bench_id}", prefix="  ")
                continue
            selected.append(info)

        if self.config.resume:
            remaining_ids = self.state.get_remaining([b.id for b in selected])
            selected = [b for b in selected if b.id in remaining_ids]
            _emit(f"Resuming: {len(selected)} benchmarks remaining", prefix="  ")

        total = len(selected)
        if total == 0:
            print("No valid benchmarks to run.", flush=True)
            return {}

        _emit(f"Selected       : {total} benchmarks to run", prefix="  ")

        results: list[BenchmarkResult] = []
        for index, info in enumerate(selected, 1):
            if self.interrupted:
                break

            _section(f"[{index}/{total}] {info.id}  |  {info.name}")
            _emit(f"Kind  : {info.kind}", prefix="  ")
            _emit(f"Tags  : {', '.join(info.tags) or 'none'}", prefix="  ")
            _emit(f"CVE   : {', '.join(info.cve) or 'none'}", prefix="  ")
            _emit(f"Level : {info.level}", prefix="  ")
            _emit(f"Path  : {info.path}", prefix="  ")
            if info.expected_flag:
                _emit(f"Flag  : {info.expected_flag[:24]}… (hidden)", prefix="  ")

            self.reporter.log_start(info.id, index, total)

            result: BenchmarkResult | None = None
            attempts = max(1, self.config.benchmark_max_retries)
            for attempt in range(attempts):
                if attempts > 1:
                    _emit(f"Attempt {attempt + 1}/{attempts}", prefix="  ")
                result = await self.run_single_benchmark(info)
                if result.success:
                    break
                if attempt < attempts - 1:
                    _emit("Attempt failed; retrying…", prefix="  ")

            assert result is not None
            results.append(result)
            self.state.mark_completed(info.id, result.success)
            self.reporter.log_result(result)

        end = datetime.now()
        elapsed = (end - start).total_seconds()

        if results:
            self.reporter.generate_summary(
                results,
                start,
                end,
                benchmarks_dir=str(self.config.benchmarks_dir),
                kind=self.config.kind,
            )

        _section(f"Run complete — {len(results)}/{total} benchmarks — {elapsed:.0f}s total")
        return {"total": total, "completed": len(results)}

    async def run_single_benchmark(self, info: BenchmarkInfo) -> BenchmarkResult:
        start = datetime.now()
        self.current_benchmark_path = info.path

        target_url: str | None = None
        ports: list[int] = []
        try:
            _phase("Docker startup", info.id)
            t0 = datetime.now()
            docker_result = self.docker.start_benchmark(info.path)
            t_elapsed = (datetime.now() - t0).total_seconds()
            if not docker_result["success"]:
                _phase_done("Docker startup", t_elapsed, "FAILED")
                _emit(f"Error: {docker_result['message']}", prefix="  ")
                return self._error_result(
                    info, start, "Docker start failed: " + docker_result["message"],
                    target_url, ports,
                )
            target_url = docker_result.get("target_url")
            ports = docker_result.get("ports") or []
            _phase_done(
                "Docker startup",
                t_elapsed,
                f"OK target={target_url} ports={ports}",
            )

            description = self.executor.build_description(
                bench_id=info.id,
                bench_name=info.name,
                target_url=target_url,
                ports=ports,
                tags=info.tags,
                cve=info.cve,
                readme_excerpt=info.readme_excerpt,
                kind=info.kind,
                expected_flag=info.expected_flag,
            )

            output_file = self.reporter.get_benchmark_log_path(info.id)
            exec_result = await self.executor.execute(
                description=description,
                max_interactions=self.config.max_interactions,
                timeout_seconds=self.config.timeout_seconds,
                output_file=output_file,
                save_name=f"bench_{info.id.replace('/', '_')}_{int(start.timestamp())}",
                no_save=True,
            )

            _phase("Output parsing & flag evaluation")
            t0 = datetime.now()
            parsed = self.parser.parse_output(
                exec_result["output_lines"],
                extra_keywords=self.config.success_keywords,
            )

            found_flags = parsed["flags"]
            correct_flag = False
            if info.expected_flag:
                expected_lower = info.expected_flag.lower()
                correct_flag = expected_lower in [f.lower() for f in found_flags]

            if self.config.pattern_flag:
                strict_flags = self.parser.filter_strict_flags(found_flags)
                correct_flag = len(strict_flags) > 0
                _emit(f"Pattern-flag mode: strict={strict_flags}", prefix="    ")
            elif self.config.any_flag:
                correct_flag = len(found_flags) > 0
                _emit(f"Any-flag mode: count={len(found_flags)}", prefix="    ")

            _emit(f"Found flags    : {found_flags}", prefix="    ")
            _emit(f"Expected flag  : {info.expected_flag or '(vulhub: none)'}", prefix="    ")
            _emit(f"Keyword hits   : {parsed['keyword_hits']}", prefix="    ")
            _emit(f"Has done marker: {parsed['has_done']}", prefix="    ")
            _emit(f"Has error      : {parsed['has_error']} ({parsed['error_msg'] or ''})", prefix="    ")

            timed_out = exec_result["timed_out"]
            has_error = parsed["has_error"]

            if timed_out:
                status = "TIMEOUT"
                success = False
            elif has_error and not correct_flag and not parsed["keyword_hits"]:
                status = "ERROR"
                success = False
            elif correct_flag:
                status = "SUCCESS"
                success = True
            elif (not info.expected_flag
                  and (parsed["keyword_hits"] or self.config.any_flag and found_flags)
                  and parsed["has_done"]):
                status = "SUCCESS"
                success = True
            else:
                status = "FAILURE"
                success = False

            _phase_done("Output parsing", (datetime.now() - t0).total_seconds(), status)

            return BenchmarkResult(
                benchmark_id=info.id,
                benchmark_name=info.name,
                kind=info.kind,
                tags=info.tags,
                cve=info.cve,
                level=info.level,
                status=status,
                success=success,
                expected_flag=info.expected_flag,
                found_flags=found_flags,
                correct_flag=correct_flag,
                duration_seconds=(datetime.now() - start).total_seconds(),
                session_id=parsed.get("session_id", ""),
                target_url=target_url or "",
                target_ports=ports,
                error_message=parsed.get("error_msg"),
                timeout_occurred=timed_out,
                start_time=start,
                end_time=datetime.now(),
                output_log_path=str(output_file),
            )

        except Exception as e:
            import traceback
            _emit(f"Unexpected error in benchmark {info.id}: {e!r}", prefix="  ")
            traceback.print_exc()
            return self._error_result(
                info, start, f"Unexpected error: {e!r}", target_url, ports,
            )
        finally:
            _phase("Docker cleanup", info.id)
            t0 = datetime.now()
            try:
                self.docker.stop_benchmark(info.path)
                _phase_done("Docker cleanup", (datetime.now() - t0).total_seconds())
            except Exception as e:
                _emit(f"warn: stop_benchmark failed: {e!r}", prefix="  ")
            finally:
                self.current_benchmark_path = None

    def _error_result(
        self,
        info: BenchmarkInfo,
        start: datetime,
        message: str,
        target_url: str | None,
        ports: list[int],
    ) -> BenchmarkResult:
        return BenchmarkResult(
            benchmark_id=info.id,
            benchmark_name=info.name,
            kind=info.kind,
            tags=info.tags,
            cve=info.cve,
            level=info.level,
            status="ERROR",
            success=False,
            expected_flag=info.expected_flag,
            found_flags=[],
            correct_flag=False,
            duration_seconds=(datetime.now() - start).total_seconds(),
            session_id="",
            target_url=target_url or "",
            target_ports=ports,
            error_message=message,
            timeout_occurred=False,
            start_time=start,
            end_time=datetime.now(),
            output_log_path=str(self.reporter.get_benchmark_log_path(info.id)),
        )
