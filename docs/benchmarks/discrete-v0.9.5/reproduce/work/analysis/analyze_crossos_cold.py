#!/usr/bin/env python3
"""Analyze paired Discrete Universal cold-sync runs on Ubuntu and Debian."""

from __future__ import annotations

import csv
import itertools
import json
import math
import re
import statistics
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[2]
RAW_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "raw" / "cold"
OUT_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "analysis"
CLK_TCK = 100
SECTOR_SIZE = 512


def read_key_values(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def as_int(row: dict[str, str], key: str) -> int:
    return int(row[key])


def delta(first: dict[str, str], last: dict[str, str], key: str) -> int:
    return as_int(last, key) - as_int(first, key)


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def exact_sign_flip_pvalue(differences: list[float]) -> float:
    observed = abs(statistics.mean(differences))
    exceed = 0
    total = 0
    for signs in itertools.product((-1, 1), repeat=len(differences)):
        candidate = abs(statistics.mean([d * s for d, s in zip(differences, signs)]))
        exceed += candidate >= observed - 1e-12
        total += 1
    return exceed / total


def exact_paired_bootstrap_ci(differences: list[float]) -> tuple[float, float]:
    means = [
        statistics.mean(differences[index] for index in selection)
        for selection in itertools.product(range(len(differences)), repeat=len(differences))
    ]
    return percentile(means, 0.025), percentile(means, 0.975)


def summarize_pair_metric(rows: list[dict[str, float | int | str]], metric: str) -> dict[str, float | int]:
    ubuntu = [float(row[metric]) for row in rows if row["os"] == "ubuntu24.04"]
    debian = [float(row[metric]) for row in rows if row["os"] == "debian12"]
    by_pair = {(int(row["pair"]), str(row["os"])): float(row[metric]) for row in rows}
    differences = [by_pair[(pair, "ubuntu24.04")] - by_pair[(pair, "debian12")] for pair in range(1, 7)]
    ci_low, ci_high = exact_paired_bootstrap_ci(differences)
    return {
        "ubuntu_mean": statistics.mean(ubuntu),
        "ubuntu_sd": statistics.stdev(ubuntu),
        "debian_mean": statistics.mean(debian),
        "debian_sd": statistics.stdev(debian),
        "paired_mean_diff_ubuntu_minus_debian": statistics.mean(differences),
        "paired_median_diff_ubuntu_minus_debian": statistics.median(differences),
        "relative_diff_percent_of_debian_mean": statistics.mean(differences) / statistics.mean(debian) * 100,
        "paired_bootstrap_95_ci_low": ci_low,
        "paired_bootstrap_95_ci_high": ci_high,
        "exact_sign_flip_two_sided_p": exact_sign_flip_pvalue(differences),
        "ubuntu_lower_count": sum(diff < 0 for diff in differences),
        "debian_lower_count": sum(diff > 0 for diff in differences),
        "ties": sum(diff == 0 for diff in differences),
    }


def known_monitor_pid_race(run_dir: Path) -> bool:
    pattern = re.compile(
        r"monitor\.sh\[\d+\]: awk: fatal: cannot open file `/proc/\d+/io' "
        r"for reading: Permission denied$"
    )
    crash_pattern = re.compile(
        r"SIGILL|illegal instruction|segmentation fault|segfault|assert|fatal|"
        r"terminate called|core dumped",
        flags=re.IGNORECASE,
    )
    matches: list[str] = []
    for name in ("discreted.log", "journal-run.txt", "dmesg-tail.txt"):
        for line in (run_dir / name).read_text(encoding="utf-8", errors="replace").splitlines():
            if crash_pattern.search(line):
                matches.append(line)
    systemd = read_key_values(run_dir / "systemd-daemon-post-run.txt")
    return (
        len(matches) == 1
        and bool(pattern.search(matches[0]))
        and systemd.get("Result") == "success"
        and systemd.get("ExecMainCode") == "0"
        and systemd.get("ExecMainStatus") == "0"
    )


def analyze_run(
    run_dir: Path,
    os_name: str,
    pair: int,
    *,
    allow_known_monitor_race: bool = False,
) -> dict[str, float | int | str]:
    summary = read_key_values(run_dir / "run-summary.txt")
    raw_fatal_matches = int(summary["fatal_pattern_matches"])
    classified_monitor_race = (
        raw_fatal_matches == 1
        and allow_known_monitor_race
        and known_monitor_pid_race(run_dir)
    )
    if summary["stop_rc"] != "0" or (raw_fatal_matches != 0 and not classified_monitor_race):
        raise RuntimeError(f"invalid lifecycle result: {run_dir}")
    if summary["incoming_at_target"] != "0":
        raise RuntimeError(f"inbound peer detected: {run_dir}")

    target_epoch = int((run_dir / "target-epoch-ns.txt").read_text(encoding="utf-8").strip())
    samples = read_tsv(run_dir / "process-host-samples.tsv")
    if not samples:
        raise RuntimeError(f"no process samples: {run_dir}")
    samples_to_target = [row for row in samples if int(row["epoch_ns"]) <= target_epoch]
    if not samples_to_target:
        raise RuntimeError(f"no sample before target: {run_dir}")
    first = samples[0]
    last_target = samples_to_target[-1]
    required_final_fields = (
        "utime_ticks", "stime_ticks", "minflt", "majflt", "voluntary_ctxt",
        "nonvoluntary_ctxt", "read_bytes", "write_bytes", "syscr", "syscw",
    )
    complete_samples = [
        row for row in samples
        if all(row.get(field, "") != "" for field in required_final_fields)
    ]
    if not complete_samples:
        raise RuntimeError(f"no complete process samples: {run_dir}")
    last = complete_samples[-1]

    host_keys = [
        "host_cpu_user", "host_cpu_nice", "host_cpu_system", "host_cpu_idle",
        "host_cpu_iowait", "host_cpu_irq", "host_cpu_softirq", "host_cpu_steal",
    ]
    host_deltas = {key: delta(first, last_target, key) for key in host_keys}
    host_total = sum(host_deltas.values())

    rpc_rows = [
        row for row in read_tsv(run_dir / "rpc-samples.tsv")
        if int(row["epoch_ns"]) <= target_epoch and row["http_code"] == "200"
    ]
    rpc_latencies_ms = [float(row["time_total_s"]) * 1000 for row in rpc_rows]

    target = json.loads((run_dir / "target-getinfo.json").read_text(encoding="utf-8"))
    wall = float(summary["wall_to_target_seconds"])
    observed_height = int(summary["observed_target_height"])
    cpu_user = as_int(last, "utime_ticks") / CLK_TCK
    cpu_system = as_int(last, "stime_ticks") / CLK_TCK

    data_size = int((run_dir / "data-size-bytes.txt").read_text(encoding="utf-8").split()[0])
    return {
        "pair": pair,
        "os": os_name,
        "run_id": summary["run_id"],
        "raw_fatal_pattern_matches": raw_fatal_matches,
        "classified_monitor_pid_race": classified_monitor_race,
        "wall_to_target_s": wall,
        "observed_height": observed_height,
        "normalized_wall_to_4500_s": wall * 4500 / observed_height,
        "observed_blocks_per_s": observed_height / wall,
        "outgoing_at_target": int(summary["outgoing_at_target"]),
        "incoming_at_target": int(summary["incoming_at_target"]),
        "target_last_known": int(target["last_known_block_index"]),
        "cpu_user_final_s": cpu_user,
        "cpu_system_final_s": cpu_system,
        "cpu_total_final_s": cpu_user + cpu_system,
        "cpu_total_per_observed_block_ms": (cpu_user + cpu_system) * 1000 / observed_height,
        "cpu_average_percent_one_core": (cpu_user + cpu_system) / wall * 100,
        "rss_average_to_target_kb": statistics.mean(as_int(row, "vmrss_kb") for row in samples_to_target),
        "rss_peak_kb": max(as_int(row, "vmhwm_kb") for row in samples),
        "minor_faults_final": as_int(last, "minflt"),
        "major_faults_final": as_int(last, "majflt"),
        "voluntary_context_switches_final": as_int(last, "voluntary_ctxt"),
        "nonvoluntary_context_switches_final": as_int(last, "nonvoluntary_ctxt"),
        "process_read_bytes_final": as_int(last, "read_bytes"),
        "process_write_bytes_final": as_int(last, "write_bytes"),
        "process_read_syscalls_final": as_int(last, "syscr"),
        "process_write_syscalls_final": as_int(last, "syscw"),
        "host_net_rx_bytes_to_target": delta(first, last_target, "net_rx_bytes"),
        "host_net_tx_bytes_to_target": delta(first, last_target, "net_tx_bytes"),
        "host_disk_reads_to_target": delta(first, last_target, "block_reads_completed"),
        "host_disk_read_bytes_to_target": delta(first, last_target, "block_sectors_read") * SECTOR_SIZE,
        "host_disk_writes_to_target": delta(first, last_target, "block_writes_completed"),
        "host_disk_write_bytes_to_target": delta(first, last_target, "block_sectors_written") * SECTOR_SIZE,
        "host_cpu_steal_percent_to_target": host_deltas["host_cpu_steal"] / host_total * 100 if host_total else 0,
        "host_cpu_iowait_percent_to_target": host_deltas["host_cpu_iowait"] / host_total * 100 if host_total else 0,
        "rpc_success_samples_to_target": len(rpc_rows),
        "rpc_latency_mean_ms": statistics.mean(rpc_latencies_ms),
        "rpc_latency_p95_ms": percentile(rpc_latencies_ms, 0.95),
        "stop_seconds": float(summary["stop_seconds"]),
        "data_size_bytes": data_size,
        "last_sample_before_target_gap_ms": (target_epoch - int(last_target["epoch_ns"])) / 1_000_000,
    }


def main() -> None:
    rows: list[dict[str, float | int | str]] = []
    for pair in range(1, 7):
        for os_name, folder, suffix in (
            ("ubuntu24.04", "ubuntu", "ubuntu24.04"),
            ("debian12", "debian", "debian12"),
        ):
            run_dir = RAW_ROOT / folder / f"crossos-cold-{pair:02d}-{suffix}"
            if not run_dir.is_dir():
                raise RuntimeError(f"missing run directory: {run_dir}")
            rows.append(analyze_run(run_dir, os_name, pair))

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_ROOT / "cold-per-run.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    metrics = [
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
    ]
    stats = {metric: summarize_pair_metric(rows, metric) for metric in metrics}
    stats_path = OUT_ROOT / "cold-comparison-statistics.json"
    stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"wrote {csv_path}")
    print(f"wrote {stats_path}")
    for metric in (
        "wall_to_target_s", "normalized_wall_to_4500_s", "cpu_total_final_s",
        "rss_average_to_target_kb", "rss_peak_kb", "host_cpu_steal_percent_to_target",
        "host_net_rx_bytes_to_target", "stop_seconds",
    ):
        item = stats[metric]
        print(
            f"{metric}: ubuntu={item['ubuntu_mean']:.6f} debian={item['debian_mean']:.6f} "
            f"U-D={item['paired_mean_diff_ubuntu_minus_debian']:.6f} "
            f"rel={item['relative_diff_percent_of_debian_mean']:.3f}% "
            f"CI=[{item['paired_bootstrap_95_ci_low']:.6f},{item['paired_bootstrap_95_ci_high']:.6f}] "
            f"p={item['exact_sign_flip_two_sided_p']:.5f}"
        )


if __name__ == "__main__":
    main()
