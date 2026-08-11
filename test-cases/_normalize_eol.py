"""One-off helper: normalise CRLF -> LF for container-executed scripts in the
20 dataset challenges. Only touches files that begin with a shebang (#!) and
actually contain CRLF, so dataset *content* is unchanged (line endings only).

This is required because the benchmark submodule was checked out on Windows
with autocrlf, leaving shell entrypoints with \r\n which breaks the Linux
shebang ("exec ...: no such file or directory").
"""
import os

BASE = os.path.join(os.path.dirname(__file__), "..",
                    "benchmark", "xbow-val-benchmark", "benchmarks")
IDS = ["XBEN-039-24", "XBEN-071-24", "XBEN-078-24", "XBEN-083-24",
       "XBEN-004-24", "XBEN-008-24", "XBEN-010-24", "XBEN-011-24",
       "XBEN-001-24", "XBEN-002-24", "XBEN-003-24", "XBEN-005-24",
       "XBEN-009-24", "XBEN-022-24", "XBEN-023-24", "XBEN-025-24",
       "XBEN-031-24", "XBEN-035-24", "XBEN-037-24", "XBEN-045-24"]

changed = []
for cid in IDS:
    root = os.path.join(BASE, cid)
    for dirpath, _, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                with open(path, "rb") as f:
                    head = f.read(2)
                    if head != b"#!":
                        continue
                    f.seek(0)
                    data = f.read()
            except (OSError, ValueError):
                continue
            if b"\r\n" not in data:
                continue
            with open(path, "wb") as f:
                f.write(data.replace(b"\r\n", b"\n"))
            changed.append(os.path.relpath(path, BASE))

print(f"Normalised {len(changed)} shebang script(s):")
for c in changed:
    print("  ", c)
