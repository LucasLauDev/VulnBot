"""State persistence for resumable VulnBot benchmark runs."""

from __future__ import annotations

import json
from pathlib import Path


class StateManager:
    """Track which benchmark IDs already completed (success/failure)."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.completed: set[str] = set()
        self.failed: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            self.completed = set(data.get("completed", []))
            self.failed = set(data.get("failed", []))
            print(
                f"Loaded state: {len(self.completed)} completed, "
                f"{len(self.failed)} failed",
                flush=True,
            )
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: failed to load state file ({e}); starting fresh.", flush=True)

    def save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(
                    {"completed": sorted(self.completed), "failed": sorted(self.failed)},
                    indent=2,
                ),
                encoding="utf-8",
            )
            tmp.replace(self.state_file)
        except OSError as e:
            print(f"Warning: failed to save state file: {e}", flush=True)

    def mark_completed(self, benchmark_id: str, success: bool) -> None:
        if success:
            self.completed.add(benchmark_id)
            self.failed.discard(benchmark_id)
        else:
            self.failed.add(benchmark_id)
        self.save()

    def is_completed(self, benchmark_id: str) -> bool:
        return benchmark_id in self.completed

    def get_remaining(self, all_ids: list[str]) -> list[str]:
        return [b for b in all_ids if b not in self.completed]

    def clear(self) -> None:
        self.completed.clear()
        self.failed.clear()
        if self.state_file.exists():
            try:
                self.state_file.unlink()
            except OSError:
                pass
