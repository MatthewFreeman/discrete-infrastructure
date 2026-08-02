#!/usr/bin/env python3
"""Summarize the Ubuntu-vs-Debian smaps diagnostic pair."""

from __future__ import annotations

import csv
import json
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[2]
RAW_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "raw" / "diagnostic-smaps"
OUT_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "analysis"
LABELS = ("idle-start", "idle-mid", "idle-end")
FIELDS = (
    "Rss", "Pss", "Pss_Anon", "Pss_File", "Pss_Shmem", "Shared_Clean",
    "Shared_Dirty", "Private_Clean", "Private_Dirty", "Referenced", "Anonymous",
    "KSM", "LazyFree", "AnonHugePages", "ShmemPmdMapped", "FilePmdMapped",
    "Shared_Hugetlb", "Private_Hugetlb", "Swap", "SwapPss", "Locked",
)


def parse_smaps(path: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        if key in FIELDS:
            values[key] = int(rest.split()[0])
    missing = (set(FIELDS) - {"KSM"}) - set(values)
    if missing:
        raise RuntimeError(f"missing smaps fields in {path}: {sorted(missing)}")
    return values


def main() -> None:
    rows: list[dict[str, str | int]] = []
    for os_name in ("ubuntu", "debian"):
        for label in LABELS:
            values = parse_smaps(RAW_ROOT / os_name / f"{label}-smaps-rollup.txt")
            epoch = int((RAW_ROOT / os_name / f"{label}-memory-epoch-ns.txt").read_text(encoding="utf-8").strip())
            rows.append({"os": os_name, "label": label, "epoch_ns": epoch, **{f"{key}_kb": values.get(key, "") for key in FIELDS}})

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_ROOT / "smaps-diagnostic.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    lookup = {(str(row["os"]), str(row["label"])): row for row in rows}
    comparisons = {}
    for label in LABELS:
        ubuntu = lookup[("ubuntu", label)]
        debian = lookup[("debian", label)]
        comparisons[label] = {
            "rss_diff_debian_minus_ubuntu_kb": int(debian["Rss_kb"]) - int(ubuntu["Rss_kb"]),
            "anonymous_diff_debian_minus_ubuntu_kb": int(debian["Anonymous_kb"]) - int(ubuntu["Anonymous_kb"]),
            "anon_huge_pages_ubuntu_kb": int(ubuntu["AnonHugePages_kb"]),
            "anon_huge_pages_debian_kb": int(debian["AnonHugePages_kb"]),
            "pss_file_diff_debian_minus_ubuntu_kb": int(debian["Pss_File_kb"]) - int(ubuntu["Pss_File_kb"]),
        }
    json_path = OUT_ROOT / "smaps-diagnostic.json"
    json_path.write_text(json.dumps(comparisons, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")
    for label in LABELS:
        item = comparisons[label]
        print(
            f"{label}: RSS D-U={item['rss_diff_debian_minus_ubuntu_kb']} kB; "
            f"Anonymous D-U={item['anonymous_diff_debian_minus_ubuntu_kb']} kB; "
            f"AnonHugePages U={item['anon_huge_pages_ubuntu_kb']} kB "
            f"D={item['anon_huge_pages_debian_kb']} kB; "
            f"Pss_File D-U={item['pss_file_diff_debian_minus_ubuntu_kb']} kB"
        )


if __name__ == "__main__":
    main()
