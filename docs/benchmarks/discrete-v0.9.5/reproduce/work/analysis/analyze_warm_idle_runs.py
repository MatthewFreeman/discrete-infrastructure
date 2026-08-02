#!/usr/bin/env python3
import csv
import datetime as dt
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
        "sum": sum(values),
    }


LOG_TIME = re.compile(r"^(\d{4}-[A-Za-z]{3}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)")


def marker_time(lines: list[str], marker: str) -> dt.datetime:
    for line in lines:
        if marker in line:
            match = LOG_TIME.match(line)
            if match:
                return dt.datetime.strptime(match.group(1), "%Y-%b-%d %H:%M:%S.%f")
    raise RuntimeError(f"log marker not found: {marker}")


def analyze_run(run_dir: Path) -> dict[str, object]:
    metadata = read_kv(run_dir / "run-metadata.txt")
    launch_ns = read_int(run_dir / "launch-epoch-ns.txt")
    sync_ns = read_int(run_dir / "sync-detected-epoch-ns.txt")
    idle_start_ns = read_int(run_dir / "idle-start-epoch-ns.txt")
    idle_end_ns = read_int(run_dir / "idle-end-epoch-ns.txt")
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
    first_rpc = valid_rpc[0]
    first_rpc_ns = int(first_rpc["epoch_ns"])

    samples = read_tsv(run_dir / "process-host-samples.tsv")
    idle_samples = [row for row in samples if idle_start_ns <= int(row["epoch_ns"]) <= idle_end_ns]
    if len(idle_samples) < 2:
        raise RuntimeError(f"too few idle samples in {run_dir}")
    first_sample = idle_samples[0]
    last_sample = idle_samples[-1]
    sample_window_s = (number(last_sample, "epoch_ns") - number(first_sample, "epoch_ns")) / 1e9

    user_s = (number(last_sample, "utime_ticks") - number(first_sample, "utime_ticks")) / clock_ticks
    system_s = (number(last_sample, "stime_ticks") - number(first_sample, "stime_ticks")) / clock_ticks
    cpu_total_s = user_s + system_s

    peak_cpu_pct = 0.0
    for previous, current in zip(idle_samples, idle_samples[1:]):
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

    idle_rpc = [row for row in valid_rpc if idle_start_ns <= int(row["epoch_ns"]) <= idle_end_ns]
    if not idle_rpc:
        raise RuntimeError(f"no idle RPC samples in {run_dir}")
    rpc_latencies_ms = [number(row, "time_total_s") * 1000 for row in idle_rpc]

    idle_start_info = json.loads((run_dir / "idle-start-getinfo.json").read_text(encoding="utf-8"))
    idle_end_info = json.loads((run_dir / "idle-end-getinfo.json").read_text(encoding="utf-8"))

    log_text = (run_dir / "discreted.log").read_text(encoding="utf-8", errors="replace")
    log_lines = log_text.splitlines()
    dmesg_text = (run_dir / "dmesg-tail.txt").read_text(encoding="utf-8", errors="replace")
    crash_pattern = re.compile(r"sigill|illegal instruction|segfault|oom-kill|out of memory", re.IGNORECASE)

    p2p_begin = marker_time(log_lines, "Initializing p2p server...")
    igd_begin = marker_time(log_lines, "Attempting to add IGD port mapping.")
    igd_end = marker_time(log_lines, "No IGD was found.")
    p2p_end = marker_time(log_lines, "P2p server initialized OK")
    core_begin = marker_time(log_lines, "Initializing core...")
    core_end = marker_time(log_lines, "Core initialized OK")
    rpc_begin = marker_time(log_lines, "Starting core RPC server on address")
    rpc_end = marker_time(log_lines, "RPC server started successfully")

    return {
        "run_id": metadata["run_id"],
        "variant": metadata["variant"],
        "binary_sha256": metadata["binary_sha256"],
        "rpc_ready_s": (first_rpc_ns - launch_ns) / 1e9,
        "sync_detected_s": (sync_ns - launch_ns) / 1e9,
        "p2p_init_log_s": (p2p_end - p2p_begin).total_seconds(),
        "igd_wait_log_s": (igd_end - igd_begin).total_seconds(),
        "core_init_log_s": (core_end - core_begin).total_seconds(),
        "rpc_server_init_log_s": (rpc_end - rpc_begin).total_seconds(),
        "idle_requested_s": (idle_end_ns - idle_start_ns) / 1e9,
        "idle_sample_window_s": sample_window_s,
        "idle_height_start": int(idle_start_info["height"]),
        "idle_height_end": int(idle_end_info["height"]),
        "idle_height_delta": int(idle_end_info["height"]) - int(idle_start_info["height"]),
        "idle_cpu_user_s": user_s,
        "idle_cpu_system_s": system_s,
        "idle_cpu_total_s": cpu_total_s,
        "idle_avg_cpu_pct": cpu_total_s / sample_window_s * 100,
        "idle_peak_1s_cpu_pct": peak_cpu_pct,
        "idle_avg_rss_kb": statistics.fmean(number(row, "vmrss_kb") for row in idle_samples),
        "idle_peak_rss_kb": max(max(number(row, "vmrss_kb") for row in idle_samples), max(number(row, "vmhwm_kb") for row in idle_samples)),
        "idle_minor_faults_delta": int(number(last_sample, "minflt") - number(first_sample, "minflt")),
        "idle_major_faults_delta": int(number(last_sample, "majflt") - number(first_sample, "majflt")),
        "idle_voluntary_context_switches_delta": int(number(last_sample, "voluntary_ctxt") - number(first_sample, "voluntary_ctxt")),
        "idle_nonvoluntary_context_switches_delta": int(number(last_sample, "nonvoluntary_ctxt") - number(first_sample, "nonvoluntary_ctxt")),
        "idle_process_read_bytes_delta": int(number(last_sample, "read_bytes") - number(first_sample, "read_bytes")),
        "idle_process_write_bytes_delta": int(number(last_sample, "write_bytes") - number(first_sample, "write_bytes")),
        "idle_host_net_rx_bytes_delta": int(number(last_sample, "net_rx_bytes") - number(first_sample, "net_rx_bytes")),
        "idle_host_net_tx_bytes_delta": int(number(last_sample, "net_tx_bytes") - number(first_sample, "net_tx_bytes")),
        "idle_block_reads_completed_delta": int(number(last_sample, "block_reads_completed") - number(first_sample, "block_reads_completed")),
        "idle_block_writes_completed_delta": int(number(last_sample, "block_writes_completed") - number(first_sample, "block_writes_completed")),
        "idle_block_read_bytes_delta": int((number(last_sample, "block_sectors_read") - number(first_sample, "block_sectors_read")) * 512),
        "idle_block_write_bytes_delta": int((number(last_sample, "block_sectors_written") - number(first_sample, "block_sectors_written")) * 512),
        "idle_rpc_latency_mean_ms": statistics.fmean(rpc_latencies_ms),
        "idle_rpc_latency_p95_ms": percentile(rpc_latencies_ms, 0.95),
        "idle_outgoing_peers_mean": statistics.fmean(int(row["outgoing"]) for row in idle_rpc),
        "idle_incoming_peers_mean": statistics.fmean(int(row["incoming"]) for row in idle_rpc),
        "stop_seconds": (stop_end_ns - stop_start_ns) / 1e9,
        "stop_exit_code": stop_rc,
        "node_stopped_log_marker": "Node stopped." in log_text,
        "crash_or_oom_marker": bool(crash_pattern.search(log_text) or crash_pattern.search(dmesg_text)),
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: analyze_warm_idle_runs.py RESULTS_ROOT OUTPUT_DIR")
    results_root = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    run_dirs = sorted(path for path in (results_root / "runs").glob("warm-*") if path.is_dir())
    if len(run_dirs) != 8:
        raise RuntimeError(f"expected 8 warm runs, found {len(run_dirs)}")
    runs = [analyze_run(path) for path in run_dirs]

    with (output_dir / "warm-idle-per-run.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(runs[0].keys()))
        writer.writeheader()
        writer.writerows(runs)

    metrics = [
        "rpc_ready_s",
        "sync_detected_s",
        "p2p_init_log_s",
        "igd_wait_log_s",
        "core_init_log_s",
        "rpc_server_init_log_s",
        "idle_cpu_user_s",
        "idle_cpu_system_s",
        "idle_cpu_total_s",
        "idle_avg_cpu_pct",
        "idle_peak_1s_cpu_pct",
        "idle_avg_rss_kb",
        "idle_peak_rss_kb",
        "idle_minor_faults_delta",
        "idle_major_faults_delta",
        "idle_voluntary_context_switches_delta",
        "idle_nonvoluntary_context_switches_delta",
        "idle_process_read_bytes_delta",
        "idle_process_write_bytes_delta",
        "idle_host_net_rx_bytes_delta",
        "idle_host_net_tx_bytes_delta",
        "idle_block_reads_completed_delta",
        "idle_block_writes_completed_delta",
        "idle_block_read_bytes_delta",
        "idle_block_write_bytes_delta",
        "idle_rpc_latency_mean_ms",
        "idle_rpc_latency_p95_ms",
        "idle_outgoing_peers_mean",
        "idle_incoming_peers_mean",
        "stop_seconds",
    ]

    by_variant: dict[str, dict[str, dict[str, float]]] = {}
    stable_tip: dict[str, dict[str, object]] = {}
    for variant in ("ubuntu24.04", "linux-universal"):
        variant_runs = [run for run in runs if run["variant"] == variant]
        by_variant[variant] = {
            metric: group_stats([float(run[metric]) for run in variant_runs]) for metric in metrics
        }
        stable_runs = [run for run in variant_runs if run["idle_height_delta"] == 0]
        stable_tip[variant] = {
            "n": len(stable_runs),
            "run_ids": [run["run_id"] for run in stable_runs],
            "idle_avg_cpu_pct": group_stats([float(run["idle_avg_cpu_pct"]) for run in stable_runs]) if stable_runs else None,
            "idle_avg_rss_kb": group_stats([float(run["idle_avg_rss_kb"]) for run in stable_runs]) if stable_runs else None,
            "idle_rpc_latency_mean_ms": group_stats([float(run["idle_rpc_latency_mean_ms"]) for run in stable_runs]) if stable_runs else None,
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
        "run_count": len(runs),
        "runs_per_variant": 4,
        "idle_seconds_per_run": 60,
        "total_idle_seconds_per_variant": 240,
        "total_new_blocks_by_variant": {
            variant: sum(int(run["idle_height_delta"]) for run in runs if run["variant"] == variant)
            for variant in ("ubuntu24.04", "linux-universal")
        },
        "variants": by_variant,
        "stable_tip_subset": stable_tip,
        "comparisons": comparisons,
        "all_stop_exit_zero": all(run["stop_exit_code"] == 0 for run in runs),
        "all_node_stopped_marker": all(run["node_stopped_log_marker"] for run in runs),
        "any_crash_or_oom_marker": any(run["crash_or_oom_marker"] for run in runs),
        "binary_sha256_by_variant": {
            variant: sorted({str(run["binary_sha256"]) for run in runs if run["variant"] == variant})
            for variant in ("ubuntu24.04", "linux-universal")
        },
    }
    (output_dir / "warm-idle-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
