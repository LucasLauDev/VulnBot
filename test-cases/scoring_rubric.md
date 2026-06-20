# Scoring Rubric (objective, binary criteria)

Every per-run signal is scored automatically by `vulnbot_session_runner.py`
(reading the VulnBot MySQL database + logs) using the **explicit binary rules**
below. The rules are written so that two independent assessors would arrive at
the same score. If you choose to manually review a run, apply these same rules
and override the value in `functionality_results.csv`.

| Signal | Source | Scored **1 / pass** when … |
|--------|--------|----------------------------|
| `startup_ok` | session object | VulnBot created ≥1 plan (config + DB + LLM all worked enough to begin). |
| `target_reachable_pre` | harness HTTP probe | The reset target answered an HTTP request on its published port before the session. |
| `session_completed` | plan chain | Plans exist for all 3 phases (Collector, Scanner, Exploiter) and no unhandled exception escaped. |
| **Planning — V** (parsed) | `plans`/`tasks` tables | The phase plan parsed into ≥1 well-formed task row. |
| **Planning — R** (scope) | task instructions | ≥1 task uses a recognised pentest tool **or** references the target host/port. |
| **Planning — D** (deps) | `Plan.get_sorted_tasks()` | Topological sort succeeds (no cyclic / dangling dependencies). |
| Command `valid` | task `code` + `result` | First token is a recognised executable (or a path) **and** output has no `command not found` / malformed-command / SSH-failure marker. |
| Command `relevant` | task `code` | Uses a penetration-testing tool **and** is aimed at the assigned target (host/port present, or a self-targeting tool such as `searchsploit`/`msfconsole`/`wpscan`). |
| Command `evidence_captured` | task `result` | Output stored, non-empty, and not solely an error blob (long output must be the summarised form). |
| Command `is_error` | task `result` | Output contains an error marker (`command not found`, `SSH to Kali failed`, `Remote command failed`, `?Invalid command.`, `could not resolve host`, traceback, or "no shell command in model output"). |
| Command `recovered` | task ordering | The command errored **but** a later task in the same phase, or a later phase, still ran. |
| Transition `summary_nonempty` | prior phase tasks | The previous phase produced ≥1 finished task with non-empty evidence to summarise. |
| Transition `state_preserved` | session object | The next-phase plan exists and the original target description survived into it. |
| `human_interventions` | harness | +1 each time a human had to act for the run to proceed (manual command, restart). Auto mode target = 0. |

### Recognised tool vocabulary
Defined in `vulnbot_session_runner.py:PENTEST_TOOLS` and drawn directly from the
three VulnBot role tool lists (`roles/collector.py`, `roles/scanner.py`,
`roles/exploiter.py`) plus common shell utilities. Edit that one set if you add
tools to VulnBot, so the rubric stays in sync with the system.

### Error markers
Defined in `vulnbot_session_runner.py:ERROR_MARKERS`. These strings are exactly
the failure messages VulnBot's own executor emits (`actions/execute_task.py`),
so an "error" in this study means "VulnBot itself reported a failure".
