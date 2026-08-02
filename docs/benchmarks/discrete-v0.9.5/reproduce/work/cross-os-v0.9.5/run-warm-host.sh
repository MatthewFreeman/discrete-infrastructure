#!/usr/bin/env bash
set -euo pipefail

readonly RELEASE=v.0.9.5
readonly ROOT=/opt/discrete-benchmark
readonly BINARY="$ROOT/releases/$RELEASE/linux-universal/discreted"
readonly EXPECTED_BINARY_SHA256=6296755aad63d66f80150383a2a30a15876f766fa05d68733653f0c1063ae30e
readonly SNAPSHOT="$ROOT/data/$RELEASE/cross-os/canonical-h4656"
readonly EXPECTED_P2P_SHA256=3430f8030f676e2a74ecb35ca52e79e584448f83f925621d27d3672dc2ab7d5b
readonly EXPECTED_POOL_SHA256=3f5bc7bb025d35e40631578c1183bf1484e5ac5744569e1a6054887c5c1057b3
readonly EXPECTED_DATA_SHA256=7459fb2adcf2d5ca08aeaddf7c81feea9d5d84d3c97ae4c3e4f7eaf492e4de74
readonly DATA_ROOT="$ROOT/data/$RELEASE/cross-os-512m/warm"
readonly RESULT_ROOT="$ROOT/results/$RELEASE/cross-os-512m/warm"
readonly STATE_ROOT="$ROOT/state/$RELEASE/cross-os"
readonly DAEMON_UNIT=discrete-crossos-daemon.service
readonly MONITOR_UNIT=discrete-crossos-monitor.service
readonly P2P_PORT=19330
readonly RPC_PORT=19331
readonly IDLE_SECONDS=120

if [[ $(id -u) -ne 0 ]]; then
  echo "run-warm-host.sh must run as root" >&2
  exit 1
fi
if [[ $# -ne 2 || ! $1 =~ ^[0-9]{2}$ || ! $2 =~ ^(ubuntu24\.04|debian12)$ ]]; then
  echo "usage: run-warm-host.sh NN ubuntu24.04|debian12" >&2
  exit 1
fi

if ! grep -Eq '(^|[[:space:]])mem=512M([[:space:]]|$)' /proc/cmdline; then
  echo "refusing to start: kernel mem=512M limit is not active" >&2
  exit 1
fi
mem_total_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
if (( mem_total_kb < 430000 || mem_total_kb > 510000 )); then
  echo "refusing to start: unexpected MemTotal=${mem_total_kb}kB" >&2
  exit 1
fi

readonly ORDINAL=$1
readonly HOST_OS=$2
readonly RUN_ID="crossos-512m-warm-${ORDINAL}-${HOST_OS}"
readonly DATA_DIR="$DATA_ROOT/$RUN_ID"
readonly RESULT_DIR="$RESULT_ROOT/$RUN_ID"
readonly GO_FILE="$STATE_ROOT/warm-${ORDINAL}.go"

cleanup_on_error() {
  local rc=$?
  if (( rc != 0 )); then
    timeout 330 systemctl stop "$DAEMON_UNIT" >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap cleanup_on_error EXIT

if systemctl is-active --quiet "$DAEMON_UNIT" || pgrep -x discreted >/dev/null 2>&1; then
  echo "refusing to start: a discreted process is already active" >&2
  exit 1
fi
if ss -lnt | grep -Eq ":(${P2P_PORT}|${RPC_PORT})([[:space:]]|$)"; then
  echo "refusing to start: cross-OS benchmark port is already in use" >&2
  exit 1
fi
if [[ -e "$DATA_DIR" || -e "$RESULT_DIR" || -e "$GO_FILE" ]]; then
  echo "refusing to overwrite existing warm run or barrier path" >&2
  exit 1
fi
if [[ $(sha256sum "$BINARY" | awk '{print $1}') != "$EXPECTED_BINARY_SHA256" ]]; then
  echo "Universal binary SHA256 mismatch" >&2
  exit 1
fi
if [[ $(sha256sum "$SNAPSHOT/p2pstate.bin" | awk '{print $1}') != "$EXPECTED_P2P_SHA256" || \
      $(sha256sum "$SNAPSHOT/poolstate.bin" | awk '{print $1}') != "$EXPECTED_POOL_SHA256" || \
      $(sha256sum "$SNAPSHOT/blockchain.lmdb/data.mdb" | awk '{print $1}') != "$EXPECTED_DATA_SHA256" ]]; then
  echo "canonical snapshot SHA256 mismatch" >&2
  exit 1
fi

install -d -o root -g root -m 0755 "$STATE_ROOT"
install -d -o serveradmin -g serveradmin -m 0755 "$DATA_DIR" "$RESULT_DIR"
cp -a "$SNAPSHOT/." "$DATA_DIR/"
chown -R serveradmin:serveradmin "$DATA_DIR"

(
  cd "$DATA_DIR"
  printf '%s  p2pstate.bin\n' "$EXPECTED_P2P_SHA256"
  printf '%s  poolstate.bin\n' "$EXPECTED_POOL_SHA256"
  printf '%s  blockchain.lmdb/data.mdb\n' "$EXPECTED_DATA_SHA256"
) > "$RESULT_DIR/snapshot-expected-sha256.txt"
(
  cd "$DATA_DIR"
  sha256sum --check "$RESULT_DIR/snapshot-expected-sha256.txt"
) > "$RESULT_DIR/snapshot-verification.txt"

env_tmp=$(mktemp "$STATE_ROOT/current.env.XXXXXX")
cat > "$env_tmp" <<EOF
BENCH_RUN_ID=$RUN_ID
BENCH_BINARY=$BINARY
BENCH_EXPECTED_SHA256=$EXPECTED_BINARY_SHA256
BENCH_DATA_DIR=$DATA_DIR
BENCH_RESULT_DIR=$RESULT_DIR
BENCH_P2P_PORT=$P2P_PORT
BENCH_RPC_PORT=$RPC_PORT
EOF
chown root:root "$env_tmp"
chmod 0644 "$env_tmp"
mv "$env_tmp" "$STATE_ROOT/current.env"

{
  printf 'run_id=%s\n' "$RUN_ID"
  printf 'host_os=%s\n' "$HOST_OS"
  printf 'snapshot_height=4656\n'
  printf 'idle_seconds=%s\n' "$IDLE_SECONDS"
  printf 'prepared_utc=%s\n' "$(date --utc --iso-8601=ns)"
  uname -a
  lscpu
  free -b
  df -B1 /
  uptime
  printf 'kernel_cmdline='; cat /proc/cmdline
  cat /proc/swaps
  cat /proc/meminfo
  cat /proc/vmstat
  cat /proc/pressure/cpu /proc/pressure/io /proc/pressure/memory
  for policy in \
    /sys/kernel/mm/transparent_hugepage/enabled \
    /sys/kernel/mm/transparent_hugepage/defrag \
    /sys/kernel/mm/transparent_hugepage/shmem_enabled; do
    if [[ -r "$policy" ]]; then
      printf '%s=' "$policy"
      cat "$policy"
    fi
  done
  sha256sum "$BINARY" "$DATA_DIR/p2pstate.bin" "$DATA_DIR/poolstate.bin" "$DATA_DIR/blockchain.lmdb/data.mdb"
} > "$RESULT_DIR/host-pre-run.txt"

sync
printf '3\n' > /proc/sys/vm/drop_caches
date +%s%N > "$RESULT_DIR/caches-dropped-epoch-ns.txt"
systemctl reset-failed "$DAEMON_UNIT" "$MONITOR_UNIT" >/dev/null 2>&1 || true
systemctl start "$DAEMON_UNIT" "$MONITOR_UNIT"
date +%s%N > "$RESULT_DIR/controller-start-return-epoch-ns.txt"

deadline=$((SECONDS + 300))
synced=0
while (( SECONDS < deadline )); do
  if ! systemctl is-active --quiet "$DAEMON_UNIT"; then
    echo "daemon became inactive before sync" >&2
    systemctl status "$DAEMON_UNIT" --no-pager -l >&2 || true
    exit 1
  fi
  info=$(curl --silent --show-error --max-time 2 "http://127.0.0.1:$RPC_PORT/getinfo" 2>/dev/null || true)
  if [[ -n "$info" ]] && jq -e . >/dev/null 2>&1 <<< "$info"; then
    if [[ ! -e "$RESULT_DIR/first-rpc-getinfo.json" ]]; then
      printf '%s\n' "$info" > "$RESULT_DIR/first-rpc-getinfo.json"
      date +%s%N > "$RESULT_DIR/first-rpc-epoch-ns.txt"
    fi
    height=$(jq -r '.height // 0' <<< "$info")
    last_known=$(jq -r '.last_known_block_index // 0' <<< "$info")
    outgoing=$(jq -r '.outgoing_connections_count // 0' <<< "$info")
    if (( last_known > 100 && height >= last_known + 1 && outgoing > 0 )) && grep -q 'SYNCHRONIZED OK' "$RESULT_DIR/discreted.log"; then
      synced=1
      printf '%s\n' "$info" > "$RESULT_DIR/sync-ready-getinfo.json"
      date +%s%N > "$RESULT_DIR/sync-ready-epoch-ns.txt"
      break
    fi
  fi
  sleep 0.2
done
if (( synced == 0 )); then
  echo "warm sync timeout" >&2
  exit 1
fi

barrier_deadline=$((SECONDS + 600))
while [[ ! -e "$GO_FILE" && SECONDS -lt barrier_deadline ]]; do
  if ! systemctl is-active --quiet "$DAEMON_UNIT"; then
    echo "daemon became inactive at barrier" >&2
    exit 1
  fi
  info=$(curl --silent --show-error --max-time 2 "http://127.0.0.1:$RPC_PORT/getinfo" 2>/dev/null || true)
  if [[ -n "$info" ]] && jq -e . >/dev/null 2>&1 <<< "$info"; then
    tmp=$(mktemp "$RESULT_DIR/barrier-getinfo.json.XXXXXX")
    printf '%s\n' "$info" > "$tmp"
    chmod 0644 "$tmp"
    mv "$tmp" "$RESULT_DIR/barrier-getinfo.json"
    date +%s%N > "$RESULT_DIR/barrier-sample-epoch-ns.txt"
  fi
  sleep 0.2
done
if [[ ! -r "$GO_FILE" ]]; then
  echo "coordinator barrier timeout" >&2
  exit 1
fi

go_epoch=$(<"$GO_FILE")
if [[ ! $go_epoch =~ ^[0-9]{19}$ ]]; then
  echo "invalid coordinator epoch: $go_epoch" >&2
  exit 1
fi
now=$(date +%s%N)
if (( go_epoch <= now || go_epoch - now > 30000000000 )); then
  echo "coordinator epoch is stale or too far in future" >&2
  exit 1
fi
while (( $(date +%s%N) < go_epoch )); do sleep 0.01; done

capture_memory_snapshot() {
  local label=$1
  local daemon_pid
  daemon_pid=$(systemctl show "$DAEMON_UNIT" --property MainPID --value)
  if [[ ! $daemon_pid =~ ^[0-9]+$ || ! -r "/proc/$daemon_pid/smaps_rollup" ]]; then
    echo "cannot capture memory snapshot: label=$label pid=$daemon_pid" >&2
    return 1
  fi
  date +%s%N > "$RESULT_DIR/${label}-memory-epoch-ns.txt"
  cat "/proc/$daemon_pid/smaps_rollup" > "$RESULT_DIR/${label}-smaps-rollup.txt"
  cat "/proc/$daemon_pid/status" > "$RESULT_DIR/${label}-status.txt"
  cat "/proc/$daemon_pid/statm" > "$RESULT_DIR/${label}-statm.txt"
  cat "/proc/$daemon_pid/maps" > "$RESULT_DIR/${label}-maps.txt"
  if command -v pmap >/dev/null 2>&1; then
    pmap -x "$daemon_pid" > "$RESULT_DIR/${label}-pmap-x.txt" || true
  fi
}

date +%s%N > "$RESULT_DIR/idle-start-epoch-ns.txt"
curl --silent --show-error --max-time 3 "http://127.0.0.1:$RPC_PORT/getinfo" > "$RESULT_DIR/idle-start-getinfo.json"
if [[ "$ORDINAL" == "08" || "$ORDINAL" == "09" ]]; then
  capture_memory_snapshot idle-start
  sleep 60
  capture_memory_snapshot idle-mid
  sleep 60
else
  sleep "$IDLE_SECONDS"
fi
date +%s%N > "$RESULT_DIR/idle-end-epoch-ns.txt"
curl --silent --show-error --max-time 3 "http://127.0.0.1:$RPC_PORT/getinfo" > "$RESULT_DIR/idle-end-getinfo.json"
if [[ "$ORDINAL" == "08" || "$ORDINAL" == "09" ]]; then
  capture_memory_snapshot idle-end
fi

date +%s%N > "$RESULT_DIR/stop-start-epoch-ns.txt"
set +e
timeout 330 systemctl stop "$DAEMON_UNIT"
stop_rc=$?
set -e
date +%s%N > "$RESULT_DIR/stop-end-epoch-ns.txt"
printf '%s\n' "$stop_rc" > "$RESULT_DIR/systemctl-stop-exit-code.txt"
if (( stop_rc != 0 )); then
  echo "graceful stop failed: rc=$stop_rc" >&2
  exit 1
fi

monitor_deadline=$((SECONDS + 60))
while systemctl is-active --quiet "$MONITOR_UNIT" && (( SECONDS < monitor_deadline )); do sleep 0.1; done
if systemctl is-active --quiet "$MONITOR_UNIT"; then
  echo "monitor did not exit" >&2
  exit 1
fi

systemctl show "$DAEMON_UNIT" > "$RESULT_DIR/systemd-daemon-post-run.txt"
systemctl show "$MONITOR_UNIT" > "$RESULT_DIR/systemd-monitor-post-run.txt"
journalctl -u "$DAEMON_UNIT" -u "$MONITOR_UNIT" --since '-20 min' --no-pager > "$RESULT_DIR/journal-run.txt"
dmesg --ctime | tail -n 250 > "$RESULT_DIR/dmesg-tail.txt"
find "$DATA_DIR" -type f -print0 | sort -z | xargs -0 sha256sum > "$RESULT_DIR/data-sha256.txt"
du -B1 -s "$DATA_DIR" > "$RESULT_DIR/data-size-bytes.txt"
cat /proc/pressure/cpu /proc/pressure/io /proc/pressure/memory > "$RESULT_DIR/pressure-post-run.txt"
{
  cat /proc/swaps
  cat /proc/meminfo
  cat /proc/vmstat
} > "$RESULT_DIR/host-memory-post-run.txt"

launch=$(<"$RESULT_DIR/launch-epoch-ns.txt")
first_rpc=$(<"$RESULT_DIR/first-rpc-epoch-ns.txt")
sync_ready=$(<"$RESULT_DIR/sync-ready-epoch-ns.txt")
idle_start=$(<"$RESULT_DIR/idle-start-epoch-ns.txt")
idle_end=$(<"$RESULT_DIR/idle-end-epoch-ns.txt")
stop_start=$(<"$RESULT_DIR/stop-start-epoch-ns.txt")
stop_end=$(<"$RESULT_DIR/stop-end-epoch-ns.txt")
first_rpc_seconds=$(awk -v s="$launch" -v e="$first_rpc" 'BEGIN {printf "%.6f", (e-s)/1000000000}')
sync_seconds=$(awk -v s="$launch" -v e="$sync_ready" 'BEGIN {printf "%.6f", (e-s)/1000000000}')
idle_actual_seconds=$(awk -v s="$idle_start" -v e="$idle_end" 'BEGIN {printf "%.6f", (e-s)/1000000000}')
stop_seconds=$(awk -v s="$stop_start" -v e="$stop_end" 'BEGIN {printf "%.6f", (e-s)/1000000000}')
start_height=$(jq -r '.height' "$RESULT_DIR/idle-start-getinfo.json")
end_height=$(jq -r '.height' "$RESULT_DIR/idle-end-getinfo.json")
start_hash=$(jq -r '.top_block_hash' "$RESULT_DIR/idle-start-getinfo.json")
end_hash=$(jq -r '.top_block_hash' "$RESULT_DIR/idle-end-getinfo.json")
start_outgoing=$(jq -r '.outgoing_connections_count' "$RESULT_DIR/idle-start-getinfo.json")
start_incoming=$(jq -r '.incoming_connections_count' "$RESULT_DIR/idle-start-getinfo.json")
fatal_count=$(awk 'BEGIN {IGNORECASE=1} /SIGILL|illegal instruction|segmentation fault|segfault|assert|fatal|terminate called|core dumped/ && $0 !~ /monitor\.sh.*awk: fatal:/ {count++} END {print count+0}' \
  "$RESULT_DIR/discreted.log" "$RESULT_DIR/journal-run.txt" "$RESULT_DIR/dmesg-tail.txt" 2>/dev/null)
{
  printf 'run_id=%s\n' "$RUN_ID"
  printf 'first_rpc_seconds=%s\n' "$first_rpc_seconds"
  printf 'sync_ready_seconds=%s\n' "$sync_seconds"
  printf 'idle_actual_seconds=%s\n' "$idle_actual_seconds"
  printf 'idle_start_height=%s\n' "$start_height"
  printf 'idle_end_height=%s\n' "$end_height"
  printf 'idle_start_hash=%s\n' "$start_hash"
  printf 'idle_end_hash=%s\n' "$end_hash"
  printf 'outgoing_at_idle_start=%s\n' "$start_outgoing"
  printf 'incoming_at_idle_start=%s\n' "$start_incoming"
  printf 'stop_seconds=%s\n' "$stop_seconds"
  printf 'stop_rc=%s\n' "$stop_rc"
  printf 'fatal_pattern_matches=%s\n' "$fatal_count"
} | tee "$RESULT_DIR/run-summary.txt"

if pgrep -x discreted >/dev/null 2>&1 || ss -lnt | grep -Eq ":(${P2P_PORT}|${RPC_PORT})([[:space:]]|$)"; then
  echo "process or benchmark port remains after stop" >&2
  exit 1
fi

rm -f "$GO_FILE"
trap - EXIT
