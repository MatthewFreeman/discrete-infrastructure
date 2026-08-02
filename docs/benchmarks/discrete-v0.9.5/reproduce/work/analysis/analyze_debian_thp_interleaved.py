#!/usr/bin/env python3
"""Estimate Debian THP effects using Ubuntu as a simultaneous control host."""

from __future__ import annotations

import csv
import itertools
import json
import random
import statistics
from pathlib import Path
from typing import Any

from analyze_crossos_cold import analyze_run, percentile


WORKSPACE = Path(__file__).resolve().parents[2]
RAW_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "raw" / "cold-debian-thp-interleaved"
OUT_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "analysis"
CONDITIONS = {
    13: "always", 14: "madvise", 15: "madvise", 16: "always",
    17: "madvise", 18: "always", 19: "always", 20: "madvise",
    21: "always", 22: "madvise", 23: "madvise", 24: "always",
}
METRICS = (
    "normalized_wall_to_4500_s",
    "cpu_total_per_observed_block_ms",
    "rss_average_to_target_kb",
    "rss_peak_kb",
    "minor_faults_final",
    "major_faults_final",
    "voluntary_context_switches_final",
    "nonvoluntary_context_switches_final",
    "host_disk_read_bytes_to_target",
    "host_disk_write_bytes_to_target",
    "rpc_latency_mean_ms",
    "rpc_latency_p95_ms",
    "target_smaps_rss_kb",
    "target_smaps_anonymous_kb",
    "target_smaps_anon_huge_pages_kb",
)


def parse_smaps(path: Path) -> dict[str, int]:
    wanted = {"Rss", "Anonymous", "AnonHugePages"}
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        if key in wanted:
            values[key] = int(rest.split()[0])
    if set(values) != wanted:
        raise RuntimeError(f"missing smaps fields in {path}: {wanted - set(values)}")
    return values


def validate_thp(path: Path, expected: str) -> None:
    host_pre = (path / "host-pre-run.txt").read_text(encoding="utf-8")
    selected = f"[{expected}]"
    lines = [
        line for line in host_pre.splitlines()
        if line.startswith("/sys/kernel/mm/transparent_hugepage/enabled=")
    ]
    if len(lines) != 1 or selected not in lines[0]:
        raise RuntimeError(f"expected THP={expected}, found {lines!r}: {path}")


def exact_permutation_pvalue(always: list[float], madvise: list[float]) -> float:
    values = always + madvise
    observed = abs(statistics.mean(madvise) - statistics.mean(always))
    exceed = 0
    total = 0
    for madvise_indexes in itertools.combinations(range(len(values)), len(madvise)):
        selected = set(madvise_indexes)
        candidate_m = [value for index, value in enumerate(values) if index in selected]
        candidate_a = [value for index, value in enumerate(values) if index not in selected]
        candidate = abs(statistics.mean(candidate_m) - statistics.mean(candidate_a))
        exceed += candidate >= observed - 1e-12
        total += 1
    return exceed / total


def bootstrap_ci(always: list[float], madvise: list[float], seed: int) -> tuple[float, float]:
    rng = random.Random(seed)
    effects = []
    for _ in range(200_000):
        a_mean = statistics.mean(rng.choice(always) for _ in always)
        m_mean = statistics.mean(rng.choice(madvise) for _ in madvise)
        effects.append(m_mean - a_mean)
    return percentile(effects, 0.025), percentile(effects, 0.975)


def main() -> None:
    rows: list[dict[str, Any]] = []
    for logical_pair, ordinal in enumerate(CONDITIONS, start=1):
        condition = CONDITIONS[ordinal]
        for os_name, folder, suffix, expected_thp in (
            ("ubuntu24.04", "ubuntu", "ubuntu24.04", "madvise"),
            ("debian12", "debian", "debian12", condition),
        ):
            run_dir = RAW_ROOT / folder / f"crossos-cold-{ordinal:02d}-{suffix}"
            if not run_dir.is_dir():
                raise RuntimeError(f"missing run directory: {run_dir}")
            validate_thp(run_dir, expected_thp)
            row = analyze_run(
                run_dir,
                os_name,
                logical_pair,
                allow_known_monitor_race=(ordinal == 20 and os_name == "ubuntu24.04"),
            )
            smaps = parse_smaps(run_dir / "target-smaps-rollup.txt")
            row["ordinal"] = ordinal
            row["debian_thp_condition"] = condition
            row["target_smaps_rss_kb"] = smaps["Rss"]
            row["target_smaps_anonymous_kb"] = smaps["Anonymous"]
            row["target_smaps_anon_huge_pages_kb"] = smaps["AnonHugePages"]
            rows.append(row)

    lookup = {
        (int(row["ordinal"]), str(row["os"])): row
        for row in rows
    }
    effects: dict[str, Any] = {}
    for metric_index, metric in enumerate(METRICS, start=1):
        deltas: dict[str, list[float]] = {"always": [], "madvise": []}
        ubuntu_values: dict[str, list[float]] = {"always": [], "madvise": []}
        debian_values: dict[str, list[float]] = {"always": [], "madvise": []}
        for ordinal, condition in CONDITIONS.items():
            ubuntu = float(lookup[(ordinal, "ubuntu24.04")][metric])
            debian = float(lookup[(ordinal, "debian12")][metric])
            ubuntu_values[condition].append(ubuntu)
            debian_values[condition].append(debian)
            deltas[condition].append(debian - ubuntu)
        always = deltas["always"]
        madvise = deltas["madvise"]
        effect = statistics.mean(madvise) - statistics.mean(always)
        ci_low, ci_high = bootstrap_ci(always, madvise, metric_index)
        effects[metric] = {
            "direction": "positive means madvise increased the Debian metric relative to the simultaneous Ubuntu control",
            "ubuntu_control_mean_during_always_pairs": statistics.mean(ubuntu_values["always"]),
            "ubuntu_control_mean_during_madvise_pairs": statistics.mean(ubuntu_values["madvise"]),
            "debian_always_mean": statistics.mean(debian_values["always"]),
            "debian_madvise_mean": statistics.mean(debian_values["madvise"]),
            "debian_minus_ubuntu_delta_always_mean": statistics.mean(always),
            "debian_minus_ubuntu_delta_madvise_mean": statistics.mean(madvise),
            "adjusted_effect_madvise_minus_always": effect,
            "adjusted_effect_percent_of_debian_always_mean": (
                effect / statistics.mean(debian_values["always"]) * 100
                if statistics.mean(debian_values["always"]) else None
            ),
            "bootstrap_95_ci": [ci_low, ci_high],
            "exact_label_permutation_two_sided_p": exact_permutation_pvalue(always, madvise),
            "always_pair_deltas": always,
            "madvise_pair_deltas": madvise,
        }

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_ROOT / "cold-debian-thp-interleaved-per-run.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    classification = {
        "run": "crossos-cold-20-ubuntu24.04",
        "raw_fatal_pattern_matches": 1,
        "classification": "benchmark-monitor false positive; daemon run valid",
        "matched_line": "monitor.sh: awk fatal while reading a stale /proc/PID/io after daemon exit",
        "required_evidence": {
            "systemd_result": "success",
            "exec_main_code": 0,
            "exec_main_status": 0,
            "systemctl_stop_rc": 0,
        },
        "raw_files_were_not_modified": True,
    }
    classification_path = OUT_ROOT / "cold-pair20-monitor-race-classification.json"
    classification_path.write_text(json.dumps(classification, indent=2) + "\n", encoding="utf-8")

    stats_path = OUT_ROOT / "cold-debian-thp-interleaved-statistics.json"
    stats_path.write_text(
        json.dumps(
            {
                "design": {
                    "ubuntu_policy": "madvise for all 12 simultaneous control runs",
                    "debian_order": [CONDITIONS[ordinal] for ordinal in CONDITIONS],
                    "debian_always_runs": 6,
                    "debian_madvise_runs": 6,
                    "target_height": 4500,
                },
                "metrics": effects,
                "limitations": [
                    "THP assignment was fixed before execution but not randomly generated.",
                    "Ubuntu controls shared wall-clock network conditions but cannot remove host-specific noisy-neighbor effects.",
                    "The bootstrap confidence intervals use a deterministic 200000-draw within-condition bootstrap.",
                ],
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"wrote {csv_path}")
    print(f"wrote {classification_path}")
    print(f"wrote {stats_path}")
    for metric in (
        "normalized_wall_to_4500_s",
        "cpu_total_per_observed_block_ms",
        "rss_average_to_target_kb",
        "rss_peak_kb",
        "target_smaps_anon_huge_pages_kb",
        "rpc_latency_mean_ms",
    ):
        item = effects[metric]
        percent = item["adjusted_effect_percent_of_debian_always_mean"]
        percent_text = "n/a" if percent is None else f"{percent:+.3f}%"
        print(
            f"{metric}: D always={item['debian_always_mean']:.6f} "
            f"D madvise={item['debian_madvise_mean']:.6f}; "
            f"adjusted effect={item['adjusted_effect_madvise_minus_always']:+.6f} "
            f"({percent_text}); CI=[{item['bootstrap_95_ci'][0]:+.6f},"
            f"{item['bootstrap_95_ci'][1]:+.6f}]; "
            f"p={item['exact_label_permutation_two_sided_p']:.5f}"
        )


if __name__ == "__main__":
    main()
