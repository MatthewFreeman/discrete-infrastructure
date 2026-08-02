#!/usr/bin/env bash
set -euo pipefail

readonly RELEASE=v.0.9.5
readonly ROOT=/opt/discrete-benchmark
readonly BINARY="$ROOT/releases/$RELEASE/linux-universal/discreted"
readonly EXPECTED_BINARY_SHA256=6296755aad63d66f80150383a2a30a15876f766fa05d68733653f0c1063ae30e
readonly SEED="$ROOT/data/$RELEASE/cross-os/seed-p2pstate.bin"
readonly EXPECTED_SEED_SHA256=3430f8030f676e2a74ecb35ca52e79e584448f83f925621d27d3672dc2ab7d5b
readonly DATA_ROOT="$ROOT/data/$RELEASE/cross-os-512m/cold"
readonly RESULT_ROOT="$ROOT/results/$RELEASE/cross-os-512m/cold"
readonly STATE_ROOT="$ROOT/state/$RELEASE/cross-os"
readonly DAEMON_UNIT=discrete-crossos-daemon.service
readonly MONITOR_UNIT=discrete-crossos-monitor.service
readonly TARGET_HEIGHT=4500
readonly P2P_PORT=19330
readonly RPC_PORT=19331

if [[ $(id -u) -ne 0 ]]; then
  echo "run-cold-host.sh must run as root" >&2
  exit 1
fi
if [[ $# -ne 2 || ! $1 =~ ^[0-9]{2}$ || ! $2 =~ ^(ubuntu24\.04|debian12)$ ]]; then
  echo "usage: run-cold-host.sh NN ubuntu24.04|debian12" >&2
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
readonly RUN_ID="crossos-512m-cold-${ORDINAL}-${HOST_OS}"
readonly DATA_DIR="$DATA_ROOT/$RUN_ID"
readonly RESULT_DIR="$RESULT_ROOT/$RUN_ID"

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
if [[ -e "$DATA_DIR" || -e "$RESULT_DIR" ]]; then
  echo "refusing to overwrite existing run path" >&2
  exit 1
fi
if [[ $(sha256sum "$BINARY" | awk '{print $1}') != "$EXPECTED_BINARY_SHA256" ]]; then
  echo "Universal binary SHA256 mismatch" >&2
  exit 1
fi
if [[ $(sha256sum "$SEED" | awk '{print $1}') != "$EXPECTED_SEED_SHA256" ]]; then
  echo "seed p2pstate SHA256 mismatch" >&2
  exit 1
fi

install -d -o root -g root -m 0755 "$STATE_ROOT"
install -d -o serveradmin -g serveradmin -m 0755 "$DATA_DIR" "$RESULT_DIR"
install -o serveradmin -g serveradmin -m 0644 "$SEED" "$DATA_DIR/p2pstate.bin"

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
  printf 'target_height=%s\n' "$TARGET_HEIGHT"
  printf 'seed_sha256=%s\n' "$EXPECTED_SEED_SHA256"
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
  for thp_setting in \
    /sys/kernel/mm/transparent_hugepage/enabled \
    /sys/kernel/mm/transparent_hugepage/defrag \
    /sys/kernel/mm/transparent_hugepage/shmem_enabled; do
    if [[ -r "$thp_setting" ]]; then
      printf '%s=' "$thp_setting"
      cat "$thp_setting"
    fi
  done
  sha256sum "$BINARY" "$DATA_DIR/p2pstate.bin"
} > "$RESULT_DIR/host-pre-run.txt"

sync
printf '3\n' > /proc/sys/vm/drop_caches
date +%s%N > "$RESULT_DIR/caches-dropped-epoch-ns.txt"
systemctl reset-failed "$DAEMON_UNIT" "$MONITOR_UNIT" >/dev/null 2>&1 || true
systemctl start "$DAEMON_UNIT" "$MONITOR_UNIT"
date +%s%N > "$RESULT_DIR/controller-start-return-epoch-ns.txt"

deadline=$((SECONDS + 600))
target_seen=0
while (( SECONDS < deadline )); do
  if ! systemctl is-active --quiet "$DAEMON_UNIT"; then
    echo "daemon became inactive before target" >&2
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
    outgoing=$(jq -r '.outgoing_connections_count // 0' <<< "$info")
    if (( height >= TARGET_HEIGHT && outgoing > 0 )); then
      target_seen=1
      printf '%s\n' "$info" > "$RESULT_DIR/target-getinfo.json"
      date +%s%N > "$RESULT_DIR/target-epoch-ns.txt"
      ss -ntp > "$RESULT_DIR/network-connections-at-target.txt" || true
      break
    fi
  fi
  sleep 0.2
done

if (( target_seen == 0 )); then
  echo "target height timeout" >&2
  exit 1
fi

daemon_pid=$(systemctl show --property=MainPID --value "$DAEMON_UNIT")
if [[ "$daemon_pid" =~ ^[1-9][0-9]*$ && -r "/proc/$daemon_pid/smaps_rollup" ]]; then
  cat "/proc/$daemon_pid/smaps_rollup" > "$RESULT_DIR/target-smaps-rollup.txt"
  cat "/proc/$daemon_pid/status" > "$RESULT_DIR/target-status.txt"
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
journalctl -u "$DAEMON_UNIT" -u "$MONITOR_UNIT" --since '-15 min' --no-pager > "$RESULT_DIR/journal-run.txt"
dmesg --ctime | tail -n 250 > "$RESULT_DIR/dmesg-tail.txt"
find "$DATA_DIR" -type f -print0 | sort -z | xargs -0 sha256sum > "$RESULT_DIR/data-sha256.txt"
du -B1 -s "$DATA_DIR" > "$RESULT_DIR/data-size-bytes.txt"
df -B1 / > "$RESULT_DIR/filesystem-post-run.txt"
cat /proc/pressure/cpu /proc/pressure/io /proc/pressure/memory > "$RESULT_DIR/pressure-post-run.txt"
{
  cat /proc/swaps
  cat /proc/meminfo
  cat /proc/vmstat
} > "$RESULT_DIR/host-memory-post-run.txt"

launch=$(<"$RESULT_DIR/launch-epoch-ns.txt")
target=$(<"$RESULT_DIR/target-epoch-ns.txt")
stop_start=$(<"$RESULT_DIR/stop-start-epoch-ns.txt")
stop_end=$(<"$RESULT_DIR/stop-end-epoch-ns.txt")
wall_seconds=$(awk -v s="$launch" -v e="$target" 'BEGIN {printf "%.6f", (e-s)/1000000000}')
stop_seconds=$(awk -v s="$stop_start" -v e="$stop_end" 'BEGIN {printf "%.6f", (e-s)/1000000000}')
height=$(jq -r '.height' "$RESULT_DIR/target-getinfo.json")
outgoing=$(jq -r '.outgoing_connections_count' "$RESULT_DIR/target-getinfo.json")
incoming=$(jq -r '.incoming_connections_count' "$RESULT_DIR/target-getinfo.json")
fatal_count=$(awk 'BEGIN {IGNORECASE=1} /SIGILL|illegal instruction|segmentation fault|segfault|assert|fatal|terminate called|core dumped/ && $0 !~ /monitor\.sh.*awk: fatal:/ {count++} END {print count+0}' \
  "$RESULT_DIR/discreted.log" "$RESULT_DIR/journal-run.txt" "$RESULT_DIR/dmesg-tail.txt" 2>/dev/null)
{
  printf 'run_id=%s\n' "$RUN_ID"
  printf 'wall_to_target_seconds=%s\n' "$wall_seconds"
  printf 'observed_target_height=%s\n' "$height"
  printf 'outgoing_at_target=%s\n' "$outgoing"
  printf 'incoming_at_target=%s\n' "$incoming"
  printf 'stop_seconds=%s\n' "$stop_seconds"
  printf 'stop_rc=%s\n' "$stop_rc"
  printf 'fatal_pattern_matches=%s\n' "$fatal_count"
} | tee "$RESULT_DIR/run-summary.txt"

if pgrep -x discreted >/dev/null 2>&1 || ss -lnt | grep -Eq ":(${P2P_PORT}|${RPC_PORT})([[:space:]]|$)"; then
  echo "process or benchmark port remains after stop" >&2
  exit 1
fi

trap - EXIT
