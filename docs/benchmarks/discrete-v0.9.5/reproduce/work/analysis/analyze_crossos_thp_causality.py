#!/usr/bin/env python3
"""Compare the pair08 OS-default THP diagnostic with pair09 madvise."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
RAW_08 = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "raw" / "diagnostic-smaps"
RAW_09 = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "raw" / "diagnostic-smaps-thp-madvise"
OUT_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "analysis"
EXPECTED_BINARY_SHA256 = "6296755aad63d66f80150383a2a30a15876f766fa05d68733653f0c1063ae30e"
LABELS = ("idle-start", "idle-mid", "idle-end")
METRICS = ("Rss", "Anonymous", "AnonHugePages", "Pss_File")
RUNS = (
    {
        "pair": "08",
        "os": "ubuntu",
        "thp_policy": "madvise",
        "thp_recorded_in_raw": False,
        "path": RAW_08 / "ubuntu",
    },
    {
        "pair": "08",
        "os": "debian",
        "thp_policy": "always",
        "thp_recorded_in_raw": False,
        "path": RAW_08 / "debian",
    },
    {
        "pair": "09",
        "os": "ubuntu",
        "thp_policy": "madvise",
        "thp_recorded_in_raw": True,
        "path": RAW_09 / "crossos-warm-09-ubuntu24.04",
    },
    {
        "pair": "09",
        "os": "debian",
        "thp_policy": "madvise",
        "thp_recorded_in_raw": True,
        "path": RAW_09 / "crossos-warm-09-debian12",
    },
)


def parse_key_values(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def parse_smaps(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key in METRICS:
            result[key] = int(value.split()[0])
    missing = set(METRICS) - set(result)
    if missing:
        raise RuntimeError(f"missing smaps fields in {path}: {sorted(missing)}")
    return result


def selected_thp_policy(host_pre_run: str) -> str | None:
    match = re.search(
        r"^/sys/kernel/mm/transparent_hugepage/enabled=(.+)$",
        host_pre_run,
        flags=re.MULTILINE,
    )
    if not match:
        return None
    selected = re.search(r"\[([^]]+)\]", match.group(1))
    return selected.group(1) if selected else None


def validate_run(run: dict[str, Any]) -> dict[str, str]:
    path = Path(run["path"])
    summary = parse_key_values(path / "run-summary.txt")
    required = {
        "idle_start_height",
        "idle_end_height",
        "idle_start_hash",
        "idle_end_hash",
        "outgoing_at_idle_start",
        "incoming_at_idle_start",
        "stop_rc",
        "fatal_pattern_matches",
    }
    missing = required - set(summary)
    if missing:
        raise RuntimeError(f"missing summary fields in {path}: {sorted(missing)}")
    if summary["incoming_at_idle_start"] != "0":
        raise RuntimeError(f"unexpected inbound peers in {path}")
    if summary["stop_rc"] != "0" or summary["fatal_pattern_matches"] != "0":
        raise RuntimeError(f"failed stop or fatal pattern in {path}")

    snapshot_lines = set((path / "snapshot-verification.txt").read_text(encoding="utf-8").splitlines())
    expected_snapshot_lines = {
        "p2pstate.bin: OK",
        "poolstate.bin: OK",
        "blockchain.lmdb/data.mdb: OK",
    }
    if snapshot_lines != expected_snapshot_lines:
        raise RuntimeError(f"snapshot verification mismatch in {path}")

    host_pre_run = (path / "host-pre-run.txt").read_text(encoding="utf-8")
    if EXPECTED_BINARY_SHA256 not in host_pre_run:
        raise RuntimeError(f"binary SHA256 mismatch in {path}")
    recorded_policy = selected_thp_policy(host_pre_run)
    if run["thp_recorded_in_raw"] and recorded_policy != run["thp_policy"]:
        raise RuntimeError(
            f"THP policy mismatch in {path}: expected {run['thp_policy']}, got {recorded_policy}"
        )
    return summary


def validate_pair(pair: str, summaries: dict[tuple[str, str], dict[str, str]]) -> dict[str, Any]:
    ubuntu = summaries[(pair, "ubuntu")]
    debian = summaries[(pair, "debian")]
    equal_fields = (
        "idle_start_height",
        "idle_end_height",
        "idle_start_hash",
        "idle_end_hash",
    )
    mismatches = {
        field: {"ubuntu": ubuntu[field], "debian": debian[field]}
        for field in equal_fields
        if ubuntu[field] != debian[field]
    }
    if mismatches:
        raise RuntimeError(f"pair {pair} chain mismatch: {mismatches}")
    return {
        "valid": True,
        **{field: ubuntu[field] for field in equal_fields},
        "ubuntu_outgoing": int(ubuntu["outgoing_at_idle_start"]),
        "debian_outgoing": int(debian["outgoing_at_idle_start"]),
        "incoming_each": 0,
        "stop_rc_each": 0,
        "fatal_pattern_matches_each": 0,
    }


def percent_change(new: int, old: int) -> float:
    return 100.0 * (new - old) / old


def metric_comparison(new: dict[str, int], old: dict[str, int]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for metric in METRICS:
        old_value = old[metric]
        new_value = new[metric]
        output[f"{metric}_old_kb"] = old_value
        output[f"{metric}_new_kb"] = new_value
        output[f"{metric}_diff_kb"] = new_value - old_value
        output[f"{metric}_pct"] = round(percent_change(new_value, old_value), 6) if old_value else None
    return output


def main() -> None:
    rows: list[dict[str, Any]] = []
    summaries: dict[tuple[str, str], dict[str, str]] = {}
    for run in RUNS:
        pair = str(run["pair"])
        os_name = str(run["os"])
        path = Path(run["path"])
        summaries[(pair, os_name)] = validate_run(run)
        for label in LABELS:
            values = parse_smaps(path / f"{label}-smaps-rollup.txt")
            epoch_ns = int((path / f"{label}-memory-epoch-ns.txt").read_text(encoding="utf-8").strip())
            rows.append(
                {
                    "pair": pair,
                    "os": os_name,
                    "thp_policy": run["thp_policy"],
                    "thp_recorded_in_raw": run["thp_recorded_in_raw"],
                    "label": label,
                    "epoch_ns": epoch_ns,
                    **{f"{metric}_kb": values[metric] for metric in METRICS},
                }
            )

    pair_validity = {pair: validate_pair(pair, summaries) for pair in ("08", "09")}
    lookup = {
        (row["pair"], row["os"], row["label"]): {
            metric: int(row[f"{metric}_kb"]) for metric in METRICS
        }
        for row in rows
    }

    comparisons: dict[str, Any] = {
        "debian_pair08_always_to_pair09_madvise": {},
        "ubuntu_pair08_madvise_to_pair09_madvise_control": {},
        "pair09_debian_minus_ubuntu_both_madvise": {},
        "difference_in_differences": {},
    }
    for label in LABELS:
        d08 = lookup[("08", "debian", label)]
        d09 = lookup[("09", "debian", label)]
        u08 = lookup[("08", "ubuntu", label)]
        u09 = lookup[("09", "ubuntu", label)]
        comparisons["debian_pair08_always_to_pair09_madvise"][label] = metric_comparison(d09, d08)
        comparisons["ubuntu_pair08_madvise_to_pair09_madvise_control"][label] = metric_comparison(u09, u08)
        comparisons["pair09_debian_minus_ubuntu_both_madvise"][label] = {
            f"{metric}_diff_kb": d09[metric] - u09[metric] for metric in METRICS
        }
        comparisons["difference_in_differences"][label] = {
            f"{metric}_kb": (d09[metric] - d08[metric]) - (u09[metric] - u08[metric])
            for metric in METRICS
        }

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_ROOT / "thp-causality.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    json_path = OUT_ROOT / "thp-causality.json"
    payload = {
        "binary_sha256": EXPECTED_BINARY_SHA256,
        "pair_validity": pair_validity,
        "comparisons": comparisons,
        "limitations": [
            "pair08 predates in-harness THP capture; its Ubuntu=madvise and Debian=always policies were live-read back outside the pair08 raw directory",
            "pair08 and pair09 occurred at different wall-clock times and live network heights; Ubuntu is the time/control host for difference-in-differences",
            "one before/after diagnostic pair establishes mechanism strongly but is not a substitute for a repeated randomized OS benchmark",
        ],
        "interpretation": (
            "If Debian AnonHugePages collapses to zero and Debian RSS/Anonymous converge with the "
            "Ubuntu madvise control while Ubuntu remains stable, the earlier cross-OS RSS gap is a "
            "THP-policy effect rather than evidence that the Universal binary intrinsically uses more "
            "memory on Debian."
        ),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")
    for label in LABELS:
        debian = comparisons["debian_pair08_always_to_pair09_madvise"][label]
        control = comparisons["ubuntu_pair08_madvise_to_pair09_madvise_control"][label]
        cross = comparisons["pair09_debian_minus_ubuntu_both_madvise"][label]
        did = comparisons["difference_in_differences"][label]
        print(
            f"{label}: Debian RSS {debian['Rss_old_kb']}->{debian['Rss_new_kb']} kB "
            f"({debian['Rss_pct']:+.2f}%); AHP {debian['AnonHugePages_old_kb']}->"
            f"{debian['AnonHugePages_new_kb']} kB; Ubuntu-control RSS diff "
            f"{control['Rss_diff_kb']:+d} kB; pair09 D-U RSS {cross['Rss_diff_kb']:+d} kB; "
            f"RSS DiD {did['Rss_kb']:+d} kB"
        )


if __name__ == "__main__":
    main()
