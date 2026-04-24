"""Auto-resolve git conflict markers in app.py by combining both sides.

Usage:
    python scripts/resolve_app_conflict.py [path]

Default path is ./app.py.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _dedupe_preserve(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = line.rstrip("\n")
        if key in seen:
            continue
        seen.add(key)
        output.append(line)
    return output


def resolve_conflicts(text: str) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    conflicts = 0

    while i < len(lines):
        line = lines[i]
        if not line.startswith("<<<<<<< "):
            out.append(line)
            i += 1
            continue

        conflicts += 1
        i += 1
        ours: list[str] = []
        theirs: list[str] = []

        while i < len(lines) and not lines[i].startswith("======="):
            ours.append(lines[i])
            i += 1
        if i < len(lines) and lines[i].startswith("======="):
            i += 1

        while i < len(lines) and not lines[i].startswith(">>>>>>> "):
            theirs.append(lines[i])
            i += 1
        if i < len(lines) and lines[i].startswith(">>>>>>> "):
            i += 1

        merged = _dedupe_preserve(ours + theirs)
        out.extend(merged)

    return "".join(out), conflicts


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "app.py")
    if not target.exists():
        print(f"error: file not found: {target}")
        return 1

    text = target.read_text(encoding="utf-8")
    if "<<<<<<< " not in text:
        print(f"No conflict markers found in {target}.")
        return 0

    resolved, count = resolve_conflicts(text)
    target.write_text(resolved, encoding="utf-8")
    print(f"Resolved {count} conflict block(s) in {target}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
