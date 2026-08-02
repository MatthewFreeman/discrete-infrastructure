#!/usr/bin/env python3
"""Analyze warm/idle Ubuntu-vs-Debian runs with THP=madvise on both."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from analyze_crossos_warm import analyze_run, paired_summary


WORKSPACE = Path(__file__).resolve().parents[2]
RAW_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "raw" / "warm-thp-madvise"
OUT_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "analysis"
DEFAULT_STATS_PATH = OUT_ROOT / "warm-comparison-statistics.json"
ORDINALS = tuple(range(10, 16))
METRICS = (
    "first_rpc_seconds", "sync_ready_seconds", "idle_cpu_user_s", "idle_cpu_system_s",
    "idle_cpu_total_s", "idle_cpu_percent_one_core", "idle_rss_average_kb",
    "idle_rss_peak_kb", "lifetime_rss_hwm_kb", "idle_minor_faults",
    "idle_major_faults", "idle_voluntary_context_switches",
    "idle_nonvoluntary_context_switches", "idle_process_read_bytes",
    "idle_process_write_bytes", "idle_host_net_rx_bytes", "idle_host_net_tx_bytes",
    "idle_host_disk_reads", "idle_host_disk_read_bytes", "idle_host_disk_writes",
    "idle_host_disk_write_bytes", "idle_host_cpu_steal_percent",
    "idle_host_cpu_iowait_percent", "idle_rpc_latency_mean_ms",
    "idle_rpc_latency_p95_ms", "stop_seconds", "data_size_bytes",
)


def validate_thp(path: Path) -> None:
    host_pre = (path / "host-pre-run.txt").read_text(encoding="utf-8")
    expected = "/sys/kernel/mm/transparent_hugepage/enabled=always [madvise] never"
    if expected not in host_pre.splitlines():
        raise RuntimeError(f"run was not recorded with THP=madvise: {path}")


def main() -> None:
    rows: list[dict[str, Any]] = []
    for logical_pair, ordinal in enumerate(ORDINALS, start=1):
        pair_rows = []
        for os_name, folder, suffix in (
            ("ubuntu24.04", "ubuntu", "ubuntu24.04"),
            ("debian12", "debian", "debian12"),
        ):
            run_dir = RAW_ROOT / folder / f"crossos-warm-{ordinal:02d}-{suffix}"
            if not run_dir.is_dir():
                raise RuntimeError(f"missing run directory: {run_dir}")
            validate_thp(run_dir)
            row = analyze_run(run_dir, os_name, ordinal, logical_pair)
            row["thp_policy"] = "madvise"
            pair_rows.append(row)
        ubuntu, debian = pair_rows
        for key in ("idle_start_height", "idle_end_height", "idle_start_hash", "idle_end_hash"):
            if ubuntu[key] != debian[key]:
                raise RuntimeError(f"pair {ordinal:02d} mismatched {key}")
        rows.extend(pair_rows)

    stats = {metric: paired_summary(rows, metric) for metric in METRICS}
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_ROOT / "warm-thp-madvise-per-run.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    stats_path = OUT_ROOT / "warm-thp-madvise-statistics.json"
    stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    default_stats = json.loads(DEFAULT_STATS_PATH.read_text(encoding="utf-8"))
    selected = (
        "first_rpc_seconds", "sync_ready_seconds", "idle_cpu_total_s",
        "idle_cpu_percent_one_core", "idle_rss_average_kb", "idle_rss_peak_kb",
        "lifetime_rss_hwm_kb", "idle_minor_faults", "idle_major_faults",
        "idle_voluntary_context_switches", "idle_nonvoluntary_context_switches",
        "idle_host_net_rx_bytes", "idle_host_net_tx_bytes",
        "idle_host_disk_read_bytes", "idle_host_disk_write_bytes",
        "idle_rpc_latency_mean_ms", "idle_rpc_latency_p95_ms", "stop_seconds",
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

    comparison_path = OUT_ROOT / "warm-default-vs-thp-madvise.json"
    comparison_path.write_text(
        json.dumps(
            {
                "default_condition": "Ubuntu=madvise, Debian=always; valid warm ordinals 02-07",
                "normalized_condition": "Ubuntu=madvise, Debian=madvise; warm ordinals 10-15",
                "valid_runs_each_condition": 12,
                "metrics": comparison,
                "limitations": [
                    "Pairs are simultaneous across two separate VPS hosts, so unobserved host scheduling remains a confounder.",
                    "Live network height and peer sets evolve between pairs; paired chain-state barriers control state but not peer identity.",
                    "Cross-series gap changes are descriptive because the default and normalized series ran at different wall-clock times.",
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
        "first_rpc_seconds", "sync_ready_seconds", "idle_cpu_total_s",
        "idle_cpu_percent_one_core", "idle_rss_average_kb", "idle_rss_peak_kb",
        "idle_rpc_latency_mean_ms", "idle_rpc_latency_p95_ms", "stop_seconds",
    ):
        item = stats[metric]
        print(
            f"{metric}: U={item['ubuntu_mean']:.6f} D={item['debian_mean']:.6f} "
            f"U-D={item['paired_mean_diff_ubuntu_minus_debian']:+.6f} "
            f"rel={item['relative_diff_percent_of_debian_mean']:+.3f}% "
            f"CI=[{item['paired_bootstrap_95_ci_low']:+.6f},"
            f"{item['paired_bootstrap_95_ci_high']:+.6f}] "
            f"p={item['exact_sign_flip_two_sided_p']:.5f}"
        )


if __name__ == "__main__":
    main()
