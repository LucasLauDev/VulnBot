"""
run_functionality_tests.py - Reproducible test harness for the VulnBot
functionality & reliability study.

For every challenge in `functionality_test_dataset.csv` it executes the exact
protocol from the research design:

    1. Reset the XBOW Docker container  (down -v, rebuild with fixed flag, up --wait)
    2. Verify the target is reachable    (HTTP probe with retries)
    3. Start a fresh VulnBot session     (separate process)
    4. Assign a Run ID
    5. Give VulnBot the target information ONLY (no vulnerability hints)
    6. Let VulnBot run to completion / its interaction budget
    7. Save logs                         (per-run .log + raw .json + VulnBot log copy)
    8. Score functionality               (metrics.py)
    9. Append the row to functionality_results.csv

After all runs it aggregates the headline metrics and writes results_summary.csv.

This harness is intentionally model-agnostic: it never inspects WHETHER a flag
was captured. It only measures whether the *workflow* behaves correctly.

Prerequisites (see README.md):
    * Docker + docker compose, with the xbow-engineering/validation-benchmarks
      repository cloned locally (pass its path with --benchmarks-dir).
    * A configured, initialised VulnBot stack (`python cli.py init`, MySQL up,
      a reachable Kali SSH box, and model_config.yaml filled in).

Example:
    python test-cases/run_functionality_tests.py \
        --benchmarks-dir /path/to/validation-benchmarks \
        --vulnbot-target-host host.docker.internal \
        --max-interactions 5 --repeat 1
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import metrics  # noqa: E402

DATASET = os.path.join(HERE, "functionality_test_dataset.csv")
RESULTS_CSV = os.path.join(HERE, "functionality_results.csv")
SUMMARY_CSV = os.path.join(HERE, "results_summary.csv")
CATEGORY_CSV = os.path.join(HERE, "results_by_category.csv")
LOG_DIR = os.path.join(HERE, "logs")
RAW_DIR = os.path.join(HERE, "raw")

RESULT_COLUMNS = [
    "run_id", "timestamp", "challenge_id", "category", "difficulty",
    "target_host", "target_port",
    "startup_ok", "target_reachable_pre", "session_completed", "num_phases_executed",
    "SSR_i", "TRR_i", "SCR_i", "PQS_i", "EES_i", "MRS_i", "HIC_i",
    "commands_generated", "commands_executed", "commands_valid",
    "commands_relevant", "commands_evidence", "errors", "errors_recovered",
    "OFS_run", "fatal_error", "log_file", "raw_file",
]


# ---------------------------------------------------------------------------
# Docker / XBOW helpers
# ---------------------------------------------------------------------------
def xbow_flag(challenge_id: str) -> str:
    """Reproduce the XBOW Makefile flag:  FLAG{ sha256(UPPER(benchmark_id)) }."""
    digest = hashlib.sha256(challenge_id.upper().encode()).hexdigest()
    return f"FLAG{{{digest}}}"


def run_cmd(cmd, cwd=None, timeout=900):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def reset_container(bench_dir: str, challenge_id: str, log) -> bool:
    """Step 1: fully reset the benchmark container to a clean state."""
    flag = xbow_flag(challenge_id)
    log(f"  flag (fixed) = {flag}")
    # Tear down anything left over (ignore errors).
    run_cmd(["docker", "compose", "down", "-v", "--remove-orphans"], cwd=bench_dir)
    # Build with the fixed flag injected both ways the benchmarks expect.
    b = run_cmd(["docker", "compose", "build",
                 "--build-arg", f"FLAG={flag}", "--build-arg", f"flag={flag}"],
                cwd=bench_dir)
    if b.returncode != 0:
        log(f"  ! build failed: {b.stderr[-500:]}")
        return False
    # Start and wait until healthy.
    u = run_cmd(["docker", "compose", "up", "-d", "--wait"], cwd=bench_dir, timeout=600)
    if u.returncode != 0:
        # --wait can fail on benchmarks without healthchecks; fall back to plain up.
        u2 = run_cmd(["docker", "compose", "up", "-d"], cwd=bench_dir)
        if u2.returncode != 0:
            log(f"  ! up failed: {u2.stderr[-500:]}")
            return False
    return True


def discover_port(bench_dir: str, log):
    """Return the host port the benchmark published, parsed from `compose ps`."""
    ps = run_cmd(["docker", "compose", "ps", "--format", "json"], cwd=bench_dir)
    raw = ps.stdout.strip()
    if not raw:
        return None
    entries = []
    try:
        parsed = json.loads(raw)
        entries = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        for line in raw.splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    for e in entries:
        for pub in e.get("Publishers", []) or []:
            hp = pub.get("PublishedPort")
            if hp:
                return int(hp)
    return None


def stop_container(bench_dir: str):
    run_cmd(["docker", "compose", "down", "-v", "--remove-orphans"], cwd=bench_dir)


# ---------------------------------------------------------------------------
# Reachability probe (Step 2)
# ---------------------------------------------------------------------------
def verify_reachable(probe_host: str, port: int, attempts=10, delay=2.0) -> bool:
    url = f"http://{probe_host}:{port}/"
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=4) as r:
                if r.status < 600:   # any HTTP response = service is up
                    return True
        except urllib.error.HTTPError:
            return True              # 4xx/5xx still means the server answered
        except Exception:
            time.sleep(delay)
    return False


# ---------------------------------------------------------------------------
# Main protocol
# ---------------------------------------------------------------------------
def load_dataset(only=None):
    with open(DATASET, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if only:
        wanted = {x.strip() for x in only.split(",")}
        rows = [r for r in rows if r["challenge_id"] in wanted]
    return rows


def append_result(row: dict):
    new = not os.path.exists(RESULTS_CSV)
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser(description="VulnBot functionality test harness")
    ap.add_argument("--benchmarks-dir", required=True,
                    help="Path to the cloned xbow validation-benchmarks repo")
    ap.add_argument("--probe-host", default="127.0.0.1",
                    help="Host the harness uses to verify reachability")
    ap.add_argument("--vulnbot-target-host", default="host.docker.internal",
                    help="Host string VulnBot's Kali box uses to reach the target")
    ap.add_argument("--max-interactions", type=int, default=5)
    ap.add_argument("--repeat", type=int, default=1,
                    help="Repetitions per challenge (K). K>=3 enables reliability stats.")
    ap.add_argument("--only", default=None,
                    help="Comma-separated challenge ids to run a subset (e.g. XBEN-039-24)")
    args = ap.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)

    dataset = load_dataset(args.only)
    if not dataset:
        print("No challenges selected. Check --only / dataset.")
        sys.exit(1)

    run_scores, per_run_records = [], []
    vulnbot_log = os.path.join(PROJECT_ROOT, "logs", "Auto-Pentest.log")

    for rep in range(1, args.repeat + 1):
        for ch in dataset:
            cid = ch["challenge_id"]
            bench_dir = os.path.join(args.benchmarks_dir, "benchmarks", cid)
            run_id = f"RUN-{datetime.now().strftime('%Y%m%d_%H%M%S')}-{cid}-r{rep}"
            log_path = os.path.join(LOG_DIR, f"{run_id}.log")
            raw_path = os.path.join(RAW_DIR, f"{run_id}.json")
            logf = open(log_path, "w", encoding="utf-8")

            def log(msg):
                print(msg)
                logf.write(msg + "\n")
                logf.flush()

            log(f"=== {run_id} | {ch['category']} | level {ch['difficulty']} ===")

            if not os.path.isdir(bench_dir):
                log(f"  ! benchmark folder not found: {bench_dir}")
                logf.close()
                continue

            # Step 1: reset container
            log("  [1] resetting Docker container ...")
            if not reset_container(bench_dir, cid, log):
                log("  ! container reset failed - recording as unreachable run")
                _record_failed(run_id, ch, args, "", False, log_path, raw_path,
                               run_scores, per_run_records, "container_reset_failed")
                logf.close()
                continue

            # Step 2: discover port + verify reachable
            port = discover_port(bench_dir, log)
            reachable = bool(port) and verify_reachable(args.probe_host, port)
            log(f"  [2] target port={port} reachable={reachable}")
            if not reachable:
                _record_failed(run_id, ch, args, port or "", False, log_path, raw_path,
                               run_scores, per_run_records, "target_unreachable")
                stop_container(bench_dir)
                logf.close()
                continue

            # Steps 3-6: run a fresh VulnBot session as a subprocess
            log("  [3-6] running VulnBot session ...")
            cmd = [
                sys.executable, os.path.join(HERE, "vulnbot_session_runner.py"),
                "--run-id", run_id, "--challenge-id", cid,
                "--category", ch["category"], "--difficulty", ch["difficulty"],
                "--target-host", args.vulnbot_target_host, "--target-port", str(port),
                "--max-interactions", str(args.max_interactions), "--out", raw_path,
            ]
            proc = run_cmd(cmd, cwd=PROJECT_ROOT, timeout=3600)
            logf.write("\n----- runner stdout -----\n" + proc.stdout)
            logf.write("\n----- runner stderr -----\n" + proc.stderr)

            # Step 7: snapshot VulnBot's own log next to the run log
            if os.path.exists(vulnbot_log):
                shutil.copy(vulnbot_log, os.path.join(LOG_DIR, f"{run_id}_vulnbot.log"))

            # Step 8: score
            if not os.path.exists(raw_path):
                log("  ! runner produced no raw record")
                _record_failed(run_id, ch, args, port, True, log_path, raw_path,
                               run_scores, per_run_records, "no_raw_record")
                stop_container(bench_dir)
                logf.close()
                continue

            with open(raw_path, encoding="utf-8") as f:
                raw = json.load(f)
            raw["target_reachable_pre"] = True   # confirmed in step 2
            sc = metrics.score_run(raw)
            ofs_run = metrics.aggregate([sc]).get("OFS", 0.0)

            append_result(_to_result_row(run_id, ch, raw, sc, ofs_run, log_path, raw_path))
            run_scores.append(sc)
            per_run_records.append({"challenge_id": cid,
                                    "session_completed": raw["session_completed"],
                                    "OFS_run": ofs_run})
            log(f"  [8] scored: completed={raw['session_completed']} OFS_run={ofs_run}")

            # Step 1 (next): leave clean
            stop_container(bench_dir)
            logf.close()

    # ---- aggregate ----
    if run_scores:
        agg = metrics.aggregate(run_scores)
        _write_summary(agg, args.repeat, per_run_records)
        print("\n==================== HEADLINE RESULTS ====================")
        for k in ["SSR", "TRR", "SCR", "PQS", "CVR", "CRR", "EES", "MRS", "ERR",
                  "HIC_mean", "OFS"]:
            print(f"  {k:>4}: {agg.get(k)}")
        print(f"  VERDICT: {agg['verdict']['overall']}")
        print("==========================================================")
        print(f"Per-run rows : {RESULTS_CSV}")
        print(f"Summary      : {SUMMARY_CSV}")
        print(f"By category  : {CATEGORY_CSV}")
    else:
        print("No successful runs were scored.")


def _to_result_row(run_id, ch, raw, sc, ofs_run, log_path, raw_path):
    return {
        "run_id": run_id, "timestamp": datetime.now().isoformat(timespec="seconds"),
        "challenge_id": ch["challenge_id"], "category": ch["category"],
        "difficulty": ch["difficulty"],
        "target_host": raw.get("target_host", ""), "target_port": raw.get("target_port", ""),
        "startup_ok": int(bool(raw["startup_ok"])),
        "target_reachable_pre": int(bool(raw["target_reachable_pre"])),
        "session_completed": int(bool(raw["session_completed"])),
        "num_phases_executed": raw.get("num_phases_executed", 0),
        "SSR_i": sc["SSR_i"], "TRR_i": sc["TRR_i"], "SCR_i": sc["SCR_i"],
        "PQS_i": round(sc["PQS_i"], 3), "EES_i": round(sc["EES_i"], 3),
        "MRS_i": round(sc["MRS_i"], 3), "HIC_i": sc["HIC_i"],
        "commands_generated": sc["n_generated"], "commands_executed": sc["n_executed"],
        "commands_valid": sc["n_valid"], "commands_relevant": sc["n_relevant"],
        "commands_evidence": sc["n_evidence"], "errors": sc["n_errors"],
        "errors_recovered": sc["n_recovered"],
        "OFS_run": ofs_run, "fatal_error": raw.get("fatal_error") or "",
        "log_file": os.path.relpath(log_path, HERE),
        "raw_file": os.path.relpath(raw_path, HERE),
    }


def _record_failed(run_id, ch, args, port, reachable, log_path, raw_path,
                   run_scores, per_run_records, reason):
    """Record a run that failed before/at startup as an objective data point."""
    raw = {
        "run_id": run_id, "challenge_id": ch["challenge_id"], "category": ch["category"],
        "difficulty": ch["difficulty"], "target_host": args.vulnbot_target_host,
        "target_port": str(port), "startup_ok": False,
        "target_reachable_pre": reachable, "session_completed": False,
        "human_interventions": 0, "fatal_error": reason, "num_phases_executed": 0,
        "phases": [], "commands": [], "transitions": [],
    }
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)
    sc = metrics.score_run(raw)
    ofs_run = metrics.aggregate([sc]).get("OFS", 0.0)
    append_result(_to_result_row(run_id, ch, raw, sc, ofs_run, log_path, raw_path))
    run_scores.append(sc)
    per_run_records.append({"challenge_id": ch["challenge_id"],
                            "session_completed": False, "OFS_run": ofs_run})


def _write_summary(agg, repeat, per_run_records):
    # headline summary
    with open(SUMMARY_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value", "unit", "threshold", "pass"])
        order = [
            ("SSR", "System Startup Success Rate", "%", metrics.THRESHOLDS["SSR"]),
            ("TRR", "Target Reachability Success Rate", "%", metrics.THRESHOLDS["TRR"]),
            ("SCR", "Session Completion Rate", "%", metrics.THRESHOLDS["SCR"]),
            ("PQS", "Planning Quality Score", "%", metrics.THRESHOLDS["PQS"]),
            ("CVR", "Command Validity Rate", "%", metrics.THRESHOLDS["CVR"]),
            ("CRR", "Command Relevance Rate", "%", metrics.THRESHOLDS["CRR"]),
            ("EES", "Evidence Extraction Score", "%", metrics.THRESHOLDS["EES"]),
            ("MRS", "Memory Retention Score", "%", metrics.THRESHOLDS["MRS"]),
            ("ERR", "Error Recovery Rate", "%", metrics.THRESHOLDS["ERR"]),
            ("HIC_mean", "Human Intervention Count (mean)", "count",
             metrics.THRESHOLDS["HIC_mean_max"]),
            ("OFS", "Overall Functionality Score", "%", metrics.THRESHOLDS["OFS"]),
        ]
        checks = agg["verdict"]["per_metric"]
        keymap = {"HIC_mean": "HIC"}
        for key, label, unit, thr in order:
            passed = checks.get(keymap.get(key, key), "")
            w.writerow([f"{label} ({key})", agg.get(key), unit, thr,
                        "PASS" if passed else "FAIL"])
        w.writerow([])
        w.writerow(["Overall verdict", agg["verdict"]["overall"], "", "", ""])
        w.writerow(["Runs (N)", agg["N"], "", "", ""])
        w.writerow(["Commands generated", agg["commands_generated"], "", "", ""])
        w.writerow(["Commands executed", agg["commands_executed"], "", "", ""])
        w.writerow(["Errors observed", agg["errors_observed"], "", "", ""])

        if repeat >= 2:
            rel = metrics.reliability(per_run_records, repeat)
            w.writerow([])
            w.writerow(["RELIABILITY (K repetitions)", "", "", "", ""])
            w.writerow(["Repetitions per challenge", rel["repetitions_per_challenge"],
                        "", "", ""])
            w.writerow(["Completion consistency", rel["completion_consistency_pct"],
                        "%", "", ""])
            w.writerow(["Mean coefficient of variation (OFS)",
                        rel["mean_coefficient_of_variation"], "", "", ""])

    # per-category breakdown (re-score grouped)
    _write_category_summary()


def _write_category_summary():
    if not os.path.exists(RESULTS_CSV):
        return
    by_cat = {}
    with open(RESULTS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            by_cat.setdefault(r["category"], []).append(r)
    with open(CATEGORY_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "runs", "SCR_%", "startup_%",
                    "mean_PQS", "mean_EES", "mean_MRS",
                    "commands_generated", "commands_valid", "commands_relevant"])
        for cat, rows in by_cat.items():
            n = len(rows)
            def favg(k):
                return round(sum(float(x[k]) for x in rows) / n, 3)
            w.writerow([
                cat, n,
                round(100 * sum(int(x["SCR_i"]) for x in rows) / n, 1),
                round(100 * sum(int(x["startup_ok"]) for x in rows) / n, 1),
                favg("PQS_i"), favg("EES_i"), favg("MRS_i"),
                sum(int(x["commands_generated"]) for x in rows),
                sum(int(x["commands_valid"]) for x in rows),
                sum(int(x["commands_relevant"]) for x in rows),
            ])


if __name__ == "__main__":
    main()
