#!/usr/bin/env python3
"""Validate repository-local Markdown links without network access."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
REMOTE_SCHEMES = ("http://", "https://", "mailto:", "tel:", "data:")


def strip_fenced_code(text: str) -> str:
    lines: list[str] = []
    fence: str | None = None

    for line in text.splitlines():
        stripped = line.lstrip()
        marker = stripped[:3]
        if marker in {"```", "~~~"}:
            fence = None if fence == marker else marker
            continue
        if fence is None:
            lines.append(line)

    return "\n".join(lines)


def normalized_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    return unquote(target.split("#", maxsplit=1)[0])


def main() -> int:
    failures: list[str] = []
    checked = 0

    for markdown in sorted(REPOSITORY_ROOT.rglob("*.md")):
        if ".git" in markdown.parts:
            continue

        text = strip_fenced_code(markdown.read_text(encoding="utf-8"))
        for match in LINK_PATTERN.finditer(text):
            target = normalized_target(match.group(1))
            if not target or target.startswith("#") or target.startswith(REMOTE_SCHEMES):
                continue

            checked += 1
            resolved = (markdown.parent / target).resolve()
            try:
                resolved.relative_to(REPOSITORY_ROOT)
            except ValueError:
                failures.append(f"{markdown.relative_to(REPOSITORY_ROOT)} -> {target} (outside repository)")
                continue

            if not resolved.exists():
                failures.append(f"{markdown.relative_to(REPOSITORY_ROOT)} -> {target}")

    if failures:
        print("Broken repository-local Markdown links:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"Repository-local Markdown links checked: {checked}")
    print("Broken internal links: 0")
    print("Markdown link audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
