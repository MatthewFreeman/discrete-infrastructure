#!/usr/bin/env python3
"""Analyze Discrete Universal Ubuntu/Debian runs under a mem=512M kernel cap."""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import statistics
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[2]
RAW_ROOT = WORKSPACE / "outputs" / "cross-os-512m-v0.9.5" / "raw"
OUT_ROOT = WORKSPACE / "outputs" / "cross-os-512m-v0.9.5" / "analysis"
EXPECTED_BINARY_SHA256 = "6296755aad63d66f80150383a2a30a15876f766fa05d68733653f0c1063ae30e"
CLK_TCK = 100


def read_kv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value.strip()
    return result


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows or any(value is None for value in rows[0].values()):
        raise RuntimeError(f"empty or malformed TSV: {path}")
    return rows


def integer(row: dict[str, str], key: str) -> int:
    return int(row[key])


def delta(first: dict[str, str], last: dict[str, str], key: str) -> int:
    return integer(last, key) - integer(first, key)


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def exact_sign_flip_pvalue(differences: list[float]) -> float:
    observed = abs(statistics.fmean(differences))
    candidates = (
        abs(statistics.fmean(diff * sign for diff, sign in zip(differences, signs)))
        for signs in itertools.product((-1, 1), repeat=len(differences))
    )
    return sum(candidate >= observed - 1e-12 for candidate in candidates) / (2 ** len(differences))


def exact_paired_bootstrap_ci(differences: list[float]) -> tuple[float, float]:
    means = [
        statistics.fmean(differences[index] for index in selection)
        for selection in itertools.product(range(len(differences)), repeat=len(differences))
    ]
    return percentile(means, 0.025), percentile(means, 0.975)


def paired_summary(rows: list[dict[str, float | int | str]], metric: str) -> dict[str, float | int]:
    lookup = {(int(row["pair"]), str(row["os"])): float(row[metric]) for row in rows}
    ubuntu = [lookup[(pair, "ubuntu24.04")] for pair in range(1, 7)]
    debian = [lookup[(pair, "debian12")] for pair in range(1, 7)]
    differences = [ubuntu[index] - debian[index] for index in range(6)]
    ci_low, ci_high = exact_paired_bootstrap_ci(differences)
    debian_mean = statistics.fmean(debian)
    return {
        "ubuntu_mean": statistics.fmean(ubuntu),
        "ubuntu_sd": statistics.stdev(ubuntu),
        "debian_mean": debian_mean,
        "debian_sd": statistics.stdev(debian),
        "paired_mean_diff_ubuntu_minus_debian": statistics.fmean(differences),
        "relative_diff_percent_of_debian_mean": (
            statistics.fmean(differences) / debian_mean * 100 if debian_mean else math.nan
        ),
        "paired_bootstrap_95_ci_low": ci_low,
        "paired_bootstrap_95_ci_high": ci_high,
        "exact_sign_flip_two_sided_p": exact_sign_flip_pvalue(differences),
        "ubuntu_lower_count": sum(diff < 0 for diff in differences),
        "debian_lower_count": sum(diff > 0 for diff in differences),
        "ties": sum(diff == 0 for diff in differences),
    }


def validate_run(run_dir: Path, summary: dict[str, str], incoming_key: str) -> None:
    if summary.get("stop_rc") != "0" or summary.get("fatal_pattern_matches") != "0":
        raise RuntimeError(f"lifecycle failure: {run_dir}")
    if int(summary.get(incoming_key, "-1")) != 0:
        raise RuntimeError(f"inbound peer contaminated run: {run_dir}")
    pre = (run_dir / "host-pre-run.txt").read_text(encoding="utf-8")
    if EXPECTED_BINARY_SHA256 not in pre or "mem=512M" not in pre:
        raise RuntimeError(f"provenance or memory limit mismatch: {run_dir}")
    if "/sys/kernel/mm/transparent_hugepage/enabled=always madvise [never]" not in pre:
        raise RuntimeError(f"unexpected THP policy: {run_dir}")


def sample_metrics(samples: list[dict[str, str]], prefix: str = "") -> dict[str, float | int]:
    first, last = samples[0], samples[-1]
    elapsed = (integer(last, "epoch_ns") - integer(first, "epoch_ns")) / 1_000_000_000
    cpu_seconds = (
        delta(first, last, "utime_ticks") + delta(first, last, "stime_ticks")
    ) / CLK_TCK
    swap_used = [integer(row, "swap_total_kb") - integer(row, "swap_free_kb") for row in samples]
    block_reads = delta(first, last, "block_reads_completed")
    block_writes = delta(first, last, "block_writes_completed")
    block_read_bytes = delta(first, last, "block_sectors_read") * 512
    block_write_bytes = delta(first, last, "block_sectors_written") * 512
    net_rx_bytes = delta(first, last, "net_rx_bytes")
    net_tx_bytes = delta(first, last, "net_tx_bytes")
    return {
        f"{prefix}sampled_seconds": elapsed,
        f"{prefix}process_cpu_seconds": cpu_seconds,
        f"{prefix}process_cpu_percent_one_core": cpu_seconds / elapsed * 100,
        f"{prefix}rss_average_kb": statistics.fmean(integer(row, "vmrss_kb") for row in samples),
        f"{prefix}rss_peak_kb": max(integer(row, "vmhwm_kb") for row in samples),
        f"{prefix}minor_faults_delta": delta(first, last, "minflt"),
        f"{prefix}major_faults_delta": delta(first, last, "majflt"),
        f"{prefix}voluntary_context_switches_delta": delta(first, last, "voluntary_ctxt"),
        f"{prefix}nonvoluntary_context_switches_delta": delta(first, last, "nonvoluntary_ctxt"),
        f"{prefix}process_read_bytes_delta": delta(first, last, "read_bytes"),
        f"{prefix}process_write_bytes_delta": delta(first, last, "write_bytes"),
        f"{prefix}host_block_reads_completed_delta": block_reads,
        f"{prefix}host_block_writes_completed_delta": block_writes,
        f"{prefix}host_block_read_iops": block_reads / elapsed,
        f"{prefix}host_block_write_iops": block_writes / elapsed,
        f"{prefix}host_block_read_bytes_delta": block_read_bytes,
        f"{prefix}host_block_write_bytes_delta": block_write_bytes,
        f"{prefix}host_block_read_mib_per_s": block_read_bytes / elapsed / 1024 / 1024,
        f"{prefix}host_block_write_mib_per_s": block_write_bytes / elapsed / 1024 / 1024,
        f"{prefix}host_net_rx_bytes_delta": net_rx_bytes,
        f"{prefix}host_net_tx_bytes_delta": net_tx_bytes,
        f"{prefix}host_net_rx_kib_per_s": net_rx_bytes / elapsed / 1024,
        f"{prefix}host_net_tx_kib_per_s": net_tx_bytes / elapsed / 1024,
        f"{prefix}mem_available_mean_kb": statistics.fmean(integer(row, "mem_available_kb") for row in samples),
        f"{prefix}mem_available_min_kb": min(integer(row, "mem_available_kb") for row in samples),
        f"{prefix}swap_used_max_kb": max(swap_used),
        f"{prefix}pswpin_delta": delta(first, last, "vm_pswpin"),
        f"{prefix}pswpout_delta": delta(first, last, "vm_pswpout"),
        f"{prefix}pgscan_kswapd_delta": delta(first, last, "vm_pgscan_kswapd"),
        f"{prefix}pgscan_direct_delta": delta(first, last, "vm_pgscan_direct"),
        f"{prefix}pgsteal_kswapd_delta": delta(first, last, "vm_pgsteal_kswapd"),
        f"{prefix}pgsteal_direct_delta": delta(first, last, "vm_pgsteal_direct"),
        f"{prefix}oom_kill_delta": delta(first, last, "vm_oom_kill"),
        f"{prefix}psi_memory_some_delta_us": delta(first, last, "psi_memory_some_total_us"),
        f"{prefix}psi_memory_full_delta_us": delta(first, last, "psi_memory_full_total_us"),
    }


def rpc_metrics(run_dir: Path, start_ns: int, end_ns: int, prefix: str = "") -> dict[str, float]:
    values = [
        float(row["time_total_s"]) * 1000
        for row in read_tsv(run_dir / "rpc-samples.tsv")
        if start_ns <= int(row["epoch_ns"]) <= end_ns and row["http_code"] == "200"
    ]
    if not values:
        raise RuntimeError(f"no successful RPC samples: {run_dir}")
    return {
        f"{prefix}rpc_latency_mean_ms": statistics.fmean(values),
        f"{prefix}rpc_latency_p95_ms": percentile(values, 0.95),
    }


def analyze_cold(run_dir: Path, os_name: str, pair: int) -> dict[str, float | int | str]:
    summary = read_kv(run_dir / "run-summary.txt")
    validate_run(run_dir, summary, "incoming_at_target")
    target_ns = int((run_dir / "target-epoch-ns.txt").read_text(encoding="utf-8").strip())
    samples = [row for row in read_tsv(run_dir / "process-host-samples.tsv") if int(row["epoch_ns"]) <= target_ns]
    if len(samples) < 30:
        raise RuntimeError(f"insufficient cold samples: {run_dir}")
    result: dict[str, float | int | str] = {
        "pair": pair,
        "os": os_name,
        "run_id": summary["run_id"],
        "wall_to_target_s": float(summary["wall_to_target_seconds"]),
        "observed_height": int(summary["observed_target_height"]),
        "outgoing_peers": int(summary["outgoing_at_target"]),
        "stop_seconds": float(summary["stop_seconds"]),
    }
    result.update(sample_metrics(samples))
    result["cpu_per_observed_block_ms"] = float(result["process_cpu_seconds"]) * 1000 / int(result["observed_height"])
    result.update(rpc_metrics(run_dir, int(samples[0]["epoch_ns"]), target_ns))
    return result


def analyze_warm(run_dir: Path, os_name: str, pair: int) -> dict[str, float | int | str]:
    summary = read_kv(run_dir / "run-summary.txt")
    validate_run(run_dir, summary, "incoming_at_idle_start")
    if "OK" not in (run_dir / "snapshot-verification.txt").read_text(encoding="utf-8"):
        raise RuntimeError(f"snapshot verification failed: {run_dir}")
    idle_start = int((run_dir / "idle-start-epoch-ns.txt").read_text(encoding="utf-8").strip())
    idle_end = int((run_dir / "idle-end-epoch-ns.txt").read_text(encoding="utf-8").strip())
    all_samples = read_tsv(run_dir / "process-host-samples.tsv")
    idle_samples = [row for row in all_samples if idle_start <= int(row["epoch_ns"]) <= idle_end]
    if len(idle_samples) < 100:
        raise RuntimeError(f"insufficient warm samples: {run_dir}")
    result: dict[str, float | int | str] = {
        "pair": pair,
        "os": os_name,
        "run_id": summary["run_id"],
        "first_rpc_seconds": float(summary["first_rpc_seconds"]),
        "sync_ready_seconds": float(summary["sync_ready_seconds"]),
        "idle_actual_seconds": float(summary["idle_actual_seconds"]),
        "idle_start_height": int(summary["idle_start_height"]),
        "idle_end_height": int(summary["idle_end_height"]),
        "idle_start_hash": summary["idle_start_hash"],
        "idle_end_hash": summary["idle_end_hash"],
        "outgoing_peers": int(summary["outgoing_at_idle_start"]),
        "stop_seconds": float(summary["stop_seconds"]),
    }
    result.update(sample_metrics(idle_samples, "idle_"))
    result.update(sample_metrics(all_samples, "lifetime_"))
    result.update(rpc_metrics(run_dir, idle_start, idle_end, "idle_"))
    return result


def validate_reboot(run_dir: Path) -> dict[str, object]:
    summary = read_kv(run_dir / "run-summary.txt")
    required = {"final_stop_rc": "0", "fatal_pattern_matches": "0", "daemon_enabled": "no", "monitor_enabled": "no"}
    if any(summary.get(key) != value for key, value in required.items()):
        raise RuntimeError(f"reboot lifecycle failure: {run_dir}")
    boot_ids = [(run_dir / name).read_text(encoding="utf-8").strip() for name in (
        "boot-id-before.txt", "boot-id-cycle-1.txt", "boot-id-cycle-2.txt"
    )]
    if len(set(boot_ids)) != 3:
        raise RuntimeError(f"reboot boot IDs not unique: {run_dir}")
    cycles = []
    for cycle in (1, 2):
        text = (run_dir / f"cycle-{cycle}-summary.txt").read_text(encoding="utf-8")
        values = read_kv(run_dir / f"cycle-{cycle}-summary.txt")
        memory = {
            line.split(":", 1)[0]: int(line.split()[1])
            for line in text.splitlines()
            if line.startswith(("MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:"))
        }
        if "mem=512M" not in text or "[never]" not in text or int(values["outgoing"]) <= 0:
            raise RuntimeError(f"reboot cycle validation failed: {run_dir} cycle {cycle}")
        cycles.append({
            "cycle": cycle,
            "boot_id": values["boot_id"],
            "height": int(values["height"]),
            "outgoing": int(values["outgoing"]),
            "mem_total_kb": memory["MemTotal"],
            "mem_available_kb": memory["MemAvailable"],
            "swap_used_kb": memory["SwapTotal"] - memory["SwapFree"],
        })
    return {"run_id": summary["run_id"], "boot_ids": boot_ids, "cycles": cycles, "final_stop_rc": 0, "fatal": 0}


def write_csv(path: Path, rows: list[dict[str, float | int | str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_manifest() -> None:
    lines = []
    for path in sorted(item for item in RAW_ROOT.rglob("*") if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(RAW_ROOT).as_posix()}")
    with (OUT_ROOT / "raw-file-sha256.txt").open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    cold_rows: list[dict[str, float | int | str]] = []
    warm_rows: list[dict[str, float | int | str]] = []
    for pair in range(1, 7):
        for os_name, folder, suffix in (
            ("ubuntu24.04", "ubuntu", "ubuntu24.04"),
            ("debian12", "debian", "debian12"),
        ):
            cold_dir = RAW_ROOT / "cold" / folder / f"crossos-512m-cold-{pair:02d}-{suffix}"
            warm_dir = RAW_ROOT / "warm" / folder / f"crossos-512m-warm-{pair:02d}-{suffix}"
            cold_rows.append(analyze_cold(cold_dir, os_name, pair))
            warm_rows.append(analyze_warm(warm_dir, os_name, pair))
        ubuntu, debian = warm_rows[-2:]
        for key in ("idle_start_height", "idle_end_height", "idle_start_hash", "idle_end_hash"):
            if ubuntu[key] != debian[key]:
                raise RuntimeError(f"warm pair {pair:02d} mismatched {key}")

    def numeric_metrics(rows: list[dict[str, float | int | str]], excluded: set[str]) -> list[str]:
        return [key for key, value in rows[0].items() if key not in excluded and isinstance(value, (int, float))]

    cold_metrics = numeric_metrics(cold_rows, {"pair", "observed_height", "outgoing_peers"})
    warm_metrics = numeric_metrics(warm_rows, {
        "pair", "idle_start_height", "idle_end_height", "outgoing_peers"
    })
    stats = {
        "method": {
            "pairs": 6,
            "difference": "Ubuntu minus Debian within each simultaneous pair",
            "confidence_interval": "exact paired bootstrap over all 6^6 resamples",
            "p_value": "exact two-sided sign-flip test over all 2^6 assignments",
        },
        "cold": {metric: paired_summary(cold_rows, metric) for metric in cold_metrics},
        "warm": {metric: paired_summary(warm_rows, metric) for metric in warm_metrics},
    }
    reboot = {
        "ubuntu24.04": validate_reboot(RAW_ROOT / "reboot" / "ubuntu" / "crossos-512m-reboot-01-ubuntu24.04"),
        "debian12": validate_reboot(RAW_ROOT / "reboot" / "debian" / "crossos-512m-reboot-01-debian12"),
        "limitation": "monitor runtime TSV was not copied from /run before monitor stop; cycle summaries and logs remain valid",
    }
    write_csv(OUT_ROOT / "cold-per-run.csv", cold_rows)
    write_csv(OUT_ROOT / "warm-per-run.csv", warm_rows)
    (OUT_ROOT / "comparison-statistics.json").write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT_ROOT / "reboot-validation.json").write_text(json.dumps(reboot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_manifest()

    for section, metrics in (
        ("cold", ("wall_to_target_s", "cpu_per_observed_block_ms", "rss_peak_kb", "mem_available_min_kb")),
        ("warm", ("first_rpc_seconds", "sync_ready_seconds", "idle_process_cpu_percent_one_core", "idle_rss_average_kb", "idle_mem_available_min_kb")),
    ):
        for metric in metrics:
            item = stats[section][metric]
            print(
                f"{section}.{metric}: U={item['ubuntu_mean']:.6f} D={item['debian_mean']:.6f} "
                f"U-D={item['paired_mean_diff_ubuntu_minus_debian']:.6f} "
                f"CI=[{item['paired_bootstrap_95_ci_low']:.6f},{item['paired_bootstrap_95_ci_high']:.6f}] "
                f"p={item['exact_sign_flip_two_sided_p']:.5f}"
            )


if __name__ == "__main__":
    main()
