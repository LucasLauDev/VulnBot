# VulnBot Standalone Benchmark Runner

A self-contained driver that runs VulnBot end-to-end against the curated
benchmark sets in this repository:

| Set                                                       | Path                                            | Layout                                              |
| --------------------------------------------------------- | ----------------------------------------------- | --------------------------------------------------- |
| Vulhub (selected nine vulnerability categories)           | `benchmark/vulhub/selected-benchmark/`          | `<app>/<CVE-or-name>/{docker-compose.yml,README.md}` |
| XBOW Validation Benchmarks (104 web-style CTF challenges) | `benchmark/xbow-val-benchmark/selected-benchmarks/` | `XBEN-XXX-24/{docker-compose.yml,benchmark.json,.env}` |

The runner detects the dataset layout automatically, brings up each
benchmark's Docker stack, drives VulnBot non-interactively against the
target, parses the transcript for flags / exploit evidence and writes a
per-run JSON / text / per-benchmark log.

The design is intentionally close to the
`PentestGPT/benchmark/standalone-xbow-benchmark-runner/` runner so that
results are directly comparable.

## Layout

```
benchmark/standalone-benchmark-runner/
├── README.md
├── requirements.txt
├── run_benchmarks.py          # CLI entry-point
├── vulnbot_driver.py          # non-interactive VulnBot driver (subprocess target)
└── src/
    ├── benchmark_loader.py    # detect + parse XBOW / Vulhub benchmark folders
    ├── benchmark_runner.py    # orchestrator
    ├── docker_manager.py      # docker compose lifecycle, port detection
    ├── models.py              # dataclasses for config / info / result / summary
    ├── output_parser.py       # flag / error / keyword extraction
    ├── reporter.py            # detailed.log + summary.json/.txt
    ├── state_manager.py       # resume support
    └── vulnbot_executor.py    # subprocess launch with timeout + streaming
```

## Prerequisites

1. **VulnBot installed and configured**  
   The runner imports VulnBot's normal Python modules. Install dependencies
   from the project root:

   ```bash
   cd VulnBot
   pip install -r requirements.txt
   ```

   Then configure `model_config.yaml`, `db_config.yaml`,
   `basic_config.yaml` (Kali credentials) and run `python cli.py init` per
   the main README.

2. **VulnBot infrastructure stack running**  
   The Kali SSH worker container and the MySQL session DB are launched
   together via the project root `docker-compose.yml`:

   ```bash
   cd VulnBot
   docker compose up -d
   ```

   The runner will warn if the `kali-ssh` container is not visible.

3. **Docker Desktop / Docker Engine reachable** so the runner can start
   benchmark target stacks (`docker compose up -d` inside each benchmark
   folder).

4. **Python 3.11+** (matches VulnBot's runtime; the runner itself is
   stdlib-only).

## Quick start

```bash
cd VulnBot/benchmark/standalone-benchmark-runner

# Discover what is available (auto-detects benchmarks dir and kind):
python run_benchmarks.py --list

# Vulhub: run a few CVEs by ID:
python run_benchmarks.py \
  --benchmarks-dir ../vulhub/selected-benchmark \
  --ids 1panel/CVE-2024-39907,bash/CVE-2014-6271 \
  --max-interactions 8

# XBOW: run a numbered range (uses the strict pattern-based flag matcher):
python run_benchmarks.py \
  --benchmarks-dir ../xbow-val-benchmark/selected-benchmarks \
  --range 1-5 \
  --pattern-flag

# Run everything in the auto-detected dataset, but skip benchmarks that
# already succeeded in a previous interrupted run:
python run_benchmarks.py --all --resume

# Just preview what would happen (no Docker, no VulnBot):
python run_benchmarks.py --all --dry-run
```

## CLI reference

```
Selection (exactly one is required, or use --list):
  --range N-M                1-based index range over the sorted benchmark list.
  --ids ID[,ID,...]          Comma-separated benchmark IDs.
                             vulhub: <app>/<CVE-or-name>      e.g. activemq/CVE-2023-46604
                             xbow:   XBEN-XXX-24              e.g. XBEN-001-24
  --all                      Run every detected benchmark.
  --retry-failed [PATH]      Retry only failed entries from a previous run.

Discovery / scope:
  --list                     Print the detected benchmark IDs and exit.
  --benchmarks-dir PATH      Override auto-detection. Should point at the
                             selected-benchmark / selected-benchmarks folder.
  --kind {auto,vulhub,xbow}  Force a specific dataset kind.

Execution:
  --timeout SECONDS          Per-benchmark wall-clock timeout (default 1800).
  --max-interactions N       Max VulnBot react iterations per role (default 10).
  --retries N                Re-run a failing benchmark up to N times.
  --resume                   Skip benchmarks already in state.json's "completed".
  --dry-run                  Preview only.
  --output-dir PATH          Logs / summaries directory (default ./logs).
  --skip-infra-check         Skip the kali-ssh presence check.
  --python PATH              Python interpreter for the VulnBot driver.

Flag validation (mutually exclusive):
  --any-flag                 Success if any flag-shaped string is detected.
  --pattern-flag             Success if a flag matches FLAG{32+ alnum/dashes}.
  --success-keyword WORD     Extra keyword counted as exploit evidence.
                             May be repeated. Useful in vulhub mode where
                             benchmarks have no fixed flag.
```

## How it drives VulnBot

VulnBot's regular CLI (`python cli.py vulnbot -m N`) uses
`prompt_toolkit` for an interactive task description and session-save
prompt — not friendly to subprocess piping. The runner therefore launches
a small in-process driver (`vulnbot_driver.py`) that:

1. Adds the VulnBot project root to `sys.path` (resolved via
   `VULNBOT_ROOT` or the runner's relative location).
2. Constructs a `Session` with a pre-built natural-language description
   that includes the benchmark name, CVE, tag(s), target URL/ports and a
   short README excerpt.
3. Executes the standard `Collector → Scanner → Exploiter` chain via
   `Collector.run(session)`.
4. Emits the markers `[BENCH-START]`, `[BENCH-DONE]`,
   `[BENCH-EXCEPTION]`, `[BENCH-WARN]`, `[BENCH-INFO]` so the parent
   runner can phase the transcript and detect failures.
5. Closes the persistent `ShellManager` SSH session at the end.

Each benchmark's transcript is scraped for:

* flag-shaped substrings (`flag{...}`, `FLAG{...}`, `HTB{...}`,
  `CTF{...}`, 32-hex strings),
* generic exploit-success keywords (`uid=`, `root@`, `etc/passwd`, …),
* error patterns (`Traceback`, `ConnectionRefusedError`,
  `[BENCH-EXCEPTION]`).

Status decision tree:

| Condition                                                   | Status     |
| ----------------------------------------------------------- | ---------- |
| Wall-clock timeout                                           | `TIMEOUT`  |
| `[BENCH-EXCEPTION]` / `Traceback` and no flag/keyword       | `ERROR`    |
| Expected flag matched (XBOW) or pattern/any-flag matched     | `SUCCESS`  |
| Vulhub: keyword hit + clean `[BENCH-DONE]`                   | `SUCCESS`  |
| Otherwise                                                    | `FAILURE`  |

## Output structure

```
logs/
└── benchmark_run_YYYYMMDD_HHMMSS/
    ├── summary.json        # machine-readable aggregate
    ├── summary.txt         # human-readable aggregate
    ├── detailed.log        # one line per START/COMPLETE event
    ├── state.json          # resume state (set of completed/failed IDs)
    └── benchmarks/
        ├── activemq__CVE-2023-46604.log
        ├── XBEN-001-24.log
        └── ...
```

Per-benchmark log lines are timestamped (`<isoformat> <line>`) so that
log inspection tools (e.g. `grep ' \[FLAG\]'`, `tail -f`) work cleanly.

## Caveats

* Many Vulhub `docker-compose.yml` files map host ports directly (e.g.
  `10086:10086`); some only `expose:` ports without publishing them. In
  the latter case the runner emits a warning and instructs the agent to
  reach the target via the docker network. You may need a custom Kali
  image with `--network` access or pre-existing `host.docker.internal`
  routing.
* VulnBot's "success" semantics differ from PentestGPT. For Vulhub the
  flag matcher is a heuristic — combine `--success-keyword` with
  domain-specific tokens (e.g. `--success-keyword 'cmd executed'
  --success-keyword 'orderBy'`) to harden detection.
* VulnBot persists sessions to MySQL by default. The runner passes
  `--no-save` to the driver so benchmark sessions do not pollute the DB.
  Pass a custom `--save-name` and remove `--no-save` from
  `benchmark_runner.run_single_benchmark` if you want them archived.
