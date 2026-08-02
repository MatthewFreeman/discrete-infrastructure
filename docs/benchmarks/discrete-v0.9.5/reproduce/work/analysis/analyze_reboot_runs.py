#!/usr/bin/env python3
import csv
import json
import re
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


def first_rpc_epoch(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("curl_rc") == "0" and row.get("http_code") == "200" and row.get("status") == "OK":
                return int(row["epoch_ns"])
    raise RuntimeError(f"no successful RPC sample in {path}")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: analyze_reboot_runs.py RESULTS_ROOT OUTPUT_DIR")
    results_root = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for run_dir in sorted((results_root / "runs").glob("reboot-*")):
        metadata = read_kv(run_dir / "run-metadata.txt")
        launch_ns = read_int(run_dir / "launch-epoch-ns.txt")
        rpc_ns = first_rpc_epoch(run_dir / "rpc-samples.tsv")
        stop_start_ns = read_int(run_dir / "stop-start-epoch-ns.txt")
        stop_end_ns = read_int(run_dir / "stop-end-epoch-ns.txt")
        pre_stop = json.loads((run_dir / "pre-stop-getinfo.json").read_text(encoding="utf-8"))
        log_text = (run_dir / "discreted.log").read_text(encoding="utf-8", errors="replace")
        kernel_markers = (run_dir / "kernel-error-markers.txt").read_text(encoding="utf-8", errors="replace").strip()
        running_sha_line = (run_dir / "running-binary-sha256.txt").read_text(encoding="utf-8").strip()
        running_sha = running_sha_line.split()[0]
        rows.append({
            "run_id": metadata["run_id"],
            "variant": metadata["variant"],
            "pre_reboot_boot_id": (run_dir / "pre-reboot-boot-id.txt").read_text(encoding="utf-8").strip(),
            "post_reboot_boot_id": (run_dir / "post-reboot-boot-id.txt").read_text(encoding="utf-8").strip(),
            "boot_id_changed": (run_dir / "pre-reboot-boot-id.txt").read_text(encoding="utf-8").strip() != (run_dir / "post-reboot-boot-id.txt").read_text(encoding="utf-8").strip(),
            "running_binary_sha256": running_sha,
            "expected_binary_sha256": metadata["binary_sha256"],
            "running_sha_matches": running_sha == metadata["binary_sha256"],
            "rpc_ready_after_service_launch_s": (rpc_ns - launch_ns) / 1e9,
            "pre_stop_height": int(pre_stop["height"]),
            "pre_stop_last_known_block_index": int(pre_stop["last_known_block_index"]),
            "pre_stop_outgoing_peers": int(pre_stop["outgoing_connections_count"]),
            "pre_stop_incoming_peers": int(pre_stop["incoming_connections_count"]),
            "pre_stop_top_block_hash": pre_stop["top_block_hash"],
            "stop_seconds": (stop_end_ns - stop_start_ns) / 1e9,
            "stop_exit_code": read_int(run_dir / "systemctl-stop-exit-code.txt"),
            "node_stopped_log_marker": "Node stopped." in log_text,
            "kernel_error_markers_empty": kernel_markers == "",
            "sigill_or_crash_log_marker": bool(re.search(r"sigill|illegal instruction|segfault|oom-kill|out of memory", log_text, re.IGNORECASE)),
        })
    if len(rows) != 2:
        raise RuntimeError(f"expected 2 reboot runs, found {len(rows)}")
    with (output_dir / "reboot-per-run.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "run_count": len(rows),
        "all_boot_ids_changed": all(row["boot_id_changed"] for row in rows),
        "all_running_hashes_match": all(row["running_sha_matches"] for row in rows),
        "all_stops_exit_zero": all(row["stop_exit_code"] == 0 for row in rows),
        "all_node_stopped_markers": all(row["node_stopped_log_marker"] for row in rows),
        "all_kernel_error_markers_empty": all(row["kernel_error_markers_empty"] for row in rows),
        "any_sigill_or_crash": any(row["sigill_or_crash_log_marker"] for row in rows),
        "same_final_height": len({row["pre_stop_height"] for row in rows}) == 1,
        "same_final_top_hash": len({row["pre_stop_top_block_hash"] for row in rows}) == 1,
        "runs": rows,
    }
    (output_dir / "reboot-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
