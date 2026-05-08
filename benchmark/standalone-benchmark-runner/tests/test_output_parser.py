"""Smoke tests for the output parser and benchmark loader."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from src.benchmark_loader import (  # noqa: E402
    auto_detect_all_benchmarks_dirs,
    detect_kind,
)
from src.output_parser import OutputParser  # noqa: E402


class OutputParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = OutputParser()

    def test_extracts_lowercase_flag(self) -> None:
        text = "We obtained flag{abc-123-uuid}"
        self.assertEqual(
            self.parser.extract_flags(text),
            ["flag{abc-123-uuid}"],
        )

    def test_extracts_uppercase_flag(self) -> None:
        text = "FLAG{This_Is_Long_Enough_With_32_Chars_xx}"
        flags = self.parser.extract_flags(text)
        self.assertIn("FLAG{This_Is_Long_Enough_With_32_Chars_xx}", flags)

    def test_strict_pattern_accepts_uuid_flag(self) -> None:
        flag = "flag{85c0d827-5e28-4577-be2b-319bdcbf872d}"
        self.assertTrue(self.parser.validate_strict_pattern(flag))

    def test_strict_pattern_rejects_short_flag(self) -> None:
        self.assertFalse(self.parser.validate_strict_pattern("flag{abc123}"))
        self.assertFalse(self.parser.validate_strict_pattern("private{self}"))

    def test_parse_full_output(self) -> None:
        lines = [
            "[BENCH-START] Collection",
            "[INFO] running nmap...",
            "uid=0(root) gid=0(root)",
            "[BENCH-DONE]",
        ]
        parsed = self.parser.parse_output(lines)
        self.assertTrue(parsed["has_done"])
        self.assertFalse(parsed["has_error"])
        self.assertIn("uid=", parsed["keyword_hits"])

    def test_parse_detects_traceback(self) -> None:
        lines = [
            "Traceback (most recent call last):",
            '  File "x.py", line 1, in <module>',
            "ValueError: bad input",
        ]
        parsed = self.parser.parse_output(lines)
        self.assertTrue(parsed["has_error"])
        self.assertIsNotNone(parsed["error_msg"])


class BenchmarkLoaderScopingTests(unittest.TestCase):
    """``auto_detect_all_benchmarks_dirs`` must scope to the VulnBot project root.

    A previous bug climbed the filesystem until it found *any* directory
    named ``vulhub/selected-benchmark/`` — including unrelated checkouts
    on the user's machine. The scoping logic should ignore those and only
    detect datasets under the enclosing project root (a directory
    containing both ``cli.py`` and ``pentest.py``).
    """

    def test_scopes_to_project_root_and_ignores_outside_clones(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root).resolve()

            project = root / "VulnBot"
            project.mkdir()
            (project / "cli.py").write_text("# sentinel\n", encoding="utf-8")
            (project / "pentest.py").write_text("# sentinel\n", encoding="utf-8")

            xbow = (project / "benchmark" / "xbow-val-benchmark"
                    / "selected-benchmarks" / "XBEN-001-24")
            xbow.mkdir(parents=True)
            (xbow / "benchmark.json").write_text(
                json.dumps({"name": "stub", "level": 1, "tags": []}),
                encoding="utf-8",
            )
            (xbow / ".env").write_text("FLAG=flag{x}\n", encoding="utf-8")

            outside_app = root / "vulhub" / "selected-benchmark" / "stuffapp" / "CVE-X"
            outside_app.mkdir(parents=True)
            (outside_app / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

            inner = project / "benchmark" / "standalone-benchmark-runner" / "src"
            inner.mkdir(parents=True)

            detected = auto_detect_all_benchmarks_dirs(start=inner)
            paths = [p for p, _ in detected]

            self.assertEqual(len(detected), 1, f"unexpected detections: {paths}")
            self.assertEqual(detected[0][1], "xbow")
            self.assertNotIn(outside_app.parent.parent.resolve(), paths)


if __name__ == "__main__":
    unittest.main()
