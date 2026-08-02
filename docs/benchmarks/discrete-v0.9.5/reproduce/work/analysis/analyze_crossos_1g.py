#!/usr/bin/env python3
"""Analyze paired Discrete Universal Ubuntu/Debian runs under mem=1G."""

from __future__ import annotations

import csv
import itertools
import json
import math
import statistics
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[2]
RAW_ROOT = WORKSPACE / "outputs" / "cross-os-1g-v0.9.5" / "raw"
OUT_ROOT = WORKSPACE / "outputs" / "cross-os-1g-v0.9.5" / "analysis"
CLK_TCK = 100


def read_kv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip()
    return values


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise RuntimeError(f"empty TSV: {path}")
    missing = [key for key, value in rows[0].items() if value is None]
    if missing:
        raise RuntimeError(f"malformed TSV: {path}")
    return rows


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
    observed = abs(statistics.fmean(differences))
    candidates = (
        abs(statistics.fmean(diff * sign for diff, sign in zip(differences, signs)))
        for signs in itertools.product((-1, 1), repeat=len(differences))
    )
    extreme = sum(candidate >= observed - 1e-12 for candidate in candidates)
    return extreme / (2 ** len(differences))


def exact_paired_bootstrap_ci(differences: list[float]) -> tuple[float, float]:
    means = [
        statistics.fmean(differences[index] for index in selection)
        for selection in itertools.product(range(len(differences)), repeat=len(differences))
    ]
    return percentile(means, 0.025), percentile(means, 0.975)


def paired_summary(rows: list[dict[str, float | int | str]], metric: str) -> dict[str, float | int]:
    ubuntu = [float(row[metric]) for row in rows if row["os"] == "ubuntu24.04"]
    debian = [float(row[metric]) for row in rows if row["os"] == "debian12"]
    lookup = {(int(row["pair"]), str(row["os"])): float(row[metric]) for row in rows}
    differences = [lookup[(pair, "ubuntu24.04")] - lookup[(pair, "debian12")] for pair in range(1, 7)]
    ci_low, ci_high = exact_paired_bootstrap_ci(differences)
    debian_mean = statistics.fmean(debian)
    return {
        "ubuntu_mean": statistics.fmean(ubuntu),
        "ubuntu_sd": statistics.stdev(ubuntu),
        "debian_mean": debian_mean,
        "debian_sd": statistics.stdev(debian),
        "paired_mean_diff_ubuntu_minus_debian": statistics.fmean(differences),
        "paired_median_diff_ubuntu_minus_debian": statistics.median(differences),
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


def causal_summary(
    native_rows: list[dict[str, float | int | str]],
    madvise_rows: list[dict[str, float | int | str]],
    metric: str,
) -> dict[str, float | int]:
    native = {(int(row["pair"]), str(row["os"])): float(row[metric]) for row in native_rows}
    madvise = {(int(row["pair"]), str(row["os"])): float(row[metric]) for row in madvise_rows}
    effects = []
    for pair in range(1, 7):
        native_gap = native[(pair, "debian12")] - native[(pair, "ubuntu24.04")]
        madvise_gap = madvise[(pair, "debian12")] - madvise[(pair, "ubuntu24.04")]
        effects.append(madvise_gap - native_gap)
    ci_low, ci_high = exact_paired_bootstrap_ci(effects)
    debian_native = [native[(pair, "debian12")] for pair in range(1, 7)]
    debian_madvise = [madvise[(pair, "debian12")] for pair in range(1, 7)]
    ubuntu_native = [native[(pair, "ubuntu24.04")] for pair in range(1, 7)]
    ubuntu_madvise = [madvise[(pair, "ubuntu24.04")] for pair in range(1, 7)]
    native_mean = statistics.fmean(debian_native)
    return {
        "debian_native_always_mean": native_mean,
        "debian_madvise_mean": statistics.fmean(debian_madvise),
        "ubuntu_control_native_series_mean": statistics.fmean(ubuntu_native),
        "ubuntu_control_madvise_series_mean": statistics.fmean(ubuntu_madvise),
        "adjusted_effect_madvise_minus_always": statistics.fmean(effects),
        "adjusted_effect_percent_of_debian_native_mean": (
            statistics.fmean(effects) / native_mean * 100 if native_mean else math.nan
        ),
        "paired_bootstrap_95_ci_low": ci_low,
        "paired_bootstrap_95_ci_high": ci_high,
        "exact_sign_flip_two_sided_p": exact_sign_flip_pvalue(effects),
        "effect_negative_count": sum(effect < 0 for effect in effects),
        "effect_positive_count": sum(effect > 0 for effect in effects),
        "ties": sum(effect == 0 for effect in effects),
    }


def assert_lifecycle(run_dir: Path, summary: dict[str, str], peer_key: str) -> None:
    if summary.get("stop_rc") != "0" or summary.get("fatal_pattern_matches") != "0":
        raise RuntimeError(f"invalid lifecycle result: {run_dir}")
    if int(summary.get(peer_key, "-1")) != 0:
        raise RuntimeError(f"inbound peer detected: {run_dir}")


def memory_metrics(samples: list[dict[str, str]], prefix: str) -> dict[str, float | int]:
    first, last = samples[0], samples[-1]
    swap_used = [integer(row, "swap_total_kb") - integer(row, "swap_free_kb") for row in samples]
    return {
        f"{prefix}mem_available_mean_kb": statistics.fmean(integer(row, "mem_available_kb") for row in samples),
        f"{prefix}mem_available_min_kb": min(integer(row, "mem_available_kb") for row in samples),
        f"{prefix}host_unavailable_max_kb": max(
            integer(row, "mem_total_kb") - integer(row, "mem_available_kb") for row in samples
        ),
        f"{prefix}cached_mean_kb": statistics.fmean(integer(row, "cached_kb") for row in samples),
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


def analyze_cold(run_dir: Path, os_name: str, pair: int) -> dict[str, float | int | str]:
    summary = read_kv(run_dir / "run-summary.txt")
    assert_lifecycle(run_dir, summary, "incoming_at_target")
    target_epoch = int((run_dir / "target-epoch-ns.txt").read_text(encoding="utf-8").strip())
    all_samples = read_tsv(run_dir / "process-host-samples.tsv")
    samples = [row for row in all_samples if int(row["epoch_ns"]) <= target_epoch]
    if len(samples) < 30:
        raise RuntimeError(f"insufficient cold samples: {run_dir}")
    first, last = samples[0], samples[-1]
    wall = float(summary["wall_to_target_seconds"])
    height = int(summary["observed_target_height"])
    cpu_total = (integer(last, "utime_ticks") + integer(last, "stime_ticks")) / CLK_TCK
    rpc = [
        float(row["time_total_s"]) * 1000
        for row in read_tsv(run_dir / "rpc-samples.tsv")
        if int(row["epoch_ns"]) <= target_epoch and row["http_code"] == "200"
    ]
    result: dict[str, float | int | str] = {
        "pair": pair,
        "os": os_name,
        "run_id": summary["run_id"],
        "wall_to_target_s": wall,
        "observed_height": height,
        "normalized_wall_to_4500_s": wall * 4500 / height,
        "cpu_total_to_target_s": cpu_total,
        "cpu_total_per_observed_block_ms": cpu_total * 1000 / height,
        "rss_average_to_target_kb": statistics.fmean(integer(row, "vmrss_kb") for row in samples),
        "rss_peak_kb": max(integer(row, "vmhwm_kb") for row in all_samples),
        "major_faults_to_target": integer(last, "majflt"),
        "rpc_latency_mean_ms": statistics.fmean(rpc),
        "rpc_latency_p95_ms": percentile(rpc, 0.95),
        "stop_seconds": float(summary["stop_seconds"]),
    }
    result.update(memory_metrics(samples, ""))
    return result


def analyze_warm(run_dir: Path, os_name: str, pair: int) -> dict[str, float | int | str]:
    summary = read_kv(run_dir / "run-summary.txt")
    assert_lifecycle(run_dir, summary, "incoming_at_idle_start")
    idle_start = int((run_dir / "idle-start-epoch-ns.txt").read_text(encoding="utf-8").strip())
    idle_end = int((run_dir / "idle-end-epoch-ns.txt").read_text(encoding="utf-8").strip())
    all_samples = read_tsv(run_dir / "process-host-samples.tsv")
    samples = [row for row in all_samples if idle_start <= int(row["epoch_ns"]) <= idle_end]
    if len(samples) < 100:
        raise RuntimeError(f"insufficient warm idle samples: {run_dir}")
    first, last = samples[0], samples[-1]
    sampled_seconds = (integer(last, "epoch_ns") - integer(first, "epoch_ns")) / 1_000_000_000
    cpu_total = (delta(first, last, "utime_ticks") + delta(first, last, "stime_ticks")) / CLK_TCK
    rpc = [
        float(row["time_total_s"]) * 1000
        for row in read_tsv(run_dir / "rpc-samples.tsv")
        if idle_start <= int(row["epoch_ns"]) <= idle_end and row["http_code"] == "200"
    ]
    start_info = json.loads((run_dir / "idle-start-getinfo.json").read_text(encoding="utf-8"))
    end_info = json.loads((run_dir / "idle-end-getinfo.json").read_text(encoding="utf-8"))
    result: dict[str, float | int | str] = {
        "pair": pair,
        "os": os_name,
        "run_id": summary["run_id"],
        "first_rpc_seconds": float(summary["first_rpc_seconds"]),
        "sync_ready_seconds": float(summary["sync_ready_seconds"]),
        "idle_actual_seconds": float(summary["idle_actual_seconds"]),
        "idle_sampled_seconds": sampled_seconds,
        "idle_cpu_total_s": cpu_total,
        "idle_cpu_percent_one_core": cpu_total / sampled_seconds * 100,
        "idle_rss_average_kb": statistics.fmean(integer(row, "vmrss_kb") for row in samples),
        "idle_rss_peak_kb": max(integer(row, "vmrss_kb") for row in samples),
        "lifetime_rss_hwm_kb": max(integer(row, "vmhwm_kb") for row in all_samples),
        "idle_major_faults_delta": delta(first, last, "majflt"),
        "idle_rpc_latency_mean_ms": statistics.fmean(rpc),
        "idle_rpc_latency_p95_ms": percentile(rpc, 0.95),
        "stop_seconds": float(summary["stop_seconds"]),
        "idle_start_height": int(summary["idle_start_height"]),
        "idle_end_height": int(summary["idle_end_height"]),
        "idle_start_hash": str(start_info["top_block_hash"]),
        "idle_end_hash": str(end_info["top_block_hash"]),
    }
    result.update(memory_metrics(samples, "idle_"))
    result.update(memory_metrics(all_samples, "lifetime_"))
    return result


def write_csv(path: Path, rows: list[dict[str, float | int | str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    cold_rows: list[dict[str, float | int | str]] = []
    warm_rows: list[dict[str, float | int | str]] = []
    cold_madvise_rows: list[dict[str, float | int | str]] = []
    warm_madvise_rows: list[dict[str, float | int | str]] = []
    for pair in range(1, 7):
        for os_name, folder, suffix in (
            ("ubuntu24.04", "ubuntu", "ubuntu24.04"),
            ("debian12", "debian", "debian12"),
        ):
            cold_dir = RAW_ROOT / "cold" / folder / f"crossos-1g-cold-{pair:02d}-{suffix}"
            warm_dir = RAW_ROOT / "warm" / folder / f"crossos-1g-warm-{pair:02d}-{suffix}"
            if not cold_dir.is_dir() or not warm_dir.is_dir():
                raise RuntimeError(f"missing pair {pair:02d} for {os_name}")
            cold_rows.append(analyze_cold(cold_dir, os_name, pair))
            warm_rows.append(analyze_warm(warm_dir, os_name, pair))

        ubuntu, debian = warm_rows[-2:]
        for key in ("idle_start_height", "idle_end_height", "idle_start_hash", "idle_end_hash"):
            if ubuntu[key] != debian[key]:
                raise RuntimeError(f"warm pair {pair:02d} mismatched {key}")

    for pair, ordinal in enumerate(range(7, 13), start=1):
        pair_warm_rows = []
        for os_name, folder, suffix in (
            ("ubuntu24.04", "ubuntu", "ubuntu24.04"),
            ("debian12", "debian", "debian12"),
        ):
            cold_dir = RAW_ROOT / "cold" / folder / f"crossos-1g-cold-{ordinal:02d}-{suffix}"
            warm_dir = RAW_ROOT / "warm" / folder / f"crossos-1g-warm-{ordinal:02d}-{suffix}"
            if not cold_dir.is_dir() or not warm_dir.is_dir():
                raise RuntimeError(f"missing madvise ordinal {ordinal:02d} for {os_name}")
            cold_madvise_rows.append(analyze_cold(cold_dir, os_name, pair))
            pair_warm_rows.append(analyze_warm(warm_dir, os_name, pair))
        ubuntu, debian = pair_warm_rows
        for key in ("idle_start_height", "idle_end_height", "idle_start_hash", "idle_end_hash"):
            if ubuntu[key] != debian[key]:
                raise RuntimeError(f"madvise warm pair {ordinal:02d} mismatched {key}")
        warm_madvise_rows.extend(pair_warm_rows)

    cold_metrics = [
        key for key, value in cold_rows[0].items()
        if key not in {"pair", "os", "run_id", "observed_height"} and isinstance(value, (int, float))
    ]
    warm_metrics = [
        key for key, value in warm_rows[0].items()
        if key not in {
            "pair", "os", "run_id", "idle_start_height", "idle_end_height",
            "idle_start_hash", "idle_end_hash",
        } and isinstance(value, (int, float))
    ]
    stats = {
        "method": {
            "pairs_per_series": 6,
            "difference": "Ubuntu minus Debian within the same simultaneous pair",
            "confidence_interval": "exact paired nonparametric bootstrap over all 6^6 resamples",
            "p_value": "exact two-sided paired sign-flip test over all 2^6 assignments",
        },
        "native_cross_os": {
            "cold": {metric: paired_summary(cold_rows, metric) for metric in cold_metrics},
            "warm": {metric: paired_summary(warm_rows, metric) for metric in warm_metrics},
        },
        "madvise_cross_os": {
            "cold": {metric: paired_summary(cold_madvise_rows, metric) for metric in cold_metrics},
            "warm": {metric: paired_summary(warm_madvise_rows, metric) for metric in warm_metrics},
        },
        "debian_madvise_effect_adjusted_by_ubuntu_control": {
            "cold": {metric: causal_summary(cold_rows, cold_madvise_rows, metric) for metric in cold_metrics},
            "warm": {metric: causal_summary(warm_rows, warm_madvise_rows, metric) for metric in warm_metrics},
        },
    }
    write_csv(OUT_ROOT / "cold-per-run.csv", cold_rows)
    write_csv(OUT_ROOT / "warm-per-run.csv", warm_rows)
    write_csv(OUT_ROOT / "cold-madvise-per-run.csv", cold_madvise_rows)
    write_csv(OUT_ROOT / "warm-madvise-per-run.csv", warm_madvise_rows)
    (OUT_ROOT / "comparison-statistics.json").write_text(
        json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    for section, metrics in (
        ("cold", ("normalized_wall_to_4500_s", "cpu_total_per_observed_block_ms", "rss_peak_kb", "mem_available_min_kb")),
        ("warm", ("first_rpc_seconds", "sync_ready_seconds", "idle_rss_average_kb", "idle_mem_available_min_kb")),
    ):
        for metric in metrics:
            item = stats["native_cross_os"][section][metric]
            print(
                f"native.{section}.{metric}: U={item['ubuntu_mean']:.6f} D={item['debian_mean']:.6f} "
                f"U-D={item['paired_mean_diff_ubuntu_minus_debian']:.6f} "
                f"CI=[{item['paired_bootstrap_95_ci_low']:.6f},{item['paired_bootstrap_95_ci_high']:.6f}] "
                f"p={item['exact_sign_flip_two_sided_p']:.5f}"
            )
            effect = stats["debian_madvise_effect_adjusted_by_ubuntu_control"][section][metric]
            print(
                f"effect.{section}.{metric}: adjusted_madvise-always="
                f"{effect['adjusted_effect_madvise_minus_always']:.6f} "
                f"CI=[{effect['paired_bootstrap_95_ci_low']:.6f},{effect['paired_bootstrap_95_ci_high']:.6f}] "
                f"p={effect['exact_sign_flip_two_sided_p']:.5f}"
            )


if __name__ == "__main__":
    main()
