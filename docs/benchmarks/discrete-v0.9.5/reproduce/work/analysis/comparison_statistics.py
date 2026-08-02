#!/usr/bin/env python3
import csv
import itertools
import json
import random
import statistics
import sys
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def exact_permutation_p(a: list[float], b: list[float]) -> float:
    observed = abs(statistics.fmean(a) - statistics.fmean(b))
    pooled = a + b
    extreme = 0
    total = 0
    indices = range(len(pooled))
    for group_a_indices in itertools.combinations(indices, len(a)):
        group_a_set = set(group_a_indices)
        perm_a = [pooled[i] for i in indices if i in group_a_set]
        perm_b = [pooled[i] for i in indices if i not in group_a_set]
        difference = abs(statistics.fmean(perm_a) - statistics.fmean(perm_b))
        if difference >= observed - 1e-12:
            extreme += 1
        total += 1
    return extreme / total


def bootstrap_difference_ci(a: list[float], b: list[float], rng: random.Random, iterations: int = 50000) -> tuple[float, float]:
    differences = []
    for _ in range(iterations):
        sample_a = [rng.choice(a) for _ in a]
        sample_b = [rng.choice(b) for _ in b]
        differences.append(statistics.fmean(sample_a) - statistics.fmean(sample_b))
    differences.sort()
    return differences[int(iterations * 0.025)], differences[int(iterations * 0.975)]


def compare(rows: list[dict[str, str]], metric: str, rng: random.Random) -> dict[str, float]:
    ubuntu = [float(row[metric]) for row in rows if row["variant"] == "ubuntu24.04"]
    universal = [float(row[metric]) for row in rows if row["variant"] == "linux-universal"]
    ubuntu_mean = statistics.fmean(ubuntu)
    universal_mean = statistics.fmean(universal)
    ci_low, ci_high = bootstrap_difference_ci(ubuntu, universal, rng)
    return {
        "ubuntu_mean": ubuntu_mean,
        "universal_mean": universal_mean,
        "ubuntu_minus_universal": ubuntu_mean - universal_mean,
        "ubuntu_vs_universal_pct": (ubuntu_mean / universal_mean - 1) * 100 if universal_mean else float("nan"),
        "exact_two_sided_permutation_p": exact_permutation_p(ubuntu, universal),
        "bootstrap_95pct_ci_difference_low": ci_low,
        "bootstrap_95pct_ci_difference_high": ci_high,
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: comparison_statistics.py ANALYSIS_DIR")
    analysis_dir = Path(sys.argv[1])
    cold = read_csv(analysis_dir / "cold-sync-per-run.csv")
    warm = read_csv(analysis_dir / "warm-idle-per-run.csv")
    rng = random.Random(0xD15C0)
    cold_metrics = [
        "height_4500_s",
        "blocks_per_s_to_4500",
        "cpu_total_s_to_4500",
        "avg_rss_kb_to_4500",
        "peak_rss_kb_to_4500",
        "rpc_latency_mean_ms_to_4500",
        "stop_seconds",
    ]
    warm_metrics = [
        "rpc_ready_s",
        "core_init_log_s",
        "idle_avg_cpu_pct",
        "idle_avg_rss_kb",
        "idle_peak_rss_kb",
        "idle_rpc_latency_mean_ms",
        "stop_seconds",
    ]
    result = {
        "method": {
            "groups": "4 Ubuntu-native runs vs 4 Universal runs",
            "permutation": "exact two-sided difference-in-means test across all 70 label assignments",
            "confidence_interval": "independent nonparametric bootstrap, 50000 resamples, deterministic seed",
            "warning": "small n and live-peer VPS variance; treat p-values as descriptive, not proof",
        },
        "cold_sync": {metric: compare(cold, metric, rng) for metric in cold_metrics},
        "warm_idle": {metric: compare(warm, metric, rng) for metric in warm_metrics},
    }
    (analysis_dir / "comparison-statistics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
