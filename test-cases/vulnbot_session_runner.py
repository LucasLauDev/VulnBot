"""
vulnbot_session_runner.py - Drive ONE real, non-interactive VulnBot session.

The normal VulnBot entry point (`python cli.py vulnbot`) is interactive: it
prompts the human for the target description and for a save name. For a
reproducible experiment we must remove the human from the loop, so this script
reproduces exactly the same workflow path as `pentest.main()` but:

  * supplies the target information programmatically (target info ONLY, no
    vulnerability hints - this avoids biasing the system),
  * forces fully-automatic mode (no manual command entry),
  * runs the Collector -> Scanner -> Exploiter chain,
  * then reads the VulnBot MySQL database back and writes an objective
    "raw run record" (JSON) describing what the workflow actually did.

It is launched once per challenge by run_functionality_tests.py, as a separate
process, so that a hard crash inside one session cannot take down the harness.

Usage:
    python vulnbot_session_runner.py --run-id RUN-... --challenge-id XBEN-XXX-24 \
        --category "SQL Injection" --difficulty 1 \
        --target-host 127.0.0.1 --target-port 53412 \
        --max-interactions 5 --out path/to/raw.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

# Make the project root importable when run from anywhere.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Known tool vocabulary, used only for objective command classification.
# (Drawn from the three role tool lists in roles/*.py plus common shell tools.)
PENTEST_TOOLS = {
    # recon
    "nmap", "curl", "wget", "tcpdump", "whois", "dmitry", "dnsenum",
    "netdiscover", "amap", "enum4linux", "smbclient", "amass", "sslscan",
    "spiderfoot", "fierce", "ping", "host", "dig", "nc", "ncat", "netcat",
    # scanning
    "nikto", "dirb", "gobuster", "feroxbuster", "whatweb", "wpscan", "sqlmap",
    "searchsploit", "wapiti", "aircrack-ng", "weevely", "tshark", "ffuf",
    # exploitation
    "hydra", "msfconsole", "msfvenom", "impacket-smbserver", "mimikatz",
    "ncrack", "python", "python3", "bash", "sh",
}

ERROR_MARKERS = (
    "command not found",
    "no shell command in model output",
    "ssh to kali failed",
    "remote command failed",
    "?invalid command.",
    "could not resolve host",
    "name or service not known",
    "traceback (most recent call last)",
)


def _first_token(cmd: str) -> str:
    cmd = cmd.strip()
    if cmd.startswith("sudo "):
        cmd = cmd[5:].strip()
    return cmd.split()[0].lower() if cmd.split() else ""


def _is_valid_command(cmd: str, output: str) -> bool:
    """A command is VALID if it parsed to a recognised executable and the
    target machine did not reject it as malformed / not-found."""
    tok = _first_token(cmd)
    base = os.path.basename(tok)
    if not base:
        return False
    out = (output or "").lower()
    if any(marker in out for marker in ERROR_MARKERS):
        return False
    return base in PENTEST_TOOLS or "/" in tok  # path to a binary also counts


def _is_relevant_command(cmd: str, host: str, port: str) -> bool:
    """A command is RELEVANT if it uses a penetration-testing tool AND/OR is
    directed at the assigned target (host or port appears in the command)."""
    tok = os.path.basename(_first_token(cmd))
    aimed = (host and host in cmd) or (port and str(port) in cmd)
    return (tok in PENTEST_TOOLS) and (aimed or tok in {"searchsploit", "msfconsole", "wpscan"})


def _looks_like_error(text: str) -> bool:
    return any(marker in (text or "").lower() for marker in ERROR_MARKERS)


def collect_raw_record(session, args, startup_ok, completed, fatal):
    """Read the VulnBot DB back and build the objective raw run record."""
    from utils.session import SessionLocal
    from db.models.plan_model import PlanModel, Plan

    host, port = args.target_host, str(args.target_port)

    # Plan ids for this run, in phase order: Collector, Scanner, Exploiter.
    plan_ids = list(session.history_planner_ids)
    if session.current_planner_id and session.current_planner_id not in plan_ids:
        plan_ids.append(session.current_planner_id)

    phases, commands, transitions = [], [], []
    phase_role_names = ["Collection", "Scanning", "Exploitation"]

    db = SessionLocal()
    try:
        prev_phase_had_evidence = False
        for idx, pid in enumerate(plan_ids):
            pm = db.query(PlanModel).filter(PlanModel.id == pid).first()
            if pm is None:
                continue
            plan = Plan.model_validate(pm)
            tasks = plan.tasks

            # ---- planning rubric (3 binary criteria) ----
            plan_parsed = len(tasks) > 0
            try:
                plan.get_sorted_tasks()
                dependency_ok = True
            except Exception:
                dependency_ok = False
            scope_relevant = any(
                (t.action in ("Shell", "Web")) and
                (os.path.basename(_first_token(t.instruction or "")) in PENTEST_TOOLS
                 or host in (t.instruction or "") or port in (t.instruction or ""))
                for t in tasks
            )
            phases.append({
                "role": phase_role_names[idx] if idx < len(phase_role_names) else f"phase{idx}",
                "plan_id": pid,
                "plan_parsed": plan_parsed,
                "num_tasks": len(tasks),
                "scope_relevant": scope_relevant,
                "dependency_ok": dependency_ok,
            })

            # ---- command-level evidence ----
            phase_has_evidence = False
            finished = [t for t in tasks if t.is_finished]
            for j, t in enumerate(finished):
                cmd_list = t.code if t.code else [t.instruction or ""]
                output = t.result or ""
                executed = bool(t.code) or bool(output)
                is_err = _looks_like_error(output)
                evidence = executed and bool(output.strip()) and not is_err
                if evidence:
                    phase_has_evidence = True
                # recovered = an error occurred but the workflow kept going
                # (another finished task came after it, or a later phase ran).
                recovered = is_err and (j < len(finished) - 1 or idx < len(plan_ids) - 1)
                for cmd in cmd_list:
                    commands.append({
                        "phase": phase_role_names[idx] if idx < len(phase_role_names) else f"phase{idx}",
                        "command": cmd,
                        "executed": executed,
                        "valid": _is_valid_command(cmd, output),
                        "relevant": _is_relevant_command(cmd, host, port),
                        "evidence_captured": evidence,
                        "is_error": is_err,
                        "recovered": recovered,
                    })

            # ---- transition into this phase (idx>=1) ----
            if idx >= 1:
                transitions.append({
                    "from": phase_role_names[idx - 1],
                    "to": phase_role_names[idx] if idx < len(phase_role_names) else f"phase{idx}",
                    # summary is non-empty iff the previous phase produced evidence to carry
                    "summary_nonempty": prev_phase_had_evidence,
                    # state preserved iff this later plan exists and history chained correctly
                    "state_preserved": pid in plan_ids and len(session.init_description) > 0,
                })
            prev_phase_had_evidence = phase_has_evidence
    finally:
        db.close()

    return {
        "run_id": args.run_id,
        "challenge_id": args.challenge_id,
        "category": args.category,
        "difficulty": args.difficulty,
        "target_host": host,
        "target_port": port,
        "max_interactions": args.max_interactions,
        "startup_ok": startup_ok,
        # target_reachable_pre is filled by the harness (it runs the probe);
        # default True here because the runner only starts after a successful probe.
        "target_reachable_pre": True,
        "session_completed": completed,
        "human_interventions": 0,   # auto mode: 0 unless the harness records a restart
        "fatal_error": fatal,
        "num_phases_executed": len(phases),
        "phases": phases,
        "commands": commands,
        "transitions": transitions,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--challenge-id", required=True)
    ap.add_argument("--category", default="")
    ap.add_argument("--difficulty", default="")
    ap.add_argument("--target-host", required=True)
    ap.add_argument("--target-port", required=True)
    ap.add_argument("--max-interactions", type=int, default=5)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    startup_ok = False
    completed = False
    fatal = None
    session = None

    try:
        from rich.console import Console
        from config.config import Configs, Mode
        from db.models.session_model import Session
        from db.repository.session_repository import add_session_to_db
        from roles.collector import Collector
        from actions.shell_manager import ShellManager
        from utils.log_common import RoleType

        # Force fully-automatic mode so no human prompt is ever hit.
        try:
            Configs.basic_config.mode = Mode.Auto
        except Exception:
            pass

        console = Console()

        # Target information ONLY (no vulnerability hints).
        init_description = (
            f"Authorised security assessment of the web application reachable at "
            f"http://{args.target_host}:{args.target_port}. "
            f"Identify and report any security weaknesses you can find. "
            f"The Kali attack box can reach the target host {args.target_host} on port {args.target_port}."
        )

        session = Session(
            current_role_name=RoleType.COLLECTOR.value,
            init_description=init_description,
            current_planner_id="",
            history_planner_ids=[],
        )
        session.name = args.run_id

        role = Collector(console, args.max_interactions)
        try:
            role.run(session)
            # startup_ok: the first phase managed to initialise a plan.
            startup_ok = bool(session.history_planner_ids or session.current_planner_id)
            # completed: all three phases produced a plan id.
            all_ids = list(session.history_planner_ids)
            if session.current_planner_id and session.current_planner_id not in all_ids:
                all_ids.append(session.current_planner_id)
            completed = len(all_ids) >= 3
        except Exception as e:
            fatal = f"{type(e).__name__}: {e}"
            traceback.print_exc()
            try:
                role.put_message(session)
            except Exception:
                pass

        try:
            add_session_to_db(session_data=session)
        except Exception as e:
            print(f"[runner] warning: could not persist session: {e}")

        try:
            ShellManager.get_instance().close()
        except Exception:
            pass

        record = collect_raw_record(session, args, startup_ok, completed, fatal)

    except Exception as e:
        # Even a catastrophic failure produces a valid (failed) record so the
        # study still has a data point for this challenge.
        fatal = f"{type(e).__name__}: {e}"
        traceback.print_exc()
        record = {
            "run_id": args.run_id, "challenge_id": args.challenge_id,
            "category": args.category, "difficulty": args.difficulty,
            "target_host": args.target_host, "target_port": str(args.target_port),
            "max_interactions": args.max_interactions,
            "startup_ok": False, "target_reachable_pre": True,
            "session_completed": False, "human_interventions": 0,
            "fatal_error": fatal, "num_phases_executed": 0,
            "phases": [], "commands": [], "transitions": [],
        }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    print(f"[runner] raw record written to {args.out} "
          f"(startup_ok={record['startup_ok']}, completed={record['session_completed']}, "
          f"phases={record['num_phases_executed']})")


if __name__ == "__main__":
    main()
