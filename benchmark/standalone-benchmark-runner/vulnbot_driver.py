"""Non-interactive driver for VulnBot.

VulnBot's regular ``python cli.py vulnbot`` entry-point uses
``prompt_toolkit.confirm`` / ``prompt`` to get the task description and
session-save name from a TTY. The benchmark runner cannot reasonably feed
those prompts via stdin in a portable way (prompt_toolkit detects pipes),
so we drive the agent in-process instead.

This script imports VulnBot's ``Role`` machinery directly and runs
``Collector → Scanner → Exploiter`` against a description supplied via
``--description`` / ``--description-file``. It emits two structured markers
to stdout that the runner picks up:

* ``[BENCH-START]`` once initialisation finished,
* ``[BENCH-DONE]`` once the run wrapped up cleanly,
* ``[BENCH-EXCEPTION] <repr>`` if the in-flight role raised.

The script is intentionally launched from the VulnBot project root (the
runner uses ``cwd=project_root``) so VulnBot's own relative imports work
unchanged.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from pathlib import Path


def _bootstrap_path() -> Path:
    """Locate the VulnBot project root and put it on ``sys.path``."""
    env_root = os.environ.get("VULNBOT_ROOT")
    if env_root:
        root = Path(env_root).resolve()
    else:
        root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def _emit(tag: str, payload: str = "") -> None:
    if payload:
        print(f"[{tag}] {payload}", flush=True)
    else:
        print(f"[{tag}]", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-interactive VulnBot driver")
    parser.add_argument("--description", default=None,
                        help="Penetration testing task description.")
    parser.add_argument("--description-file", default=None,
                        help="File containing the description (UTF-8).")
    parser.add_argument("--max-interactions", type=int, default=10,
                        help="Maximum react iterations per role (passed to Role).")
    parser.add_argument("--save-name", default="",
                        help="Optional session save name; default is timestamped.")
    parser.add_argument("--no-save", action="store_true",
                        help="Skip persisting the session to the DB.")
    args = parser.parse_args()

    if args.description_file:
        description = Path(args.description_file).read_text(encoding="utf-8").strip()
    elif args.description:
        description = args.description.strip()
    else:
        print("Error: either --description or --description-file is required.",
              file=sys.stderr, flush=True)
        return 2

    if not description:
        print("Error: empty description.", file=sys.stderr, flush=True)
        return 2

    root = _bootstrap_path()
    _emit("BENCH-INFO", f"VulnBot root: {root}")
    _emit("BENCH-INFO", f"max_interactions={args.max_interactions}")
    _emit("BENCH-INFO", f"description={description[:200]}")

    try:
        from rich.console import Console

        from actions.shell_manager import ShellManager
        from db.models.session_model import Session
        from db.repository.session_repository import add_session_to_db
        from roles.collector import Collector
        from roles.exploiter import Exploiter
        from roles.scanner import Scanner
        from utils.log_common import RoleType
    except Exception as e:
        _emit("BENCH-EXCEPTION", f"Failed to import VulnBot modules: {e!r}")
        traceback.print_exc()
        return 3

    console = Console(force_terminal=False, soft_wrap=True)

    session = Session(
        current_role_name=RoleType.COLLECTOR.value,
        init_description=description,
        current_planner_id="",
        history_planner_ids=[],
    )

    role_map = {
        RoleType.COLLECTOR.value: Collector,
        RoleType.SCANNER.value: Scanner,
        RoleType.EXPLOITER.value: Exploiter,
    }

    _emit("BENCH-START", session.current_role_name)

    rc = 0
    role = None
    try:
        try:
            cls = role_map[session.current_role_name]
            role = cls(console=console, max_interactions=args.max_interactions)
            role.run(session)
        except Exception as e:
            _emit("BENCH-EXCEPTION", f"{type(e).__name__}: {e}")
            traceback.print_exc()
            rc = 4
            if role is not None:
                try:
                    role.put_message(session)
                except Exception as cleanup_err:
                    _emit("BENCH-WARN", f"cleanup failed: {cleanup_err!r}")

        if not args.no_save:
            session.name = args.save_name or f"benchmark_{int(time.time())}"
            try:
                add_session_to_db(session_data=session)
                _emit("BENCH-INFO", f"saved session as {session.name}")
            except Exception as e:
                _emit("BENCH-WARN", f"save_session failed: {e!r}")

    finally:
        try:
            ShellManager.get_instance().close()
        except Exception as e:
            _emit("BENCH-WARN", f"ShellManager.close failed: {e!r}")

    _emit("BENCH-DONE")
    return rc


if __name__ == "__main__":
    sys.exit(main())
