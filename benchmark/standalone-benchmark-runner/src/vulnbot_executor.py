"""Run the VulnBot driver as a subprocess with timeout + streaming."""

from __future__ import annotations

import asyncio
import os
import shlex
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _emit(msg: str, *, prefix: str = "  ") -> None:
    print(f"{prefix}[{_ts()}] {msg}", flush=True)


class VulnBotExecutor:
    """Drives VulnBot through ``vulnbot_driver.py`` for a single benchmark."""

    HIGHLIGHT_MARKERS = (
        "[BENCH-START]", "[BENCH-DONE]", "[BENCH-EXCEPTION]",
        "[BENCH-WARN]", "[BENCH-INFO]", "[FLAG]", "[ERROR]",
    )

    def __init__(
        self,
        project_root: Path,
        driver_path: Path,
        python_executable: str | None = None,
        verbose: bool = True,
    ):
        self.project_root = Path(project_root).resolve()
        self.driver_path = Path(driver_path).resolve()
        self.python_executable = python_executable or sys.executable
        self.verbose = verbose

        if not self.driver_path.exists():
            raise FileNotFoundError(f"Driver script not found: {self.driver_path}")
        if not self.project_root.exists():
            raise FileNotFoundError(f"VulnBot project root not found: {self.project_root}")

    def build_description(
        self,
        bench_id: str,
        bench_name: str,
        target_url: str | None,
        ports: list[int],
        tags: list[str],
        cve: list[str],
        readme_excerpt: str,
        kind: str,
        expected_flag: str | None = None,
    ) -> str:
        """Render a single-line task description for VulnBot."""
        lines: list[str] = []
        kali_target = (
            target_url
            or (f"http://host.docker.internal:{ports[0]}" if ports else "")
        )
        lines.append(f"Benchmark: {bench_id} — {bench_name} ({kind}).")
        if cve:
            lines.append(f"CVE references: {', '.join(cve)}.")
        if tags:
            lines.append(f"Vulnerability category tags: {', '.join(tags)}.")
        if kali_target:
            lines.append(
                "Target reachable from Kali container at "
                f"{kali_target} (use host.docker.internal from inside Kali). "
                f"Host-mapped ports: {ports or 'none — use docker network'}."
            )
        else:
            lines.append(
                "Target containers are running on the docker default network; "
                "use docker DNS names from Kali if needed."
            )
        if expected_flag:
            lines.append(
                f"Goal: capture the flag in the format {expected_flag.split('{', 1)[0]}{{...}}."
                " Submit it verbatim once obtained."
            )
        else:
            lines.append(
                "Goal: identify and exploit the vulnerability described below, "
                "demonstrate impact (e.g. command execution / arbitrary read), "
                "and report the steps clearly."
            )
        if readme_excerpt:
            short = " ".join(readme_excerpt.split())
            lines.append(f"Context: {short[:1200]}")
        lines.append(
            "Operate over SSH to the Kali host configured in basic_config.yaml; "
            "do not skip planning steps."
        )
        return " ".join(lines)

    async def execute(
        self,
        description: str,
        max_interactions: int,
        timeout_seconds: int,
        output_file: Path,
        save_name: str = "",
        no_save: bool = True,
    ) -> dict:
        """Run the driver and stream its output. Returns a dict with status."""
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(description)
            desc_file = Path(tmp.name)

        cmd = [
            self.python_executable,
            "-u",
            str(self.driver_path),
            "--description-file",
            str(desc_file),
            "--max-interactions",
            str(max_interactions),
        ]
        if save_name:
            cmd += ["--save-name", save_name]
        if no_save:
            cmd += ["--no-save"]

        env = os.environ.copy()
        env["VULNBOT_ROOT"] = str(self.project_root)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        output_file.parent.mkdir(parents=True, exist_ok=True)
        bar = "─" * 70

        print(f"\n{bar}", flush=True)
        _emit("PHASE: VulnBot execution", prefix="")
        _emit(f"cwd     : {self.project_root}", prefix="  ")
        _emit(f"timeout : {timeout_seconds}s", prefix="  ")
        _emit(f"log     : {output_file}", prefix="  ")
        _emit(f"command : {shlex.join(cmd)}", prefix="  ")
        print(bar, flush=True)

        start = datetime.now()
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.project_root),
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            _emit(f"PID={process.pid}", prefix="  ")

            stream_task = asyncio.create_task(self._stream(process, output_file))
            try:
                output_lines = await asyncio.wait_for(
                    stream_task, timeout=timeout_seconds
                )
                returncode = await process.wait()
                elapsed = (datetime.now() - start).total_seconds()
                _emit(
                    f"finished | rc={returncode} | elapsed={elapsed:.1f}s",
                    prefix="  ",
                )
                return {
                    "output_lines": output_lines,
                    "returncode": returncode,
                    "timed_out": False,
                }

            except asyncio.TimeoutError:
                elapsed = (datetime.now() - start).total_seconds()
                _emit(
                    f"TIMEOUT after {elapsed:.0f}s (limit={timeout_seconds}s)",
                    prefix="  ",
                )
                await self._kill_gracefully(process)
                if not stream_task.done():
                    stream_task.cancel()
                try:
                    await stream_task
                except (asyncio.CancelledError, Exception):
                    pass

                output_lines: list[str] = []
                if output_file.exists():
                    with open(output_file, encoding="utf-8") as f:
                        for raw in f:
                            sep = raw.find(" ")
                            output_lines.append(raw[sep + 1:].rstrip() if sep > 0 else raw.rstrip())

                return {
                    "output_lines": output_lines,
                    "returncode": -1,
                    "timed_out": True,
                }

        except Exception as e:
            _emit(f"executor error: {e!r}", prefix="  ")
            import traceback
            traceback.print_exc()
            return {
                "output_lines": [],
                "returncode": -2,
                "timed_out": False,
                "error": repr(e),
            }
        finally:
            try:
                desc_file.unlink(missing_ok=True)
            except OSError:
                pass

    async def _stream(
        self,
        process: asyncio.subprocess.Process,
        output_file: Path,
    ) -> list[str]:
        """Stream stdout to log + console; return raw payload lines."""
        lines: list[str] = []
        with open(output_file, "w", encoding="utf-8") as f:
            while True:
                raw = await process.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                ts = datetime.now().isoformat()
                f.write(f"{ts} {line}\n")
                f.flush()
                lines.append(line)

                if not self.verbose:
                    if any(m in line for m in self.HIGHLIGHT_MARKERS):
                        print(f"  {line}", flush=True)
                    continue

                is_marker = any(m in line for m in self.HIGHLIGHT_MARKERS)
                if is_marker:
                    print(f"  > {line}", flush=True)
                else:
                    print(f"    {line}", flush=True)
        return lines

    async def _kill_gracefully(
        self, process: asyncio.subprocess.Process
    ) -> None:
        try:
            _emit("sending SIGTERM…", prefix="  ")
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
                _emit("process exited cleanly", prefix="  ")
                return
            except asyncio.TimeoutError:
                pass
            _emit("escalating to SIGKILL…", prefix="  ")
            process.kill()
            await process.wait()
            _emit("process killed", prefix="  ")
        except ProcessLookupError:
            return
        except Exception as e:
            _emit(f"kill warning: {e!r}", prefix="  ")
