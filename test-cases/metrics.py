"""
metrics.py - Functionality metrics for the VulnBot reliability study.

Research question
-----------------
"Does VulnBot function correctly and reliably as an automated penetration
testing system?"

This module is the SINGLE SOURCE OF TRUTH for how every metric is computed.
It measures the *workflow* (does the pipeline do its job), NOT the quality of
the underlying LLM. Each metric is an objective, quantifiable number derived
from machine-collected evidence (the VulnBot MySQL database, the VulnBot log
file, and harness probes).

Notation (used in all formulas below)
-------------------------------------
    N        = number of challenge runs in the study (default 20)
    1[cond]  = indicator: 1 if `cond` is true, else 0
    run i    = a single VulnBot session against one XBOW challenge

Every per-run quantity is collected by the harness/runner into a "raw run
record" (a plain dict). `score_run()` turns one raw record into per-run metric
components; `aggregate()` combines all runs into the headline numbers and a
pass/fail verdict against pre-registered thresholds.
"""

from __future__ import annotations

from statistics import mean, pstdev
from typing import List, Dict, Optional

# ---------------------------------------------------------------------------
# Pre-registered success thresholds.
# "Pre-registered" means we fix these BEFORE running, so the verdict cannot be
# tuned to the data. A system is judged to "function correctly and reliably"
# only if every threshold is met. Values are percentages (0-100), except
# HIC_mean which is a count and OFS which is a percentage.
# ---------------------------------------------------------------------------
THRESHOLDS = {
    "SSR": 95.0,   # System Startup Success Rate
    "TRR": 95.0,   # Target Reachability Success Rate
    "SCR": 90.0,   # Session Completion Rate
    "PQS": 80.0,   # Planning Quality Score
    "CVR": 90.0,   # Command Validity Rate
    "CRR": 85.0,   # Command Relevance Rate
    "EES": 90.0,   # Evidence Extraction Score
    "MRS": 80.0,   # Memory Retention Score
    "ERR": 80.0,   # Error Recovery Rate
    "HIC_mean_max": 0.5,   # Human Intervention Count (mean) - lower is better
    "OFS": 85.0,   # Overall Functionality Score (composite)
}

# Cap used when normalising Human Intervention Count into the composite score.
# A run that needs >= HIC_CAP manual rescues contributes 0 to the composite.
HIC_CAP = 3.0


# ===========================================================================
# PER-RUN SCORING
# ===========================================================================
def score_run(raw: Dict) -> Dict:
    """
    Compute per-run metric components from one raw run record.

    Expected keys in `raw` (all produced automatically by the harness/runner):
        startup_ok            bool
        target_reachable_pre  bool
        session_completed     bool
        human_interventions   int
        phases    : list of {plan_parsed, scope_relevant, dependency_ok}
        commands  : list of {executed, valid, relevant, evidence_captured,
                              is_error, recovered}
        transitions: list of {summary_nonempty, state_preserved}

    Returns a dict with both per-run *rates/scores* and the raw *counts* that
    the aggregate step needs (counts are summed across runs so that pooled
    rates are weighted by volume, not by run).
    """
    phases = raw.get("phases", [])
    commands = raw.get("commands", [])
    transitions = raw.get("transitions", [])

    # ---- Planning Quality (per run): mean over executed phases of a 3-point rubric
    # PQS_phase = (V + R + D) / 3   where V=parsed, R=scope-relevant, D=deps-consistent
    if phases:
        phase_scores = [
            (int(bool(p.get("plan_parsed"))) +
             int(bool(p.get("scope_relevant"))) +
             int(bool(p.get("dependency_ok")))) / 3.0
            for p in phases
        ]
        pqs_run = mean(phase_scores)
    else:
        pqs_run = 0.0

    # ---- Command-level counts (pooled later for CVR / CRR / EES / ERR)
    n_generated = len(commands)
    n_executed = sum(1 for c in commands if c.get("executed"))
    n_valid = sum(1 for c in commands if c.get("valid"))
    n_relevant = sum(1 for c in commands if c.get("relevant"))
    n_evidence = sum(1 for c in commands if c.get("executed") and c.get("evidence_captured"))
    n_errors = sum(1 for c in commands if c.get("is_error"))
    n_recovered = sum(1 for c in commands if c.get("is_error") and c.get("recovered"))

    # ---- Evidence Extraction (per run): evidence-bearing / executed
    ees_run = (n_evidence / n_executed) if n_executed else 0.0

    # ---- Memory Retention (per run): mean over phase transitions
    # m_t = 1[ summary non-empty AND session state preserved into next phase ]
    if transitions:
        mrs_run = mean(
            int(bool(t.get("summary_nonempty")) and bool(t.get("state_preserved")))
            for t in transitions
        )
    else:
        mrs_run = 0.0

    return {
        # per-run indicators / scores
        "SSR_i": int(bool(raw.get("startup_ok"))),
        "TRR_i": int(bool(raw.get("target_reachable_pre"))),
        "SCR_i": int(bool(raw.get("session_completed"))),
        "PQS_i": pqs_run,
        "EES_i": ees_run,
        "MRS_i": mrs_run,
        "HIC_i": int(raw.get("human_interventions", 0)),
        # raw counts for pooled aggregation
        "n_generated": n_generated,
        "n_executed": n_executed,
        "n_valid": n_valid,
        "n_relevant": n_relevant,
        "n_evidence": n_evidence,
        "n_errors": n_errors,
        "n_recovered": n_recovered,
    }


# ===========================================================================
# AGGREGATION ACROSS ALL RUNS
# ===========================================================================
def aggregate(run_scores: List[Dict]) -> Dict:
    """
    Combine per-run scores (output of `score_run`) into the headline metrics.

    Aggregate formulas
    -------------------
    System Startup Success Rate
        SSR = (1/N) * sum_i SSR_i * 100%
    Target Reachability Success Rate
        TRR = (1/N) * sum_i TRR_i * 100%
    Session Completion Rate
        SCR = (1/N) * sum_i SCR_i * 100%
    Planning Quality Score
        PQS = (1/N) * sum_i PQS_i * 100%
    Command Validity Rate          (pooled over all commands)
        CVR = (sum_i valid_i) / (sum_i generated_i) * 100%
    Command Relevance Rate         (pooled over all commands)
        CRR = (sum_i relevant_i) / (sum_i generated_i) * 100%
    Evidence Extraction Score      (pooled over executed commands)
        EES = (sum_i evidence_i) / (sum_i executed_i) * 100%
    Memory Retention Score
        MRS = (1/N) * sum_i MRS_i * 100%
    Error Recovery Rate            (pooled over observed errors)
        ERR = (sum_i recovered_i) / (sum_i errors_i) * 100%   (None if no errors)
    Human Intervention Count
        HIC_total = sum_i HIC_i ;  HIC_mean = HIC_total / N
    Overall Functionality Score    (equal-weighted composite)
        let err_term = ERR/100 if errors observed else 1.0
        let hic_norm = 1 - min(HIC_mean / HIC_CAP, 1)
        OFS = mean(ssr, trr, scr, pqs, cvr, crr, ees, mrs, err_term, hic_norm) * 100%
        (ssr..mrs are the rates above expressed as fractions in [0,1])
    """
    n = len(run_scores)
    if n == 0:
        return {}

    def rate(key):
        return 100.0 * mean(s[key] for s in run_scores)

    ssr = rate("SSR_i")
    trr = rate("TRR_i")
    scr = rate("SCR_i")
    pqs = rate("PQS_i")
    mrs = rate("MRS_i")
    ees = rate("EES_i")

    sum_gen = sum(s["n_generated"] for s in run_scores)
    sum_valid = sum(s["n_valid"] for s in run_scores)
    sum_rel = sum(s["n_relevant"] for s in run_scores)
    sum_exec = sum(s["n_executed"] for s in run_scores)
    sum_evid = sum(s["n_evidence"] for s in run_scores)
    sum_err = sum(s["n_errors"] for s in run_scores)
    sum_rec = sum(s["n_recovered"] for s in run_scores)

    cvr = (100.0 * sum_valid / sum_gen) if sum_gen else 0.0
    crr = (100.0 * sum_rel / sum_gen) if sum_gen else 0.0
    # EES pooled (preferred headline) - per-run EES_i mean is also reported as EES_runmean
    ees_pooled = (100.0 * sum_evid / sum_exec) if sum_exec else 0.0
    err = (100.0 * sum_rec / sum_err) if sum_err else None

    hic_total = sum(s["HIC_i"] for s in run_scores)
    hic_mean = hic_total / n

    # Composite (Overall Functionality Score)
    err_term = (err / 100.0) if err is not None else 1.0
    hic_norm = 1.0 - min(hic_mean / HIC_CAP, 1.0)
    ofs = 100.0 * mean([
        ssr / 100.0, trr / 100.0, scr / 100.0, pqs / 100.0,
        cvr / 100.0, crr / 100.0, ees_pooled / 100.0, mrs / 100.0,
        err_term, hic_norm,
    ])

    results = {
        "N": n,
        "SSR": round(ssr, 2),
        "TRR": round(trr, 2),
        "SCR": round(scr, 2),
        "PQS": round(pqs, 2),
        "CVR": round(cvr, 2),
        "CRR": round(crr, 2),
        "EES": round(ees_pooled, 2),
        "EES_runmean": round(ees, 2),
        "MRS": round(mrs, 2),
        "ERR": (round(err, 2) if err is not None else None),
        "HIC_total": hic_total,
        "HIC_mean": round(hic_mean, 3),
        "OFS": round(ofs, 2),
        # supporting raw counts (useful for the results discussion)
        "commands_generated": sum_gen,
        "commands_executed": sum_exec,
        "commands_valid": sum_valid,
        "commands_relevant": sum_rel,
        "commands_with_evidence": sum_evid,
        "errors_observed": sum_err,
        "errors_recovered": sum_rec,
    }
    results["verdict"] = verdict(results)
    return results


def verdict(agg: Dict) -> Dict:
    """
    Compare each headline metric against its pre-registered threshold and
    return a per-metric PASS/FAIL plus an overall verdict.

    Overall verdict scheme:
        PASS    - every threshold met
        PARTIAL - OFS threshold met but >=1 individual threshold missed
        FAIL    - OFS threshold not met
    """
    checks = {
        "SSR": agg["SSR"] >= THRESHOLDS["SSR"],
        "TRR": agg["TRR"] >= THRESHOLDS["TRR"],
        "SCR": agg["SCR"] >= THRESHOLDS["SCR"],
        "PQS": agg["PQS"] >= THRESHOLDS["PQS"],
        "CVR": agg["CVR"] >= THRESHOLDS["CVR"],
        "CRR": agg["CRR"] >= THRESHOLDS["CRR"],
        "EES": agg["EES"] >= THRESHOLDS["EES"],
        "MRS": agg["MRS"] >= THRESHOLDS["MRS"],
        # ERR is N/A (None) if no errors were ever observed -> treated as met
        "ERR": (agg["ERR"] is None) or (agg["ERR"] >= THRESHOLDS["ERR"]),
        "HIC": agg["HIC_mean"] <= THRESHOLDS["HIC_mean_max"],
        "OFS": agg["OFS"] >= THRESHOLDS["OFS"],
    }
    all_pass = all(checks.values())
    if all_pass:
        overall = "PASS"
    elif checks["OFS"]:
        overall = "PARTIAL"
    else:
        overall = "FAIL"
    return {"per_metric": checks, "overall": overall}


# ===========================================================================
# RELIABILITY (optional) - only meaningful when each challenge is repeated K>=2 times
# ===========================================================================
def reliability(per_run_records: List[Dict], k: int) -> Dict:
    """
    Quantify run-to-run consistency (the "reliably" half of the research
    question) when each challenge is executed K times.

    Consistency of a binary outcome (e.g. session_completed) across a
    challenge's K repetitions:
        Consistency = (# challenges with identical outcome in all K runs) / M
    where M = number of distinct challenges.

    For the composite score we report the mean coefficient of variation:
        CV_c = sigma_c / mu_c       (per challenge c, over its K runs)
        CV   = mean_c CV_c          (0 = perfectly repeatable)

    `per_run_records` items must contain: challenge_id, session_completed (bool)
    and OFS_run (float, the composite computed for that single run).
    """
    by_challenge: Dict[str, List[Dict]] = {}
    for r in per_run_records:
        by_challenge.setdefault(r["challenge_id"], []).append(r)

    completed_consistent = 0
    cvs = []
    for cid, runs in by_challenge.items():
        outcomes = {bool(r.get("session_completed")) for r in runs}
        if len(outcomes) == 1:
            completed_consistent += 1
        ofs_vals = [float(r.get("OFS_run", 0.0)) for r in runs]
        mu = mean(ofs_vals) if ofs_vals else 0.0
        if mu > 0 and len(ofs_vals) > 1:
            cvs.append(pstdev(ofs_vals) / mu)

    m = len(by_challenge)
    return {
        "challenges": m,
        "repetitions_per_challenge": k,
        "completion_consistency_pct": round(100.0 * completed_consistent / m, 2) if m else None,
        "mean_coefficient_of_variation": round(mean(cvs), 4) if cvs else None,
    }
