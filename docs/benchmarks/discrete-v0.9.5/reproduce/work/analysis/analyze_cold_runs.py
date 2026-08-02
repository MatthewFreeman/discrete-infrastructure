#!/usr/bin/env python3
import csv
import json
import math
import re
import statistics
import sys
from pathlib import Path


def read_int(path: Path) -> int:
    return int(path.read_text(encoding="utf-8").strip())


def read_kv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    if value in (None, ""):
        return default
    return float(value)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def group_stats(values: list[float]) -> dict[str, float]:
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def analyze_run(run_dir: Path) -> dict[str, object]:
    metadata = read_kv(run_dir / "run-metadata.txt")
    launch_ns = read_int(run_dir / "launch-epoch-ns.txt")
    sync_ns = read_int(run_dir / "sync-detected-epoch-ns.txt")
    stop_start_ns = read_int(run_dir / "stop-start-epoch-ns.txt")
    stop_end_ns = read_int(run_dir / "stop-end-epoch-ns.txt")
    stop_rc = read_int(run_dir / "systemctl-stop-exit-code.txt")

    events_text = (run_dir / "events.log").read_text(encoding="utf-8", errors="replace")
    clock_match = re.search(r"clock_ticks=(\d+)", events_text)
    clock_ticks = int(clock_match.group(1)) if clock_match else 100

    rpc_rows = read_tsv(run_dir / "rpc-samples.tsv")
    valid_rpc = [
        row
        for row in rpc_rows
        if row.get("curl_rc") == "0"
        and row.get("http_code") == "200"
        and row.get("status") == "OK"
        and row.get("height", "").isdigit()
    ]
    if not valid_rpc:
        raise RuntimeError(f"no valid RPC samples in {run_dir}")

    samples = read_tsv(run_dir / "process-host-samples.tsv")
    if len(samples) < 2:
        raise RuntimeError(f"too few process samples in {run_dir}")

    first_rpc = valid_rpc[0]
    first_rpc_ns = int(first_rpc["epoch_ns"])
    first_rpc_height = int(first_rpc["height"])

    thresholds: dict[int, dict[str, str]] = {}
    for threshold in (1000, 2000, 3000, 4000, 4500):
        row = next((r for r in valid_rpc if int(r["height"]) >= threshold), None)
        if row is None:
            raise RuntimeError(f"height {threshold} not reached in {run_dir}")
        thresholds[threshold] = row

    fixed_rpc = thresholds[4500]
    fixed_ns = int(fixed_rpc["epoch_ns"])
    duration_fixed_s = (fixed_ns - launch_ns) / 1e9
    sync_phase_s = (fixed_ns - first_rpc_ns) / 1e9
    blocks_per_s = (4500 - first_rpc_height) / sync_phase_s

    fixed_samples = [row for row in samples if int(row["epoch_ns"]) <= fixed_ns]
    if len(fixed_samples) < 2:
        raise RuntimeError(f"too few samples through height 4500 in {run_dir}")
    first_sample = fixed_samples[0]
    last_sample = fixed_samples[-1]

    user_s = number(last_sample, "utime_ticks") / clock_ticks
    system_s = number(last_sample, "stime_ticks") / clock_ticks
    cpu_total_s = user_s + system_s
    avg_cpu_pct = cpu_total_s / duration_fixed_s * 100

    peak_cpu_pct = 0.0
    for previous, current in zip(fixed_samples, fixed_samples[1:]):
        wall_s = (number(current, "epoch_ns") - number(previous, "epoch_ns")) / 1e9
        if wall_s <= 0:
            continue
        ticks = (
            number(current, "utime_ticks")
            + number(current, "stime_ticks")
            - number(previous, "utime_ticks")
            - number(previous, "stime_ticks")
        )
        peak_cpu_pct = max(peak_cpu_pct, ticks / clock_ticks / wall_s * 100)

    rss_values = [number(row, "vmrss_kb") for row in fixed_samples]
    vmhwm_values = [number(row, "vmhwm_kb") for row in fixed_samples]

    rpc_fixed = [row for row in valid_rpc if int(row["epoch_ns"]) <= fixed_ns]
    rpc_latencies_ms = [number(row, "time_total_s") * 1000 for row in rpc_fixed]

    pre_stop = json.loads((run_dir / "pre-stop-getinfo.json").read_text(encoding="utf-8"))
    log_text = (run_dir / "discreted.log").read_text(encoding="utf-8", errors="replace")
    dmesg_text = (run_dir / "dmesg-tail.txt").read_text(encoding="utf-8", errors="replace")
    crash_pattern = re.compile(r"sigill|illegal instruction|segfault|oom-kill|out of memory", re.IGNORECASE)

    return {
        "run_id": metadata["run_id"],
        "variant": metadata["variant"],
        "binary_sha256": metadata["binary_sha256"],
        "rpc_ready_s": (first_rpc_ns - launch_ns) / 1e9,
        "first_rpc_height": first_rpc_height,
        "height_1000_s": (int(thresholds[1000]["epoch_ns"]) - launch_ns) / 1e9,
        "height_2000_s": (int(thresholds[2000]["epoch_ns"]) - launch_ns) / 1e9,
        "height_3000_s": (int(thresholds[3000]["epoch_ns"]) - launch_ns) / 1e9,
        "height_4000_s": (int(thresholds[4000]["epoch_ns"]) - launch_ns) / 1e9,
        "height_4500_s": duration_fixed_s,
        "blocks_per_s_to_4500": blocks_per_s,
        "sync_detected_s": (sync_ns - launch_ns) / 1e9,
        "cpu_user_s_to_4500": user_s,
        "cpu_system_s_to_4500": system_s,
        "cpu_total_s_to_4500": cpu_total_s,
        "avg_cpu_pct_to_4500": avg_cpu_pct,
        "peak_1s_cpu_pct_to_4500": peak_cpu_pct,
        "avg_rss_kb_to_4500": statistics.fmean(rss_values),
        "peak_rss_kb_to_4500": max(max(rss_values), max(vmhwm_values)),
        "minor_faults_to_4500": int(number(last_sample, "minflt")),
        "major_faults_to_4500": int(number(last_sample, "majflt")),
        "voluntary_context_switches_to_4500": int(number(last_sample, "voluntary_ctxt")),
        "nonvoluntary_context_switches_to_4500": int(number(last_sample, "nonvoluntary_ctxt")),
        "process_read_bytes_to_4500": int(number(last_sample, "read_bytes")),
        "process_write_bytes_to_4500": int(number(last_sample, "write_bytes")),
        "host_net_rx_bytes_delta_to_4500": int(number(last_sample, "net_rx_bytes") - number(first_sample, "net_rx_bytes")),
        "host_net_tx_bytes_delta_to_4500": int(number(last_sample, "net_tx_bytes") - number(first_sample, "net_tx_bytes")),
        "block_reads_completed_delta_to_4500": int(number(last_sample, "block_reads_completed") - number(first_sample, "block_reads_completed")),
        "block_writes_completed_delta_to_4500": int(number(last_sample, "block_writes_completed") - number(first_sample, "block_writes_completed")),
        "block_read_bytes_delta_to_4500": int((number(last_sample, "block_sectors_read") - number(first_sample, "block_sectors_read")) * 512),
        "block_write_bytes_delta_to_4500": int((number(last_sample, "block_sectors_written") - number(first_sample, "block_sectors_written")) * 512),
        "block_iops_avg_to_4500": (
            number(last_sample, "block_reads_completed")
            + number(last_sample, "block_writes_completed")
            - number(first_sample, "block_reads_completed")
            - number(first_sample, "block_writes_completed")
        ) / duration_fixed_s,
        "rpc_latency_mean_ms_to_4500": statistics.fmean(rpc_latencies_ms),
        "rpc_latency_p95_ms_to_4500": percentile(rpc_latencies_ms, 0.95),
        "max_outgoing_peers_to_4500": max(int(row["outgoing"]) for row in rpc_fixed),
        "max_incoming_peers_to_4500": max(int(row["incoming"]) for row in rpc_fixed),
        "pre_stop_outgoing_peers": int(pre_stop["outgoing_connections_count"]),
        "pre_stop_incoming_peers": int(pre_stop["incoming_connections_count"]),
        "stop_seconds": (stop_end_ns - stop_start_ns) / 1e9,
        "stop_exit_code": stop_rc,
        "node_stopped_log_marker": "Node stopped." in log_text,
        "crash_or_oom_marker": bool(crash_pattern.search(log_text) or crash_pattern.search(dmesg_text)),
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: analyze_cold_runs.py RESULTS_ROOT OUTPUT_DIR")
    results_root = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    run_dirs = sorted(path for path in (results_root / "runs").glob("cold-*") if path.is_dir())
    if len(run_dirs) != 8:
        raise RuntimeError(f"expected 8 cold runs, found {len(run_dirs)}")
    runs = [analyze_run(path) for path in run_dirs]

    per_run_csv = output_dir / "cold-sync-per-run.csv"
    with per_run_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(runs[0].keys()))
        writer.writeheader()
        writer.writerows(runs)

    metrics = [
        "rpc_ready_s",
        "height_1000_s",
        "height_2000_s",
        "height_3000_s",
        "height_4000_s",
        "height_4500_s",
        "blocks_per_s_to_4500",
        "sync_detected_s",
        "cpu_user_s_to_4500",
        "cpu_system_s_to_4500",
        "cpu_total_s_to_4500",
        "avg_cpu_pct_to_4500",
        "peak_1s_cpu_pct_to_4500",
        "avg_rss_kb_to_4500",
        "peak_rss_kb_to_4500",
        "minor_faults_to_4500",
        "major_faults_to_4500",
        "voluntary_context_switches_to_4500",
        "nonvoluntary_context_switches_to_4500",
        "process_read_bytes_to_4500",
        "process_write_bytes_to_4500",
        "host_net_rx_bytes_delta_to_4500",
        "host_net_tx_bytes_delta_to_4500",
        "block_reads_completed_delta_to_4500",
        "block_writes_completed_delta_to_4500",
        "block_read_bytes_delta_to_4500",
        "block_write_bytes_delta_to_4500",
        "block_iops_avg_to_4500",
        "rpc_latency_mean_ms_to_4500",
        "rpc_latency_p95_ms_to_4500",
        "stop_seconds",
    ]

    by_variant: dict[str, dict[str, dict[str, float]]] = {}
    for variant in ("ubuntu24.04", "linux-universal"):
        variant_runs = [run for run in runs if run["variant"] == variant]
        by_variant[variant] = {
            metric: group_stats([float(run[metric]) for run in variant_runs]) for metric in metrics
        }

    comparisons: dict[str, dict[str, float]] = {}
    for metric in metrics:
        ubuntu_mean = by_variant["ubuntu24.04"][metric]["mean"]
        universal_mean = by_variant["linux-universal"][metric]["mean"]
        comparisons[metric] = {
            "ubuntu_mean": ubuntu_mean,
            "universal_mean": universal_mean,
            "ubuntu_minus_universal": ubuntu_mean - universal_mean,
            "ubuntu_vs_universal_pct": ((ubuntu_mean / universal_mean) - 1) * 100 if universal_mean else math.nan,
        }

    summary = {
        "fixed_comparison_height": 4500,
        "run_count": len(runs),
        "runs_per_variant": 4,
        "variants": by_variant,
        "comparisons": comparisons,
        "all_stop_exit_zero": all(run["stop_exit_code"] == 0 for run in runs),
        "all_node_stopped_marker": all(run["node_stopped_log_marker"] for run in runs),
        "any_crash_or_oom_marker": any(run["crash_or_oom_marker"] for run in runs),
        "binary_sha256_by_variant": {
            variant: sorted({str(run["binary_sha256"]) for run in runs if run["variant"] == variant})
            for variant in ("ubuntu24.04", "linux-universal")
        },
    }
    (output_dir / "cold-sync-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
