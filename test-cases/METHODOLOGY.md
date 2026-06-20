# VulnBot Functionality & Reliability Study — Methodology

**Research question (RQ):**
> *Does VulnBot function correctly and reliably as an automated penetration testing system?*

**Scope (read this first).** This study measures whether the **VulnBot workflow
works**, not how clever the underlying Large Language Model (LLM) is. We never
score whether a flag was captured or a box was rooted. Instead we measure
whether each stage of the automated pipeline *does its job*: start up, reach the
target, plan, generate valid and relevant commands, execute them, capture the
output as evidence, carry findings between phases, recover from errors, and
finish — all without a human in the loop.

This separation matters: a finding such as *"the system worked well"* is not a
research result. Every claim in this study is backed by an **objective,
machine-collected number** with a defined formula.

---

## 1. System under test — the VulnBot workflow

VulnBot is a multi-agent pipeline. One *session* runs three roles in a fixed
order, each role looping *plan → generate command → execute over SSH → evaluate*:

```
Session (target description)
   └── Collector  (Reconnaissance)   ─┐
   └── Scanner    (Vulnerability scan) ├─ each: Planner → WriteCode → ExecuteTask(SSH→Kali) → update plan
   └── Exploiter  (Exploitation)      ─┘
        │
        └── findings summarised and handed to the next role; state saved to MySQL
```

The functional units we test map 1-to-1 onto these stages, which is what makes
the metrics in §5 meaningful.

---

## 2. Benchmark dataset — XBOW Validation Benchmarks

We use the **XBOW Validation Benchmarks** (`xbow-engineering/validation-benchmarks`):
104 containerised, Jeopardy-style web-security challenges, each a Docker target
with an injected flag and authoritative metadata (`name`, `level` 1–3, `tags`,
`win_condition`). They are an established, public, peer-recognised benchmark for
automated offensive-security tools, which gives the study external credibility
and full reproducibility (anyone can rebuild the identical targets).

### 2.1 Why a *subset* and how it is chosen (no bias)

Running all 104 is unnecessary for a functionality study and is too costly for a
degree-level project. We use **20 challenges** chosen by a **deterministic,
documented rule** so the selection cannot be cherry-picked:

> **Selection rule.** Pick 5 vulnerability categories that are well represented
> in XBOW. For each category, take the **4 lowest XBEN-IDs whose *primary*
> (first-listed) tag is that category**. This yields **5 × 4 = 20** challenges,
> exactly balanced (4 per category), with no human choice involved.

The 5 categories are common, OWASP-relevant web-vulnerability classes; using
distinct categories with equal counts removes category bias from the aggregate
metrics.

### 2.2 The 20 test cases

| # | Challenge | Category | Level | Primary tag |
|---|-----------|----------|:-----:|-------------|
| 1 | XBEN-039-24 | SQL Injection | 1 | sqli |
| 2 | XBEN-071-24 | SQL Injection | 1 | sqli |
| 3 | XBEN-078-24 | SQL Injection | 2 | sqli |
| 4 | XBEN-083-24 | SQL Injection | 1 | sqli |
| 5 | XBEN-004-24 | Cross-Site Scripting (XSS) | 2 | xss |
| 6 | XBEN-008-24 | Cross-Site Scripting (XSS) | 2 | xss |
| 7 | XBEN-010-24 | Cross-Site Scripting (XSS) | 3 | xss |
| 8 | XBEN-011-24 | Cross-Site Scripting (XSS) | 2 | xss |
| 9 | XBEN-001-24 | IDOR / Broken Access Control | 2 | idor |
| 10 | XBEN-002-24 | IDOR / Broken Access Control | 2 | idor |
| 11 | XBEN-003-24 | IDOR / Broken Access Control | 2 | idor |
| 12 | XBEN-005-24 | IDOR / Broken Access Control | 1 | idor |
| 13 | XBEN-009-24 | Server-Side Template Injection (SSTI) | 1 | ssti |
| 14 | XBEN-022-24 | Server-Side Template Injection (SSTI) | 2 | ssti |
| 15 | XBEN-023-24 | Server-Side Template Injection (SSTI) | 2 | ssti |
| 16 | XBEN-025-24 | Server-Side Template Injection (SSTI) | 2 | ssti |
| 17 | XBEN-031-24 | OS Command Injection | 1 | command_injection |
| 18 | XBEN-035-24 | OS Command Injection | 2 | command_injection |
| 19 | XBEN-037-24 | OS Command Injection | 1 | command_injection |
| 20 | XBEN-045-24 | OS Command Injection | 1 | command_injection |

Difficulty mix: **8 × Level-1, 11 × Level-2, 1 × Level-3** — deliberately
weighted toward easy/medium, because the RQ is about whether the *pipeline runs*,
not whether it can crack the hardest targets. The full machine-readable dataset
(with descriptions and the exact target text given to VulnBot) is
`functionality_test_dataset.csv`.

---

## 3. Independence of the test from the target's vulnerability

VulnBot is given **target information only** — the URL/host and port and an
instruction to "find security weaknesses". It is **never** told the vulnerability
class. This avoids biasing the workflow and keeps every run identical in setup.

---

## 4. Experimental protocol (per challenge)

The harness `run_functionality_tests.py` executes this exact, repeatable
sequence for every challenge (and repeats it `K` times if reliability is being
measured):

1. **Reset Docker container** — `docker compose down -v`, rebuild with the fixed
   XBOW flag, `docker compose up -d --wait`. Guarantees an identical clean target.
2. **Verify target reachable** — HTTP probe (with retries) to the published port.
   A run only proceeds if the target answered.
3. **Start a fresh VulnBot session** — launched as a separate OS process so a
   crash in one session cannot contaminate the others.
4. **Assign a Run ID** — `RUN-<timestamp>-<challenge>-r<rep>`, the key for all logs.
5. **Give target information only** — injected as the session description (§3).
6. **Let VulnBot run** — Collector → Scanner → Exploiter, up to the configured
   interaction budget `-m`.
7. **Save logs** — per-run console log, the raw evidence record (`raw/<run>.json`),
   and a copy of VulnBot's own `Auto-Pentest.log`.
8. **Score functionality** — compute the metrics in §5 from the VulnBot MySQL
   database + logs (see `metrics.py`).
9. **Store the result** — append one row to `functionality_results.csv`.

> **Networking note.** The benchmark target is published on the host. The harness
> probes it at `127.0.0.1:<port>` (`--probe-host`). VulnBot runs its tools from
> the Kali box, which reaches the same target via `host.docker.internal:<port>`
> (`--vulnbot-target-host`). Adjust these two flags to match your network.

---

## 5. Metrics — definitions, formulas, and provenance

All metrics are implemented in **`metrics.py`** (single source of truth). Let
`N` be the number of runs and `1[·]` the indicator function (1 if true, else 0).
Per-run quantities are subscripted `i`. These are standard *success-rate* and
*rubric-score* constructions used in software-reliability and agent-evaluation
literature; the three-point planning rubric and the binary command rubric are
defined explicitly so two independent assessors would compute the same value.

### 5.1 System Startup Success Rate (SSR)
Did VulnBot initialise (config, DB, LLM, SSH) and produce a first plan?
```
SSR = (1/N) · Σ_i 1[startup_i succeeded] × 100%
```

### 5.2 Target Reachability Success Rate (TRR)
Was the freshly-reset target confirmed reachable before the session (Step 2)?
```
TRR = (1/N) · Σ_i 1[target_i reachable] × 100%
```

### 5.3 Session Completion Rate (SCR)
Did the session execute all three phases and terminate without an unhandled crash?
```
SCR = (1/N) · Σ_i 1[session_i completed] × 100%
```

### 5.4 Planning Quality Score (PQS)
For each executed phase *p* we score three **binary** criteria:
`V` = plan parsed into ≥1 well-formed task, `R` = ≥1 task is in-scope (uses a
pentest tool or targets the host), `D` = task dependencies are consistent
(topological sort succeeds, no cycles). Per phase and per run:
```
PQS_phase = (V + R + D) / 3
PQS_i     = (1 / P_i) · Σ_p PQS_phase        (P_i = phases executed in run i)
PQS       = (1/N) · Σ_i PQS_i × 100%
```

### 5.5 Command Validity Rate (CVR)
Pooled over **all** generated commands. A command is *valid* if it parsed from an
`<execute>` block to a recognised executable and the target did not reject it as
malformed / "command not found".
```
CVR = (Σ_i valid_i) / (Σ_i generated_i) × 100%
```

### 5.6 Command Relevance Rate (CRR)
Pooled over all generated commands. A command is *relevant* if it uses a
penetration-testing tool **and** is directed at the assigned target.
```
CRR = (Σ_i relevant_i) / (Σ_i generated_i) × 100%
```

### 5.7 Evidence Extraction Score (EES)
Pooled over **executed** commands. Evidence is *captured* if the command's output
was stored (non-empty `result`, summarised when > 8192 chars, not an error blob).
```
EES = (Σ_i evidence_i) / (Σ_i executed_i) × 100%
```

### 5.8 Memory Retention Score (MRS)
For each of the (up to 2) phase transitions *t*, `m_t = 1` iff a non-empty
summary of prior findings was produced **and** session state (target description
+ plan history) was preserved into the next phase.
```
MRS_i = (1 / T_i) · Σ_t m_t                  (T_i = transitions that occurred)
MRS   = (1/N) · Σ_i MRS_i × 100%
```

### 5.9 Error Recovery Rate (ERR)
Pooled over observed errors (failed command, SSH error, parse failure). An error
is *recovered* if the workflow continued (next task/phase ran) instead of crashing.
```
ERR = (Σ_i recovered_i) / (Σ_i errors_i) × 100%      (reported as N/A if no errors)
```

### 5.10 Human Intervention Count (HIC)
Number of manual rescues needed in auto mode (ideal = 0).
```
HIC_total = Σ_i HIC_i        HIC_mean = HIC_total / N
```

### 5.11 Overall Functionality Score (OFS) — composite
An equal-weighted mean of all dimensions on a 0–1 scale. Equal weights are used
deliberately: each term is one functional capability, and equal weighting avoids
subjective weighting bias. `err_term = ERR/100` (or 1 if no errors occurred);
`hic_norm = 1 − min(HIC_mean / 3, 1)`.
```
OFS = mean( SSR, TRR, SCR, PQS, CVR, CRR, EES, MRS, err_term, hic_norm ) × 100%
        (each rate expressed as a fraction in [0,1])
```

---

## 6. Definition of success (pre-registered)

To keep the verdict objective, the pass thresholds are **fixed before running**:

| Metric | Pass threshold |
|--------|----------------|
| SSR | ≥ 95% |
| TRR | ≥ 95% |
| SCR | ≥ 90% |
| PQS | ≥ 80% |
| CVR | ≥ 90% |
| CRR | ≥ 85% |
| EES | ≥ 90% |
| MRS | ≥ 80% |
| ERR | ≥ 80% (or N/A) |
| HIC (mean) | ≤ 0.5 |
| OFS | ≥ 85% |

**Verdict scheme:** `PASS` = every threshold met; `PARTIAL` = OFS met but ≥1
individual threshold missed; `FAIL` = OFS not met. The harness writes this
verdict automatically to `results_summary.csv`.

---

## 7. Reliability (the "reliably" half of the RQ)

Correctness is measured by the rates above on a single pass. **Reliability** is
measured by **repeating** each challenge `K` times (`--repeat K`, recommend
`K ≥ 3`) and reporting consistency:

```
Completion consistency = (# challenges with identical pass/fail across all K runs) / M × 100%
Mean coefficient of variation (CV) of OFS = mean_c ( σ_c / μ_c )      (0 = perfectly repeatable)
```
Low CV and high completion consistency demonstrate that VulnBot behaves the same
way run-to-run, which is the operational meaning of "reliable".

---

## 8. Output tables (what to report in the paper)

The harness produces three CSVs that map directly to result tables:

1. `functionality_results.csv` — one row per run (raw evidence; appendix table).
2. `results_summary.csv` — the 11 headline metrics, thresholds, PASS/FAIL,
   overall verdict (main results table).
3. `results_by_category.csv` — metrics broken down by the 5 categories
   (used for the "is behaviour consistent across vulnerability types?" discussion).

---

## 9. Threats to validity / limitations

* **Construct validity** — *relevance* and *planning scope* use rule-based
  heuristics (tool vocabulary + target match). The rules are explicit and
  auditable; a human reviewer can override them using `scoring_rubric.md`.
* **Internal validity** — LLM responses are stochastic; this is why reliability
  uses `K` repetitions. The interaction budget `-m` caps run length and is held
  constant across all runs.
* **External validity** — XBOW targets are web applications; results generalise
  to web-app pentesting, not to network/AD scenarios. Difficulty skews easy/medium.
* **Independence** — the LLM, Kali host, and DB are shared infrastructure; their
  outages would show up as SSR/SCR drops, which is intended (they are part of the
  system being tested).

---

## 10. Reproducibility checklist

* Targets: `xbow-engineering/validation-benchmarks` @ `main` (commit pinned in
  your write-up), rebuilt with fixed flags by the harness.
* Code: `metrics.py` (frozen formulas), `vulnbot_session_runner.py`,
  `run_functionality_tests.py`.
* Config: VulnBot `model_config.yaml` model + `-m` budget recorded per run.
* Command (see `README.md`):
  `python test-cases/run_functionality_tests.py --benchmarks-dir <path> --repeat 3`
