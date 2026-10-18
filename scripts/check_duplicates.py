#!/usr/bin/env python3
"""Internal duplicate-code check for this repository.

    python scripts/check_duplicates.py [--window 8]

Slides a window of N significant source lines (blank lines, comments, lone brackets and import lines are
ignored; whitespace is normalised) over every .py / .js / .jsx / .css / .sh file and reports any window that
appears more than once. Exit code 1 if any repeated window is found, so it can be used in CI.

This finds copy-pasted blocks INSIDE the project. It does not compare against code elsewhere.
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTS = {".py", ".js", ".jsx", ".css", ".sh"}
SKIP_DIRS = {"node_modules", "dist", "__pycache__", ".pytest_cache", "fixtures", ".git"}
_BRACKETS_ONLY = re.compile(r"[\)\]\}\(\[\{,;]+")
_IMPORT = re.compile(r"^(import |from \S+ import |export \{)")


def significant(line: str) -> str | None:
    s = line.strip()
    if not s or s.startswith(("#", "//", "/*", "*", '"""', "'''")):
        return None
    if _BRACKETS_ONLY.fullmatch(s) or _IMPORT.match(s):
        return None
    return re.sub(r"\s+", " ", s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=8, help="repeated block size in significant lines")
    args = ap.parse_args()

    files = [p for p in ROOT.rglob("*") if p.suffix in EXTS and not (set(p.parts) & SKIP_DIRS)]
    seen: dict[str, list[tuple[str, int]]] = collections.defaultdict(list)
    total = 0
    for path in files:
        lines = [(i, s) for i, raw in enumerate(path.read_text(errors="ignore").splitlines(), 1)
                 if (s := significant(raw))]
        total += len(lines)
        for k in range(len(lines) - args.window + 1):
            block = "\n".join(s for _, s in lines[k:k + args.window])
            seen[block].append((str(path.relative_to(ROOT)), lines[k][0]))

    repeated = {b: where for b, where in seen.items() if len(where) > 1}
    print(f"files scanned: {len(files)} | significant lines: {total} | window: {args.window} lines")
    print(f"repeated blocks: {len(repeated)}")
    pairs = collections.Counter(tuple(sorted({f for f, _ in where})) for where in repeated.values())
    for files_hit, n in pairs.most_common(15):
        print(f"  {n:>3}  {' <-> '.join(files_hit)}")
    return 1 if repeated else 0


if __name__ == "__main__":
    sys.exit(main())
