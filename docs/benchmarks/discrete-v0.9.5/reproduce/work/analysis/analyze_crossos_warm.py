#!/usr/bin/env python3
"""Analyze paired Discrete Universal warm-start and idle runs."""

from __future__ import annotations

import csv
import itertools
import json
import math
import statistics
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[2]
RAW_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "raw" / "warm"
OUT_ROOT = WORKSPACE / "outputs" / "cross-os-v0.9.5" / "analysis"
CLK_TCK = 100
SECTOR_SIZE = 512
VALID_ORDINALS = tuple(range(2, 8))


def key_values(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def integer(row: dict[str, str], key: str) -> int:
    return int(row[key])


def delta(first: dict[str, str], last: dict[str, str], key: str) -> int:
    return integer(last, key) - integer(first, key)


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
    candidates = [
        abs(statistics.mean([difference * sign for difference, sign in zip(differences, signs)]))
        for signs in itertools.product((-1, 1), repeat=len(differences))
    ]
    return sum(candidate >= observed - 1e-12 for candidate in candidates) / len(candidates)


def exact_bootstrap_ci(differences: list[float]) -> tuple[float, float]:
    means = [
        statistics.mean(differences[index] for index in selection)
        for selection in itertools.product(range(len(differences)), repeat=len(differences))
    ]
    return percentile(means, 0.025), percentile(means, 0.975)


def paired_summary(rows: list[dict[str, float | int | str]], metric: str) -> dict[str, float | int]:
    ubuntu = [float(row[metric]) for row in rows if row["os"] == "ubuntu24.04"]
    debian = [float(row[metric]) for row in rows if row["os"] == "debian12"]
    lookup = {(int(row["pair"]), str(row["os"])): float(row[metric]) for row in rows}
    differences = [lookup[(pair, "ubuntu24.04")] - lookup[(pair, "debian12")] for pair in range(1, 7)]
    ci_low, ci_high = exact_bootstrap_ci(differences)
    debian_mean = statistics.mean(debian)
    relative = statistics.mean(differences) / debian_mean * 100 if debian_mean else math.nan
    return {
        "ubuntu_mean": statistics.mean(ubuntu),
        "ubuntu_sd": statistics.stdev(ubuntu),
        "debian_mean": debian_mean,
        "debian_sd": statistics.stdev(debian),
        "paired_mean_diff_ubuntu_minus_debian": statistics.mean(differences),
        "paired_median_diff_ubuntu_minus_debian": statistics.median(differences),
        "relative_diff_percent_of_debian_mean": relative,
        "paired_bootstrap_95_ci_low": ci_low,
        "paired_bootstrap_95_ci_high": ci_high,
        "exact_sign_flip_two_sided_p": exact_sign_flip_pvalue(differences),
        "ubuntu_lower_count": sum(difference < 0 for difference in differences),
        "debian_lower_count": sum(difference > 0 for difference in differences),
        "ties": sum(difference == 0 for difference in differences),
    }


def analyze_run(run_dir: Path, os_name: str, ordinal: int, pair: int) -> dict[str, float | int | str]:
    summary = key_values(run_dir / "run-summary.txt")
    if summary["stop_rc"] != "0" or summary["fatal_pattern_matches"] != "0":
        raise RuntimeError(f"invalid lifecycle result: {run_dir}")
    if summary["incoming_at_idle_start"] != "0":
        raise RuntimeError(f"inbound peer at idle start: {run_dir}")

    idle_start = int((run_dir / "idle-start-epoch-ns.txt").read_text(encoding="utf-8").strip())
    idle_end = int((run_dir / "idle-end-epoch-ns.txt").read_text(encoding="utf-8").strip())
    all_samples = tsv(run_dir / "process-host-samples.tsv")
    samples = [row for row in all_samples if idle_start <= int(row["epoch_ns"]) <= idle_end]
    if len(samples) < 100:
        raise RuntimeError(f"insufficient idle samples ({len(samples)}): {run_dir}")
    first = samples[0]
    last = samples[-1]
    sampled_seconds = (integer(last, "epoch_ns") - integer(first, "epoch_ns")) / 1_000_000_000

    host_keys = [
        "host_cpu_user", "host_cpu_nice", "host_cpu_system", "host_cpu_idle",
        "host_cpu_iowait", "host_cpu_irq", "host_cpu_softirq", "host_cpu_steal",
    ]
    host_deltas = {key: delta(first, last, key) for key in host_keys}
    host_total = sum(host_deltas.values())

    rpc_rows = [
        row for row in tsv(run_dir / "rpc-samples.tsv")
        if idle_start <= int(row["epoch_ns"]) <= idle_end and row["http_code"] == "200"
    ]
    rpc_ms = [float(row["time_total_s"]) * 1000 for row in rpc_rows]
    start_info = json.loads((run_dir / "idle-start-getinfo.json").read_text(encoding="utf-8"))
    end_info = json.loads((run_dir / "idle-end-getinfo.json").read_text(encoding="utf-8"))

    user_seconds = delta(first, last, "utime_ticks") / CLK_TCK
    system_seconds = delta(first, last, "stime_ticks") / CLK_TCK
    total_seconds = user_seconds + system_seconds
    data_size = int((run_dir / "data-size-bytes.txt").read_text(encoding="utf-8").split()[0])
    lifetime_hwm_values = [integer(row, "vmhwm_kb") for row in all_samples if row["vmhwm_kb"]]
    if not lifetime_hwm_values:
        raise RuntimeError(f"no process HWM samples: {run_dir}")
    return {
        "pair": pair,
        "ordinal": ordinal,
        "os": os_name,
        "run_id": summary["run_id"],
        "first_rpc_seconds": float(summary["first_rpc_seconds"]),
        "sync_ready_seconds": float(summary["sync_ready_seconds"]),
        "idle_actual_seconds": float(summary["idle_actual_seconds"]),
        "idle_sampled_seconds": sampled_seconds,
        "idle_start_height": int(summary["idle_start_height"]),
        "idle_end_height": int(summary["idle_end_height"]),
        "idle_blocks_received": int(summary["idle_end_height"]) - int(summary["idle_start_height"]),
        "outgoing_at_idle_start": int(summary["outgoing_at_idle_start"]),
        "incoming_at_idle_start": int(summary["incoming_at_idle_start"]),
        "idle_cpu_user_s": user_seconds,
        "idle_cpu_system_s": system_seconds,
        "idle_cpu_total_s": total_seconds,
        "idle_cpu_percent_one_core": total_seconds / sampled_seconds * 100,
        "idle_rss_average_kb": statistics.mean(integer(row, "vmrss_kb") for row in samples),
        "idle_rss_peak_kb": max(integer(row, "vmrss_kb") for row in samples),
        "lifetime_rss_hwm_kb": max(lifetime_hwm_values),
        "idle_minor_faults": delta(first, last, "minflt"),
        "idle_major_faults": delta(first, last, "majflt"),
        "idle_voluntary_context_switches": delta(first, last, "voluntary_ctxt"),
        "idle_nonvoluntary_context_switches": delta(first, last, "nonvoluntary_ctxt"),
        "idle_process_read_bytes": delta(first, last, "read_bytes"),
        "idle_process_write_bytes": delta(first, last, "write_bytes"),
        "idle_process_read_syscalls": delta(first, last, "syscr"),
        "idle_process_write_syscalls": delta(first, last, "syscw"),
        "idle_host_net_rx_bytes": delta(first, last, "net_rx_bytes"),
        "idle_host_net_tx_bytes": delta(first, last, "net_tx_bytes"),
        "idle_host_disk_reads": delta(first, last, "block_reads_completed"),
        "idle_host_disk_read_bytes": delta(first, last, "block_sectors_read") * SECTOR_SIZE,
        "idle_host_disk_writes": delta(first, last, "block_writes_completed"),
        "idle_host_disk_write_bytes": delta(first, last, "block_sectors_written") * SECTOR_SIZE,
        "idle_host_cpu_steal_percent": host_deltas["host_cpu_steal"] / host_total * 100 if host_total else 0,
        "idle_host_cpu_iowait_percent": host_deltas["host_cpu_iowait"] / host_total * 100 if host_total else 0,
        "idle_rpc_success_samples": len(rpc_rows),
        "idle_rpc_latency_mean_ms": statistics.mean(rpc_ms),
        "idle_rpc_latency_p95_ms": percentile(rpc_ms, 0.95),
        "stop_seconds": float(summary["stop_seconds"]),
        "data_size_bytes": data_size,
        "idle_start_hash": str(start_info["top_block_hash"]),
        "idle_end_hash": str(end_info["top_block_hash"]),
    }


def main() -> None:
    invalids = sorted(RAW_ROOT.glob("**/crossos-warm-01-*/invalid-reason.txt"))
    if len(invalids) != 2:
        raise RuntimeError(f"expected two explicit invalid pair-01 markers, found {len(invalids)}")

    rows: list[dict[str, float | int | str]] = []
    for pair, ordinal in enumerate(VALID_ORDINALS, start=1):
        pair_rows = []
        for os_name, folder, suffix in (
            ("ubuntu24.04", "ubuntu", "ubuntu24.04"),
            ("debian12", "debian", "debian12"),
        ):
            run_dir = RAW_ROOT / folder / f"crossos-warm-{ordinal:02d}-{suffix}"
            if not run_dir.is_dir():
                raise RuntimeError(f"missing valid run: {run_dir}")
            pair_rows.append(analyze_run(run_dir, os_name, ordinal, pair))
        ubuntu, debian = pair_rows
        for key in ("idle_start_height", "idle_end_height", "idle_start_hash", "idle_end_hash"):
            if ubuntu[key] != debian[key]:
                raise RuntimeError(f"pair {ordinal:02d} mismatched {key}")
        rows.extend(pair_rows)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_ROOT / "warm-per-run.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    metrics = [
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
    ]
    stats = {metric: paired_summary(rows, metric) for metric in metrics}
    stats_path = OUT_ROOT / "warm-comparison-statistics.json"
    stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"wrote {csv_path}")
    print(f"wrote {stats_path}")
    for metric in (
        "first_rpc_seconds", "sync_ready_seconds", "idle_cpu_total_s",
        "idle_cpu_percent_one_core", "idle_rss_average_kb", "idle_rss_peak_kb",
        "idle_rpc_latency_mean_ms", "stop_seconds",
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
