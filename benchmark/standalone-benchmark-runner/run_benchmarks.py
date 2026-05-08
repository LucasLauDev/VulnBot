#!/usr/bin/env python3
"""Run VulnBot against the Vulhub or XBOW benchmark sets.

Usage examples
--------------

    # Auto-detect the benchmark set under ../vulhub/selected-benchmark or
    # ../xbow-val-benchmark/selected-benchmarks and list every entry.
    python run_benchmarks.py --list

    # Run a couple of vulhub benchmarks (IDs are <app>/<CVE-or-name>):
    python run_benchmarks.py --ids 1panel/CVE-2024-39907,bash/CVE-2014-6271

    # Run XBOW benchmarks 1..10 (requires the XBOW dataset on disk):
    python run_benchmarks.py --benchmarks-dir ../xbow-val-benchmark/selected-benchmarks --range 1-10 --pattern-flag

    # Resume the previous interrupted run:
    python run_benchmarks.py --all --resume

    # Dry run (no Docker, no VulnBot — just preview the selection):
    python run_benchmarks.py --all --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from src.benchmark_loader import (  # noqa: E402  (sys.path tweak above)
    auto_detect_all_benchmarks_dirs,
    auto_detect_benchmarks_dir,
    detect_kind,
    load_benchmarks,
)
from src.benchmark_runner import BenchmarkRunner  # noqa: E402
from src.models import BenchmarkConfig  # noqa: E402
from src.vulnbot_executor import VulnBotExecutor  # noqa: E402


DRIVER_PATH = HERE / "vulnbot_driver.py"
PROJECT_ROOT = HERE.parents[1]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run VulnBot against benchmark suites (Vulhub / XBOW).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--range", type=str,
                     help="1-based index range over the sorted benchmark list, e.g. '1-10'.")
    sel.add_argument("--ids", type=str,
                     help="Comma-separated benchmark IDs "
                          "(vulhub: '<app>/<cve>'; xbow: 'XBEN-001-24').")
    sel.add_argument("--all", action="store_true",
                     help="Run every benchmark detected under --benchmarks-dir.")
    sel.add_argument("--retry-failed", nargs="?", const="", metavar="PATH",
                     help="Retry failed benchmarks from the most recent run "
                          "(or specify a run directory).")

    p.add_argument("--list", action="store_true",
                   help="Print every benchmark ID and exit.")

    p.add_argument("--benchmarks-dir", type=Path, default=None,
                   help="Path to .../selected-benchmark (vulhub) or "
                        ".../selected-benchmarks (xbow). Auto-detected if omitted.")
    p.add_argument("--kind", choices=("auto", "vulhub", "xbow"), default="auto",
                   help="Force benchmark kind. Default: auto-detect from the directory.")

    p.add_argument("--timeout", type=int, default=1800,
                   help="Timeout per benchmark in seconds (default: 1800).")
    p.add_argument("--max-interactions", type=int, default=10,
                   help="Max VulnBot react iterations per role (default: 10).")
    p.add_argument("--retries", type=int, default=1,
                   help="Re-run a failing benchmark up to this many attempts (default: 1).")

    p.add_argument("--resume", action="store_true",
                   help="Skip benchmarks already marked successful in state.json.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the planned execution without invoking Docker / VulnBot.")
    p.add_argument("--output-dir", type=Path, default=Path("./logs"),
                   help="Directory for run logs and summaries (default: ./logs).")
    p.add_argument("--skip-infra-check", action="store_true",
                   help="Skip the kali-ssh container presence check.")
    p.add_argument("--python", type=str, default=sys.executable,
                   help="Python interpreter used to run vulnbot_driver.py "
                        "(default: current interpreter).")

    flag_mode = p.add_mutually_exclusive_group()
    flag_mode.add_argument("--any-flag", action="store_true",
                           help="Mark a run successful if ANY flag-shaped string is found.")
    flag_mode.add_argument("--pattern-flag", action="store_true",
                           help="Mark a run successful if a flag matches FLAG{32+ alnum/dash}.")

    p.add_argument("--success-keyword", action="append", default=[],
                   metavar="WORD",
                   help="Extra keyword counted as exploit evidence (vulhub mode). "
                        "May be passed multiple times.")

    return p.parse_args()


def parse_index_range(range_str: str, n_available: int) -> list[int]:
    parts = range_str.replace("-", " ").split()
    if len(parts) != 2:
        raise ValueError(f"Invalid range (use e.g. 1-10): {range_str!r}")
    start, end = int(parts[0]), int(parts[1])
    if start < 1 or end < start or end > n_available:
        raise ValueError(f"Range must satisfy 1 <= start <= end <= {n_available}")
    return list(range(start - 1, end))


def find_last_run(output_dir: Path) -> Path:
    if not output_dir.exists():
        raise FileNotFoundError(f"Output directory not found: {output_dir}")
    runs = sorted(output_dir.glob("benchmark_run_*"))
    if not runs:
        raise FileNotFoundError(f"No previous benchmark runs in {output_dir}")
    return runs[-1]


def load_failed_benchmarks(run_dir: Path) -> list[dict]:
    summary_file = run_dir / "summary.json"
    if not summary_file.exists():
        raise FileNotFoundError(f"summary.json not found in {run_dir}")
    data = json.loads(summary_file.read_text(encoding="utf-8"))
    return [r for r in data.get("results", []) if not r.get("success")]


def _do_list(datasets: list[tuple[Path, str]]) -> int:
    """Print every benchmark in every detected dataset and return 0.

    When more than one dataset is present (the common case in this repo —
    Vulhub + XBOW side by side), each one is printed under its own
    header so the user can see the full inventory at a glance.
    """
    grand_total = 0
    for index, (benchmarks_dir, kind) in enumerate(datasets, 1):
        try:
            all_benchmarks = load_benchmarks(benchmarks_dir, kind)
        except (FileNotFoundError, ValueError) as e:
            print(f"[{index}] Error loading {benchmarks_dir}: {e}", file=sys.stderr)
            continue

        sorted_ids = sorted(all_benchmarks.keys())
        if index > 1:
            print()
        print(f"[{index}/{len(datasets)}] Benchmarks dir : {benchmarks_dir}")
        print(f"      Kind            : {kind}")
        print(f"      Total           : {len(sorted_ids)}")
        for bid in sorted_ids:
            info = all_benchmarks[bid]
            tags = ",".join(info.tags) if info.tags else "-"
            cve = ",".join(info.cve) if info.cve else "-"
            print(f"        {bid:<40} [{kind}] tags={tags} cve={cve}")
        grand_total += len(sorted_ids)

    if len(datasets) > 1:
        print()
        print(f"Grand total across {len(datasets)} datasets: {grand_total} benchmarks")
    return 0


def _resolve_target_datasets(
    args: argparse.Namespace,
) -> list[tuple[Path, str]]:
    """Resolve which dataset directories the current invocation targets.

    Returns one ``(path, kind)`` pair when ``--benchmarks-dir`` is given.
    Otherwise returns every dataset auto-detected on disk (so ``--list``
    can show both Vulhub and XBOW). Filters by ``--kind`` if the user
    specified one. Raises ``FileNotFoundError`` if nothing is found.
    """
    if args.benchmarks_dir is not None:
        path = args.benchmarks_dir.resolve()
        kind = args.kind if args.kind != "auto" else detect_kind(path)
        return [(path, kind)]

    found = auto_detect_all_benchmarks_dirs()
    if not found:
        raise FileNotFoundError(
            "Could not auto-detect a benchmark dataset. Pass --benchmarks-dir "
            "pointing at .../selected-benchmark (vulhub) or "
            ".../selected-benchmarks (xbow)."
        )

    if args.kind != "auto":
        filtered = [(p, k) for (p, k) in found if k == args.kind]
        if not filtered:
            raise FileNotFoundError(
                f"No detected dataset matches --kind {args.kind}. "
                f"Found: {[k for _, k in found]}"
            )
        return filtered

    return found


async def main_async() -> int:
    args = parse_args()

    try:
        datasets = _resolve_target_datasets(args)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.list:
        return _do_list(datasets)

    if len(datasets) > 1:
        kinds = ", ".join(f"{k} -> {p}" for p, k in datasets)
        print(
            "Error: multiple benchmark datasets detected ("
            f"{kinds}). Pass --benchmarks-dir or --kind {{vulhub,xbow}} "
            "to choose one before running.",
            file=sys.stderr,
        )
        return 2

    benchmarks_dir, kind = datasets[0]
    try:
        all_benchmarks = load_benchmarks(benchmarks_dir, kind)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not all_benchmarks:
        print(f"No benchmarks found under {benchmarks_dir} (kind={kind})", file=sys.stderr)
        return 1

    sorted_ids = sorted(all_benchmarks.keys())

    selection_count = sum([
        bool(args.range),
        bool(args.ids),
        bool(args.all),
        args.retry_failed is not None,
    ])
    if selection_count != 1:
        print("Error: choose exactly one of --range / --ids / --all / --retry-failed "
              "(or pass --list).", file=sys.stderr)
        return 2

    selected_ids: list[str] = []
    retry_info: dict | None = None

    try:
        if args.all:
            selected_ids = sorted_ids
        elif args.ids:
            for raw in args.ids.split(","):
                bid = raw.strip()
                if not bid:
                    continue
                if bid in all_benchmarks:
                    selected_ids.append(bid)
                else:
                    print(f"Warning: id not found, skipping: {bid}", flush=True)
        elif args.range:
            indices = parse_index_range(args.range, len(sorted_ids))
            selected_ids = [sorted_ids[i] for i in indices]
        elif args.retry_failed is not None:
            run_dir = (
                find_last_run(args.output_dir)
                if args.retry_failed == ""
                else Path(args.retry_failed).resolve()
            )
            if not run_dir.exists():
                print(f"Error: run directory not found: {run_dir}", file=sys.stderr)
                return 1
            failed = load_failed_benchmarks(run_dir)
            if not failed:
                print(f"No failed benchmarks in {run_dir}. Nothing to retry.")
                return 0
            failed_ids = sorted({str(r["benchmark_id"]) for r in failed})
            selected_ids = [bid for bid in failed_ids if bid in all_benchmarks]
            retry_info = {"run_dir": run_dir, "failed": failed}
            print(f"Retrying {len(selected_ids)} failed benchmark(s) from {run_dir.name}.")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error: failed to parse summary.json: {e}", file=sys.stderr)
        return 1

    if not selected_ids:
        print("Error: empty selection.", file=sys.stderr)
        return 2

    config = BenchmarkConfig(
        benchmark_ids=selected_ids,
        kind=kind,
        benchmarks_dir=benchmarks_dir,
        timeout_seconds=args.timeout,
        max_interactions=args.max_interactions,
        benchmark_max_retries=args.retries,
        resume=args.resume,
        output_dir=args.output_dir.resolve(),
        any_flag=args.any_flag,
        pattern_flag=args.pattern_flag,
        success_keywords=list(args.success_keyword or []),
        project_root=PROJECT_ROOT,
        python_executable=args.python,
        skip_infra_check=args.skip_infra_check,
    )

    if args.dry_run:
        bar = "=" * 70
        print(bar)
        print("DRY RUN — VulnBot benchmark runner")
        print(bar)
        print(f"Benchmarks dir   : {benchmarks_dir}")
        print(f"Kind             : {kind}")
        print(f"Total available  : {len(sorted_ids)}")
        print(f"Selected         : {len(selected_ids)}")
        for bid in selected_ids[:25]:
            info = all_benchmarks[bid]
            print(f"  - {bid:<40} tags={info.tags} cve={info.cve}")
        if len(selected_ids) > 25:
            print(f"  ... and {len(selected_ids) - 25} more")
        print(f"Timeout/bench    : {args.timeout}s")
        print(f"Max interactions : {args.max_interactions}")
        print(f"Retries/bench    : {args.retries}")
        print(f"Resume           : {args.resume}")
        print(f"Output dir       : {config.output_dir}")
        print(
            "Flag mode        : "
            f"{'pattern' if args.pattern_flag else 'any' if args.any_flag else 'exact'}"
        )
        if retry_info:
            print(f"Retry source     : {retry_info['run_dir']}")
        print(bar)
        return 0

    try:
        executor = VulnBotExecutor(
            project_root=PROJECT_ROOT,
            driver_path=DRIVER_PATH,
            python_executable=config.python_executable,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    runner = BenchmarkRunner(config, executor)
    try:
        await runner.run_all()
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user", flush=True)
        return 130
    except Exception as e:
        import traceback
        print(f"\nFatal error: {e!r}", flush=True)
        traceback.print_exc()
        return 1


def main() -> None:
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
