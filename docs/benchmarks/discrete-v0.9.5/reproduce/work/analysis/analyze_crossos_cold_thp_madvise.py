#!/usr/bin/env python3
"""Analyze cold sync on Ubuntu/Debian with THP=madvise on both hosts."""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path
from typing import Any

from analyze_crossos_cold import (
    analyze_run,
    exact_paired_bootstrap_ci,
    exact_sign_flip_pvalue,
    summarize_pair_metric,
)


WORKSPACE = Path(__file__).resolve().parents[2]
RAW_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "raw" / "cold-thp-madvise"
OUT_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "analysis"
DEFAULT_STATS_PATH = OUT_ROOT / "cold-comparison-statistics.json"
ORDINALS = tuple(range(7, 13))
METRICS = (
    "wall_to_target_s", "normalized_wall_to_4500_s", "observed_blocks_per_s",
    "cpu_user_final_s", "cpu_system_final_s", "cpu_total_final_s",
    "cpu_total_per_observed_block_ms", "cpu_average_percent_one_core",
    "rss_average_to_target_kb", "rss_peak_kb", "minor_faults_final",
    "major_faults_final", "voluntary_context_switches_final",
    "nonvoluntary_context_switches_final", "process_read_bytes_final",
    "process_write_bytes_final", "host_net_rx_bytes_to_target",
    "host_net_tx_bytes_to_target", "host_disk_reads_to_target",
    "host_disk_read_bytes_to_target", "host_disk_writes_to_target",
    "host_disk_write_bytes_to_target", "host_cpu_steal_percent_to_target",
    "host_cpu_iowait_percent_to_target", "rpc_latency_mean_ms",
    "rpc_latency_p95_ms", "stop_seconds", "data_size_bytes",
    "target_smaps_rss_kb", "target_smaps_anonymous_kb",
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
        raise RuntimeError(f"missing target smaps fields in {path}: {wanted - set(values)}")
    return values


def validate_thp(path: Path) -> str:
    host_pre = (path / "host-pre-run.txt").read_text(encoding="utf-8")
    expected = "/sys/kernel/mm/transparent_hugepage/enabled=always [madvise] never"
    if expected not in host_pre.splitlines():
        raise RuntimeError(f"run was not recorded with THP=madvise: {path}")
    return "madvise"


def summarize_metric(rows: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    debian = [float(row[metric]) for row in rows if row["os"] == "debian12"]
    if statistics.mean(debian) != 0:
        return summarize_pair_metric(rows, metric)
    ubuntu = [float(row[metric]) for row in rows if row["os"] == "ubuntu24.04"]
    by_pair = {(int(row["pair"]), str(row["os"])): float(row[metric]) for row in rows}
    differences = [
        by_pair[(pair, "ubuntu24.04")] - by_pair[(pair, "debian12")]
        for pair in range(1, 7)
    ]
    ci_low, ci_high = exact_paired_bootstrap_ci(differences)
    return {
        "ubuntu_mean": statistics.mean(ubuntu),
        "ubuntu_sd": statistics.stdev(ubuntu),
        "debian_mean": statistics.mean(debian),
        "debian_sd": statistics.stdev(debian),
        "paired_mean_diff_ubuntu_minus_debian": statistics.mean(differences),
        "paired_median_diff_ubuntu_minus_debian": statistics.median(differences),
        "relative_diff_percent_of_debian_mean": None,
        "paired_bootstrap_95_ci_low": ci_low,
        "paired_bootstrap_95_ci_high": ci_high,
        "exact_sign_flip_two_sided_p": exact_sign_flip_pvalue(differences),
        "ubuntu_lower_count": sum(diff < 0 for diff in differences),
        "debian_lower_count": sum(diff > 0 for diff in differences),
        "ties": sum(diff == 0 for diff in differences),
    }


def main() -> None:
    rows: list[dict[str, Any]] = []
    for logical_pair, ordinal in enumerate(ORDINALS, start=1):
        for os_name, folder, suffix in (
            ("ubuntu24.04", "ubuntu", "ubuntu24.04"),
            ("debian12", "debian", "debian12"),
        ):
            run_dir = RAW_ROOT / folder / f"crossos-cold-{ordinal:02d}-{suffix}"
            if not run_dir.is_dir():
                raise RuntimeError(f"missing run directory: {run_dir}")
            policy = validate_thp(run_dir)
            row = analyze_run(run_dir, os_name, logical_pair)
            smaps = parse_smaps(run_dir / "target-smaps-rollup.txt")
            row["ordinal"] = ordinal
            row["thp_policy"] = policy
            row["target_smaps_rss_kb"] = smaps["Rss"]
            row["target_smaps_anonymous_kb"] = smaps["Anonymous"]
            row["target_smaps_anon_huge_pages_kb"] = smaps["AnonHugePages"]
            rows.append(row)

    stats = {metric: summarize_metric(rows, metric) for metric in METRICS}
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_ROOT / "cold-thp-madvise-per-run.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    stats_path = OUT_ROOT / "cold-thp-madvise-statistics.json"
    stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    default_stats = json.loads(DEFAULT_STATS_PATH.read_text(encoding="utf-8"))
    selected = (
        "normalized_wall_to_4500_s", "cpu_total_per_observed_block_ms",
        "rss_average_to_target_kb", "rss_peak_kb", "minor_faults_final",
        "major_faults_final", "voluntary_context_switches_final",
        "nonvoluntary_context_switches_final", "host_disk_read_bytes_to_target",
        "host_disk_write_bytes_to_target", "rpc_latency_mean_ms",
        "rpc_latency_p95_ms", "stop_seconds",
    )
    comparison: dict[str, Any] = {}
    for metric in selected:
        old = default_stats[metric]
        new = stats[metric]
        old_gap = old["paired_mean_diff_ubuntu_minus_debian"]
        new_gap = new["paired_mean_diff_ubuntu_minus_debian"]
        comparison[metric] = {
            "default_ubuntu_mean": old["ubuntu_mean"],
            "default_debian_mean": old["debian_mean"],
            "default_gap_ubuntu_minus_debian": old_gap,
            "default_gap_bootstrap_95_ci": [
                old["paired_bootstrap_95_ci_low"], old["paired_bootstrap_95_ci_high"]
            ],
            "normalized_ubuntu_mean": new["ubuntu_mean"],
            "normalized_debian_mean": new["debian_mean"],
            "normalized_gap_ubuntu_minus_debian": new_gap,
            "normalized_gap_percent_of_debian_mean": new["relative_diff_percent_of_debian_mean"],
            "normalized_gap_bootstrap_95_ci": [
                new["paired_bootstrap_95_ci_low"], new["paired_bootstrap_95_ci_high"]
            ],
            "normalized_exact_sign_flip_two_sided_p": new["exact_sign_flip_two_sided_p"],
            "gap_change_normalized_minus_default": new_gap - old_gap,
        }

    comparison_path = OUT_ROOT / "cold-default-vs-thp-madvise.json"
    comparison_path.write_text(
        json.dumps(
            {
                "default_condition": "Ubuntu=madvise, Debian=always; cold ordinals 01-06",
                "normalized_condition": "Ubuntu=madvise, Debian=madvise; cold ordinals 07-12",
                "valid_runs_each_condition": 12,
                "metrics": comparison,
                "limitations": [
                    "Pairs are simultaneous across two separate VPS hosts, so unobserved host scheduling remains a confounder.",
                    "Cross-series gap changes are descriptive because ordinals 01-06 and 07-12 ran at different wall-clock times.",
                    "Six pairs provide only coarse uncertainty bounds; small differences should be treated as negligible unless consistent and operationally material.",
                ],
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"wrote {csv_path}")
    print(f"wrote {stats_path}")
    print(f"wrote {comparison_path}")
    for metric in (
        "normalized_wall_to_4500_s", "cpu_total_per_observed_block_ms",
        "rss_average_to_target_kb", "rss_peak_kb",
        "target_smaps_anon_huge_pages_kb", "rpc_latency_mean_ms", "stop_seconds",
    ):
        item = stats[metric]
        relative = item["relative_diff_percent_of_debian_mean"]
        relative_text = "n/a" if relative is None else f"{relative:+.3f}%"
        print(
            f"{metric}: U={item['ubuntu_mean']:.6f} D={item['debian_mean']:.6f} "
            f"U-D={item['paired_mean_diff_ubuntu_minus_debian']:+.6f} "
            f"rel={relative_text} "
            f"CI=[{item['paired_bootstrap_95_ci_low']:+.6f},"
            f"{item['paired_bootstrap_95_ci_high']:+.6f}] "
            f"p={item['exact_sign_flip_two_sided_p']:.5f}"
        )


if __name__ == "__main__":
    main()
