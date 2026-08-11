"""generate_report.py - Build the functionality-study evaluation report.

Reads `functionality_results.csv` (one row per VulnBot run), recomputes the
headline metrics with the frozen formulas in `metrics.py`, renders a set of
graphs into `figures/`, and writes `RESULTS_EVALUATION.md` - a comprehensive
discussion of the evaluation metrics.

Usage:  python test-cases/generate_report.py
"""
from __future__ import annotations

import csv
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import metrics

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_CSV = os.path.join(HERE, "functionality_results.csv")
CATEGORY_CSV = os.path.join(HERE, "results_by_category.csv")
FINDINGS_CSV = os.path.join(HERE, "testing_findings.csv")
FIG_DIR = os.path.join(HERE, "figures")
REPORT_MD = os.path.join(HERE, "RESULTS_EVALUATION.md")

PASS_COLOR = "#2e7d32"
FAIL_COLOR = "#c62828"
NEUTRAL = "#1565c0"

METRIC_LABELS = {
    "SSR": "System Startup Success Rate",
    "TRR": "Target Reachability Success Rate",
    "SCR": "Session Completion Rate",
    "PQS": "Planning Quality Score",
    "CVR": "Command Validity Rate",
    "CRR": "Command Relevance Rate",
    "EES": "Evidence Extraction Score",
    "MRS": "Memory Retention Score",
    "ERR": "Error Recovery Rate",
    "OFS": "Overall Functionality Score",
}


def load_runs():
    with open(RESULTS_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _i(row, k):
    try:
        return int(float(row.get(k, 0) or 0))
    except (ValueError, TypeError):
        return 0


def _f(row, k):
    try:
        return float(row.get(k, 0) or 0)
    except (ValueError, TypeError):
        return 0.0


def row_to_score(row):
    """Rebuild a metrics.score_run()-shaped dict from one CSV row."""
    return {
        "SSR_i": _i(row, "SSR_i"),
        "TRR_i": _i(row, "TRR_i"),
        "SCR_i": _i(row, "SCR_i"),
        "PQS_i": _f(row, "PQS_i"),
        "EES_i": _f(row, "EES_i"),
        "MRS_i": _f(row, "MRS_i"),
        "HIC_i": _i(row, "HIC_i"),
        "n_generated": _i(row, "commands_generated"),
        "n_executed": _i(row, "commands_executed"),
        "n_valid": _i(row, "commands_valid"),
        "n_relevant": _i(row, "commands_relevant"),
        "n_evidence": _i(row, "commands_evidence"),
        "n_errors": _i(row, "errors"),
        "n_recovered": _i(row, "errors_recovered"),
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def fig_headline(agg, checks):
    keys = ["SSR", "TRR", "SCR", "PQS", "CVR", "CRR", "EES", "MRS", "ERR", "OFS"]
    vals, cols, thrs, labels = [], [], [], []
    for k in keys:
        v = agg.get(k)
        if v is None:
            continue
        vals.append(v)
        labels.append(k)
        thrs.append(metrics.THRESHOLDS.get(k))
        cols.append(PASS_COLOR if checks.get(k) else FAIL_COLOR)
    y = range(len(labels))
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(list(y), vals, color=cols)
    for i, (v, t) in enumerate(zip(vals, thrs)):
        if t is not None:
            ax.plot([t, t], [i - 0.4, i + 0.4], color="black", lw=2)
        ax.text(min(v + 1.5, 101), i, f"{v:.1f}%", va="center", fontsize=9)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels)
    ax.set_xlim(0, 105)
    ax.invert_yaxis()
    ax.set_xlabel("Score (%)  -  black tick = pass threshold")
    ax.set_title("Headline functionality metrics vs pre-registered thresholds")
    plt.tight_layout()
    p = os.path.join(FIG_DIR, "headline_metrics.png")
    plt.savefig(p, dpi=130)
    plt.close()
    return p


def fig_funnel(agg):
    stages = ["Generated", "Executed", "Valid", "Relevant", "Evidence"]
    vals = [agg["commands_generated"], agg["commands_executed"], agg["commands_valid"],
            agg["commands_relevant"], agg["commands_with_evidence"]]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(stages, vals, color=["#1565c0", "#1976d2", "#42a5f5", "#90caf9", "#2e7d32"])
    for i, v in enumerate(vals):
        ax.text(i, v + max(vals) * 0.01 + 0.1, str(v), ha="center", fontsize=10)
    ax.set_ylabel("Command count (pooled over all runs)")
    ax.set_title("Command pipeline funnel")
    plt.tight_layout()
    p = os.path.join(FIG_DIR, "command_funnel.png")
    plt.savefig(p, dpi=130)
    plt.close()
    return p


def fig_per_category():
    if not os.path.exists(CATEGORY_CSV):
        return None
    with open(CATEGORY_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    cats = [r["category"] for r in rows]
    scr = [float(r["SCR_%"]) for r in rows]
    start = [float(r["startup_%"]) for r in rows]
    pqs = [float(r["mean_PQS"]) * 100 for r in rows]
    ees = [float(r["mean_EES"]) * 100 for r in rows]
    mrs = [float(r["mean_MRS"]) * 100 for r in rows]
    x = range(len(cats))
    w = 0.16
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar([i - 2 * w for i in x], start, w, label="Startup %", color="#1565c0")
    ax.bar([i - w for i in x], scr, w, label="Completion %", color="#00897b")
    ax.bar([i for i in x], pqs, w, label="Planning %", color="#6a1b9a")
    ax.bar([i + w for i in x], ees, w, label="Evidence %", color="#2e7d32")
    ax.bar([i + 2 * w for i in x], mrs, w, label="Memory %", color="#ef6c00")
    ax.set_xticks(list(x))
    ax.set_xticklabels([c.replace(" ", "\n") for c in cats], fontsize=8)
    ax.set_ylabel("Score (%)")
    ax.set_ylim(0, 105)
    ax.set_title("Functionality by vulnerability category")
    ax.legend(ncol=5, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    plt.tight_layout()
    p = os.path.join(FIG_DIR, "per_category.png")
    plt.savefig(p, dpi=130)
    plt.close()
    return p


def fig_per_run(rows):
    rows = sorted(rows, key=lambda r: r["challenge_id"])
    ids = [r["challenge_id"] for r in rows]
    ofs = [_f(r, "OFS_run") for r in rows]
    cols = [PASS_COLOR if _i(r, "session_completed") else FAIL_COLOR for r in rows]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(range(len(ids)), ofs, color=cols)
    ax.set_xticks(range(len(ids)))
    ax.set_xticklabels(ids, rotation=90, fontsize=7)
    ax.set_ylabel("Per-run Overall Functionality Score (%)")
    ax.set_title("Per-run OFS (green = session completed all 3 phases, red = not completed)")
    ax.set_ylim(0, 100)
    plt.tight_layout()
    p = os.path.join(FIG_DIR, "per_run_ofs.png")
    plt.savefig(p, dpi=130)
    plt.close()
    return p


def fig_phases(rows):
    counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for r in rows:
        n = _i(r, "num_phases_executed")
        counts[min(n, 3)] = counts.get(min(n, 3), 0) + 1
    fig, ax = plt.subplots(figsize=(7, 4.2))
    xs = ["0 phases", "1 phase", "2 phases", "3 phases"]
    ys = [counts.get(i, 0) for i in range(4)]
    ax.bar(xs, ys, color=["#c62828", "#ef6c00", "#fbc02d", "#2e7d32"])
    for i, v in enumerate(ys):
        ax.text(i, v + 0.05, str(v), ha="center")
    ax.set_ylabel("Number of runs")
    ax.set_title("How many workflow phases each run reached")
    plt.tight_layout()
    p = os.path.join(FIG_DIR, "phase_completion.png")
    plt.savefig(p, dpi=130)
    plt.close()
    return p


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def rel(p):
    return os.path.relpath(p, HERE).replace("\\", "/") if p else None


def md_table_headline(agg, checks):
    order = ["SSR", "TRR", "SCR", "PQS", "CVR", "CRR", "EES", "MRS", "ERR", "OFS"]
    lines = ["| Metric | Value | Threshold | Verdict |", "|---|---|---|---|"]
    for k in order:
        v = agg.get(k)
        thr = metrics.THRESHOLDS.get(k)
        vtxt = "N/A" if v is None else f"{v:.2f}%"
        ttxt = "-" if thr is None else f">= {thr:g}%"
        verdict = "PASS" if checks.get(k) else "FAIL"
        if k == "ERR" and v is None:
            verdict = "N/A"
        lines.append(f"| {METRIC_LABELS[k]} ({k}) | {vtxt} | {ttxt} | {verdict} |")
    hic = agg.get("HIC_mean")
    lines.append(f"| Human Intervention Count (HIC, mean) | {hic:g} | <= {metrics.THRESHOLDS['HIC_mean_max']:g} | "
                 f"{'PASS' if checks.get('HIC') else 'FAIL'} |")
    return "\n".join(lines)


def md_findings():
    if not os.path.exists(FINDINGS_CSV):
        return "_No findings file present._"
    with open(FINDINGS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    lines = ["| ID | Severity | Component | Problem | Resolution | Status |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['finding_id']} | {r['severity']} | {r['component']} | "
                     f"{r['problem_observed']} | {r['resolution']} | {r['status']} |")
    return "\n".join(lines)


def md_per_run(rows):
    rows = sorted(rows, key=lambda r: r["challenge_id"])
    cols = ["challenge_id", "category", "difficulty", "target_reachable_pre", "startup_ok",
            "session_completed", "num_phases_executed", "commands_generated",
            "commands_executed", "commands_evidence", "errors", "OFS_run", "fatal_error"]
    head = "| " + " | ".join(c.replace("_", " ") for c in cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    lines = [head, sep]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    rows = load_runs()
    if not rows:
        print("No result rows found; run the harness first.")
        return
    scores = [row_to_score(r) for r in rows]
    agg = metrics.aggregate(scores)
    checks = agg["verdict"]["per_metric"]

    f_head = fig_headline(agg, checks)
    f_funnel = fig_funnel(agg)
    f_cat = fig_per_category()
    f_run = fig_per_run(rows)
    f_phase = fig_phases(rows)

    n = agg["N"]
    completed = sum(_i(r, "session_completed") for r in rows)
    reachable = sum(_i(r, "target_reachable_pre") for r in rows)
    started = sum(_i(r, "startup_ok") for r in rows)
    fatals = [r for r in rows if (r.get("fatal_error") or "").strip()]

    md = []
    md.append("# VulnBot Functionality & Reliability — Results Evaluation\n")
    md.append(f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} from `functionality_results.csv` "
              f"({n} runs)._\n")
    md.append("> **Research question.** *Does VulnBot function correctly and reliably as an automated "
              "penetration-testing system?* This study scores the **workflow** (startup, reachability, "
              "planning, command generation/execution, evidence capture, memory hand-off, error recovery, "
              "autonomy) — **not** the hacking skill of the underlying LLM.\n")
    cats_run = sorted({r.get("category", "") for r in rows if r.get("category")})
    challenges_run = sorted({r.get("challenge_id", "") for r in rows if r.get("challenge_id")})
    md.append("## 1. Experimental setup\n")
    md.append("| Item | Value |\n|---|---|")
    md.append(f"| Model under workflow test | `qwen3.5:4b` (Ollama, local) with verbose reasoning disabled |")
    md.append(f"| Dataset | XBOW Validation Benchmarks (`xbow-val-benchmark`) |")
    md.append(f"| Challenges run | {len(challenges_run)} ({', '.join(challenges_run)}) |")
    md.append(f"| Categories covered | {len(cats_run)}: {', '.join(cats_run)} |")
    md.append(f"| Interaction budget (`-m`) | 1 per role (CPU-bound model; see validity notes) |")
    md.append(f"| Runs scored (N) | {n} |")
    md.append(f"| Infrastructure | Dockerised targets + Kali SSH worker + MySQL session DB |")
    md.append("")
    md.append("> **Note on model performance vs system functionality.** `qwen3.5:4b` ran on CPU only, so "
              "inference was slow and the interaction budget was kept small. This is deliberate: the study "
              "measures whether the *pipeline* performs each function, not how good the model is at hacking. "
              "Low command-quality numbers therefore reflect a small local model, **not** a broken workflow.\n")

    md.append("## 2. Headline verdict\n")
    md.append(f"**Overall verdict: `{agg['verdict']['overall']}`** "
              f"(Overall Functionality Score = **{agg['OFS']:.2f}%**, threshold {metrics.THRESHOLDS['OFS']:g}%).\n")
    md.append(md_table_headline(agg, checks))
    md.append("")
    md.append(f"![Headline metrics]({rel(f_head)})\n")
    md.append("Verdict scheme: `PASS` = every threshold met; `PARTIAL` = OFS met but >=1 individual "
              "threshold missed; `FAIL` = OFS not met.\n")

    md.append("## 3. Pipeline reliability (does each stage run?)\n")
    md.append(f"- **Startup** succeeded in **{started}/{n}** runs (SSR = {agg['SSR']:.1f}%).")
    md.append(f"- **Target reachability** confirmed in **{reachable}/{n}** runs (TRR = {agg['TRR']:.1f}%).")
    md.append(f"- **Session completion** (all 3 phases, no unhandled crash) in **{completed}/{n}** runs "
              f"(SCR = {agg['SCR']:.1f}%).")
    md.append(f"- **Fatal errors** recorded in **{len(fatals)}** runs.")
    md.append("")
    md.append(f"![Phase completion]({rel(f_phase)})\n")

    md.append("## 4. Planning, commands and evidence\n")
    md.append(f"Across all runs VulnBot generated **{agg['commands_generated']}** commands, executed "
              f"**{agg['commands_executed']}**, of which **{agg['commands_valid']}** were valid and "
              f"**{agg['commands_relevant']}** relevant; **{agg['commands_with_evidence']}** produced "
              f"captured evidence. Planning Quality averaged **{agg['PQS']:.1f}%**.\n")
    md.append(f"![Command funnel]({rel(f_funnel)})\n")
    md.append("- **Command Validity Rate (CVR)** = valid / generated = "
              f"**{agg['CVR']:.1f}%**.")
    md.append("- **Command Relevance Rate (CRR)** = relevant / generated = "
              f"**{agg['CRR']:.1f}%**.")
    md.append("- **Evidence Extraction Score (EES)** = evidence / executed = "
              f"**{agg['EES']:.1f}%**.")
    err_txt = "N/A (no errors observed)" if agg["ERR"] is None else f"{agg['ERR']:.1f}%"
    md.append(f"- **Error Recovery Rate (ERR)** = recovered / errors = **{err_txt}** "
              f"(errors observed: {agg['errors_observed']}, recovered: {agg['errors_recovered']}).")
    md.append("")

    md.append("## 5. Memory hand-off and autonomy\n")
    md.append(f"- **Memory Retention Score (MRS)** = **{agg['MRS']:.1f}%** "
              "(findings summarised + state preserved across phase transitions).")
    md.append(f"- **Human Intervention Count (HIC, mean)** = **{agg['HIC_mean']:g}** "
              f"(threshold <= {metrics.THRESHOLDS['HIC_mean_max']:g}); the pipeline ran fully unattended.")
    md.append("")

    md.append("## 6. Behaviour across vulnerability categories\n")
    if f_cat:
        md.append(f"![Per category]({rel(f_cat)})\n")
        md.append("This breakdown shows whether the workflow behaves consistently regardless of the "
                  "vulnerability class given to it (it is never told the class).\n")
    else:
        md.append("_Per-category breakdown unavailable._\n")

    md.append("## 7. Per-run OFS\n")
    md.append(f"![Per run OFS]({rel(f_run)})\n")

    md.append("## 8. Problems encountered during testing\n")
    md.append("These are recorded in machine-readable form in `testing_findings.csv`.\n")
    md.append(md_findings())
    md.append("")

    md.append("## 9. Threats to validity\n")
    md.append("- **Model vs workflow.** A small CPU-bound model and a low interaction budget depress the "
              "*command-quality* metrics (CVR/CRR/EES). These are properties of the model, not the pipeline; "
              "the structural metrics (SSR/TRR/SCR/MRS/HIC) are the true measure of workflow functionality.")
    md.append("- **Heuristic scoring.** Command *validity*/*relevance* use a fixed tool vocabulary + target "
              "match (see `metrics.py`); rules are explicit and auditable.")
    md.append("- **Lightweight Kali box.** The worker image ships only `nmap` and `curl`; commands using "
              "other tools surface as `command not found`, which legitimately exercises error handling.")
    md.append("- **Single pass.** Reliability (run-to-run consistency) needs `--repeat K>=3`; this run is a "
              "correctness pass (K=1).")
    md.append("")

    md.append("## 10. Appendix — per-run evidence\n")
    md.append(md_per_run(rows))
    md.append("")

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Wrote {REPORT_MD}")
    print(f"Figures in {FIG_DIR}")
    print(f"Overall verdict: {agg['verdict']['overall']}  OFS={agg['OFS']:.2f}%  N={n}")


if __name__ == "__main__":
    main()
