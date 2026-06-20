# VulnBot Functionality & Reliability Test Suite

Reproducible test cases that answer the research question:

> **Does VulnBot function correctly and reliably as an automated penetration testing system?**

This suite measures the **VulnBot workflow** (start-up, reachability, planning,
command generation/execution, evidence capture, memory hand-off, error recovery,
autonomy) — **not** the LLM's hacking skill. Targets come from the public
**XBOW Validation Benchmarks**. Full design, formulas and success thresholds are
in **[`METHODOLOGY.md`](./METHODOLOGY.md)**.

## Files

| File | Purpose |
|------|---------|
| `functionality_test_dataset.csv` | The 20 balanced challenges (5 categories × 4), with the exact target text given to VulnBot. |
| `metrics.py` | **Single source of truth** for every metric formula + the pass/fail verdict. |
| `vulnbot_session_runner.py` | Drives one real, non-interactive VulnBot session and extracts objective evidence from the DB. |
| `run_functionality_tests.py` | The harness: reset → verify → run → log → score → store, for all challenges. |
| `scoring_rubric.md` | Explicit binary rules behind every score (for auditing / manual review). |
| `functionality_results.csv` | Per-run results (one row per run). Header is provided; rows are appended at runtime. |
| `results_summary.csv` | Headline metrics + thresholds + verdict (generated). |
| `results_by_category.csv` | Metrics per vulnerability category (generated). |

## Prerequisites

1. **Docker + docker compose**, and the XBOW benchmarks cloned locally:
   ```bash
   git clone https://github.com/xbow-engineering/validation-benchmarks.git
   ```
2. **A configured VulnBot stack** (from the project root):
   ```bash
   python cli.py init                 # create config + DB tables
   docker compose up -d               # VulnBot's MySQL + Kali SSH box
   # edit model_config.yaml  -> api_key / base_url / llm_model / llm_model_name
   # edit db_config.yaml      -> point at the MySQL above
   # edit basic_config.yaml   -> kali hostname/port (e.g. 127.0.0.1:2222), mode: auto
   ```
3. Python deps already used by VulnBot (`pip install -r requirements.txt`). The
   harness adds no new dependencies.

## Run

From the **project root**:

```bash
# Correctness pass (single run per challenge)
python test-cases/run_functionality_tests.py --benchmarks-dir /path/to/validation-benchmarks

# Correctness + reliability (recommended: 3 repetitions per challenge)
python test-cases/run_functionality_tests.py --benchmarks-dir /path/to/validation-benchmarks --repeat 3

# Smoke-test the pipeline on a single challenge first
python test-cases/run_functionality_tests.py --benchmarks-dir /path/to/validation-benchmarks --only XBEN-039-24
```

Useful flags:

| Flag | Default | Meaning |
|------|---------|---------|
| `--benchmarks-dir` | *(required)* | Path to the cloned XBOW repo. |
| `--probe-host` | `127.0.0.1` | Where the harness checks the target is up. |
| `--vulnbot-target-host` | `host.docker.internal` | Host string VulnBot's Kali box uses to reach the target. |
| `--max-interactions` | `5` | VulnBot interaction budget per role (`-m`). |
| `--repeat` | `1` | Repetitions per challenge (`K`). `K ≥ 3` unlocks reliability stats. |
| `--only` | *(all)* | Comma-separated challenge ids for a subset run. |

## Output

* **`functionality_results.csv`** — raw per-run evidence (appendix table).
* **`results_summary.csv`** — the 11 headline metrics, each with its pass
  threshold and PASS/FAIL, plus the overall verdict (main results table).
* **`results_by_category.csv`** — per-category breakdown for the discussion.
* **`logs/`** and **`raw/`** — per-run console logs, a copy of VulnBot's
  `Auto-Pentest.log`, and the machine-readable raw record for each run.

## How scoring stays honest

* Metrics are computed from the **VulnBot MySQL database and logs**, not from
  anything the harness invents.
* The pass thresholds are **pre-registered** in `metrics.py` (fixed before
  running), so the verdict cannot be tuned to the data.
* Every score follows an **explicit binary rule** in `scoring_rubric.md`.
* The challenge selection rule is **deterministic** (see `METHODOLOGY.md` §2.1),
  so the dataset is balanced and bias-free.
