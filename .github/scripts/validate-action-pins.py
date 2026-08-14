#!/usr/bin/env python3
"""Require immutable references for external GitHub Actions."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = REPOSITORY_ROOT / ".github" / "workflows"
USES_PATTERN = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)")
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def main() -> int:
    failures: list[str] = []
    checked = 0

    workflows = sorted((*WORKFLOW_ROOT.glob("*.yml"), *WORKFLOW_ROOT.glob("*.yaml")))
    for workflow in workflows:
        for line_number, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), 1):
            match = USES_PATTERN.match(line)
            if match is None:
                continue

            reference = match.group(1)
            if reference.startswith("./"):
                continue

            checked += 1
            if reference.startswith("docker://"):
                if "@sha256:" not in reference:
                    failures.append(f"{workflow.name}:{line_number}: {reference}")
                continue

            _repository, separator, revision = reference.rpartition("@")
            if not separator or FULL_SHA_PATTERN.fullmatch(revision) is None:
                failures.append(f"{workflow.name}:{line_number}: {reference}")

    if failures:
        print("External Actions must use a full immutable commit SHA:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"Immutable external Action references checked: {checked}")
    print("GitHub Action pin audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
