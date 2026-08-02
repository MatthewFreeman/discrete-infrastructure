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
readonly STATE_ROOT="$ROOT/state/$RELEASE/cross-os"
readonly DAEMON_UNIT=discrete-crossos-daemon.service
readonly MONITOR_UNIT=discrete-crossos-monitor.service
readonly P2P_PORT=19330
readonly RPC_PORT=19331

if [[ $(id -u) -ne 0 ]]; then
  echo "reboot-validation-host.sh must run as root" >&2
  exit 1
fi
if [[ $# -lt 3 || ! $1 =~ ^(prepare|verify|cleanup)$ || ! $2 =~ ^(ubuntu24\.04|debian12)$ || ! $3 =~ ^[0-9]{2}$ ]]; then
  echo "usage: reboot-validation-host.sh prepare|verify|cleanup ubuntu24.04|debian12 NN [cycle]" >&2
  exit 1
fi

readonly ACTION=$1
readonly HOST_OS=$2
readonly ORDINAL=$3
readonly RUN_ID="crossos-512m-reboot-${ORDINAL}-${HOST_OS}"
readonly DATA_DIR="$ROOT/data/$RELEASE/cross-os-512m/reboot/$RUN_ID"
readonly RESULT_DIR="$ROOT/results/$RELEASE/cross-os-512m/reboot/$RUN_ID"
readonly BACKUP_ENV="$STATE_ROOT/current.env.before-$RUN_ID"

validate_artifacts() {
  [[ $(sha256sum "$BINARY" | awk '{print $1}') == "$EXPECTED_BINARY_SHA256" ]]
  [[ $(sha256sum "$SNAPSHOT/p2pstate.bin" | awk '{print $1}') == "$EXPECTED_P2P_SHA256" ]]
  [[ $(sha256sum "$SNAPSHOT/poolstate.bin" | awk '{print $1}') == "$EXPECTED_POOL_SHA256" ]]
  [[ $(sha256sum "$SNAPSHOT/blockchain.lmdb/data.mdb" | awk '{print $1}') == "$EXPECTED_DATA_SHA256" ]]
}

validate_memory_limit() {
  grep -Eq '(^|[[:space:]])mem=512M([[:space:]]|$)' /proc/cmdline
  local mem_total_kb
  mem_total_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
  (( mem_total_kb >= 430000 && mem_total_kb <= 510000 ))
}

case "$ACTION" in
  prepare)
    validate_artifacts
    validate_memory_limit
    if systemctl is-active --quiet "$DAEMON_UNIT" || pgrep -x discreted >/dev/null 2>&1; then
      echo "daemon already active" >&2
      exit 1
    fi
    if ss -ltn | grep -Eq ":(${P2P_PORT}|${RPC_PORT})([[:space:]]|$)"; then
      echo "benchmark port already active" >&2
      exit 1
    fi
    [[ ! -e "$DATA_DIR" && ! -e "$RESULT_DIR" && ! -e "$BACKUP_ENV" ]]
    install -d -o serveradmin -g serveradmin -m 0755 "$DATA_DIR" "$RESULT_DIR"
    cp -a "$SNAPSHOT/." "$DATA_DIR/"
    chown -R serveradmin:serveradmin "$DATA_DIR"
    cp -a "$STATE_ROOT/current.env" "$BACKUP_ENV"
    env_tmp=$(mktemp "$STATE_ROOT/current.env.reboot.XXXXXX")
    {
      printf 'BENCH_RUN_ID=%s\n' "$RUN_ID"
      printf 'BENCH_BINARY=%s\n' "$BINARY"
      printf 'BENCH_EXPECTED_SHA256=%s\n' "$EXPECTED_BINARY_SHA256"
      printf 'BENCH_DATA_DIR=%s\n' "$DATA_DIR"
      printf 'BENCH_RESULT_DIR=%s\n' "$RESULT_DIR"
      printf 'BENCH_P2P_PORT=%s\n' "$P2P_PORT"
      printf 'BENCH_RPC_PORT=%s\n' "$RPC_PORT"
    } > "$env_tmp"
    chown root:root "$env_tmp"
    chmod 0644 "$env_tmp"
    mv "$env_tmp" "$STATE_ROOT/current.env"
    cat /proc/sys/kernel/random/boot_id > "$RESULT_DIR/boot-id-before.txt"
    {
      printf 'run_id=%s\n' "$RUN_ID"
      printf 'host_os=%s\n' "$HOST_OS"
      printf 'prepared_utc=%s\n' "$(date --utc --iso-8601=ns)"
      printf 'binary_sha256=%s\n' "$EXPECTED_BINARY_SHA256"
      printf 'thp_enabled='; cat /sys/kernel/mm/transparent_hugepage/enabled
      printf 'kernel_cmdline='; cat /proc/cmdline
      cat /proc/meminfo
      cat /proc/swaps
      uname -a
    } > "$RESULT_DIR/host-pre-reboot.txt"
    systemctl enable "$DAEMON_UNIT" "$MONITOR_UNIT" >/dev/null
    [[ $(systemctl is-enabled "$DAEMON_UNIT") == enabled ]]
    [[ $(systemctl is-enabled "$MONITOR_UNIT") == enabled ]]
    echo "prepared run_id=$RUN_ID"
    ;;

  verify)
    if [[ $# -ne 4 || ! $4 =~ ^[12]$ ]]; then
      echo "verify requires cycle 1 or 2" >&2
      exit 1
    fi
    readonly CYCLE=$4
    validate_artifacts
    validate_memory_limit
    [[ $(systemctl is-enabled "$DAEMON_UNIT") == enabled ]]
    [[ $(systemctl is-enabled "$MONITOR_UNIT") == enabled ]]
    systemctl is-active --quiet "$DAEMON_UNIT"
    systemctl is-active --quiet "$MONITOR_UNIT"
    current_boot_id=$(< /proc/sys/kernel/random/boot_id)
    prior_boot_file="$RESULT_DIR/boot-id-before.txt"
    if [[ "$CYCLE" == 2 ]]; then
      prior_boot_file="$RESULT_DIR/boot-id-cycle-1.txt"
    fi
    [[ "$current_boot_id" != "$(< "$prior_boot_file")" ]]
    printf '%s\n' "$current_boot_id" > "$RESULT_DIR/boot-id-cycle-${CYCLE}.txt"

    deadline=$((SECONDS + 180))
    info=''
    while (( SECONDS < deadline )); do
      info=$(curl --silent --show-error --max-time 3 "http://127.0.0.1:$RPC_PORT/getinfo" 2>/dev/null || true)
      if [[ -n "$info" ]] && jq -e '.height > 0 and .outgoing_connections_count > 0' >/dev/null 2>&1 <<< "$info"; then
        break
      fi
      sleep 1
    done
    if [[ -z "$info" ]] || ! jq -e '.height > 0 and .outgoing_connections_count > 0' >/dev/null 2>&1 <<< "$info"; then
      echo "RPC/peers not ready after reboot cycle $CYCLE" >&2
      exit 1
    fi
    printf '%s\n' "$info" > "$RESULT_DIR/getinfo-cycle-${CYCLE}.json"
    systemctl show "$DAEMON_UNIT" > "$RESULT_DIR/systemd-daemon-cycle-${CYCLE}.txt"
    systemctl show "$MONITOR_UNIT" > "$RESULT_DIR/systemd-monitor-cycle-${CYCLE}.txt"
    journalctl -b -u "$DAEMON_UNIT" -u "$MONITOR_UNIT" --no-pager > "$RESULT_DIR/journal-cycle-${CYCLE}.txt"
    if [[ "$CYCLE" == 2 ]]; then
      journalctl -b -1 -u "$DAEMON_UNIT" -u "$MONITOR_UNIT" --no-pager > "$RESULT_DIR/journal-previous-boot.txt"
    fi
    {
      printf 'cycle=%s\n' "$CYCLE"
      printf 'boot_id=%s\n' "$current_boot_id"
      printf 'height=%s\n' "$(jq -r .height <<< "$info")"
      printf 'outgoing=%s\n' "$(jq -r .outgoing_connections_count <<< "$info")"
      printf 'incoming=%s\n' "$(jq -r .incoming_connections_count <<< "$info")"
      printf 'thp_enabled='; cat /sys/kernel/mm/transparent_hugepage/enabled
      printf 'kernel_cmdline='; cat /proc/cmdline
      grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo
      printf 'verified_utc=%s\n' "$(date --utc --iso-8601=ns)"
    } | tee "$RESULT_DIR/cycle-${CYCLE}-summary.txt"
    ;;

  cleanup)
    set +e
    timeout 330 systemctl stop "$DAEMON_UNIT"
    stop_rc=$?
    systemctl stop "$MONITOR_UNIT" >/dev/null 2>&1
    set -e
    printf '%s\n' "$stop_rc" > "$RESULT_DIR/final-stop-rc.txt"
    (( stop_rc == 0 ))
    systemctl disable "$DAEMON_UNIT" "$MONITOR_UNIT" >/dev/null
    install -o root -g root -m 0644 "$BACKUP_ENV" "$STATE_ROOT/current.env"
    [[ $(systemctl is-enabled "$DAEMON_UNIT" 2>/dev/null || true) == disabled ]]
    [[ $(systemctl is-enabled "$MONITOR_UNIT" 2>/dev/null || true) == disabled ]]
    ! systemctl is-active --quiet "$DAEMON_UNIT"
    ! systemctl is-active --quiet "$MONITOR_UNIT"
    ! pgrep -x discreted >/dev/null 2>&1
    ! ss -ltn | grep -Eq ":(${P2P_PORT}|${RPC_PORT})([[:space:]]|$)"
    journalctl -b -u "$DAEMON_UNIT" -u "$MONITOR_UNIT" --no-pager > "$RESULT_DIR/journal-final-boot.txt"
    dmesg --ctime | tail -n 250 > "$RESULT_DIR/dmesg-tail.txt"
    find "$DATA_DIR" -type f -print0 | sort -z | xargs -0 sha256sum > "$RESULT_DIR/data-sha256.txt"
    diagnostic_files=()
    for candidate in "$RESULT_DIR/discreted.log" "$RESULT_DIR"/journal-*.txt "$RESULT_DIR/dmesg-tail.txt"; do
      [[ -f "$candidate" ]] && diagnostic_files+=("$candidate")
    done
    fatal_count=0
    if (( ${#diagnostic_files[@]} > 0 )); then
      fatal_count=$(awk 'BEGIN {IGNORECASE=1} /SIGILL|illegal instruction|segmentation fault|segfault|assert|fatal|terminate called|core dumped/ && $0 !~ /monitor\.sh.*awk: fatal:/ {count++} END {print count+0}' \
        "${diagnostic_files[@]}")
    fi
    {
      printf 'run_id=%s\n' "$RUN_ID"
      printf 'final_stop_rc=%s\n' "$stop_rc"
      printf 'fatal_pattern_matches=%s\n' "$fatal_count"
      printf 'daemon_enabled=no\n'
      printf 'monitor_enabled=no\n'
      printf 'cleanup_utc=%s\n' "$(date --utc --iso-8601=ns)"
    } | tee "$RESULT_DIR/run-summary.txt"
    (( fatal_count == 0 ))
    ;;
esac
