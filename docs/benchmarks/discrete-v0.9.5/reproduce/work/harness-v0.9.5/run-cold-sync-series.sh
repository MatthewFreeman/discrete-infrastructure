#!/usr/bin/env bash
set -euo pipefail

readonly RELEASE=v.0.9.5
readonly ROOT=/opt/discrete-benchmark
readonly RELEASE_ROOT="$ROOT/releases/$RELEASE"
readonly DATA_ROOT="$ROOT/data/$RELEASE"
readonly RESULT_ROOT="$ROOT/results/$RELEASE"
readonly STATE_ROOT="$ROOT/state/$RELEASE"
readonly DAEMON_UNIT=discrete-benchmark-daemon.service
readonly MONITOR_UNIT=discrete-benchmark-monitor.service
readonly COMMON_P2P_STATE="$DATA_ROOT/snapshots/seed-p2pstate.bin"
readonly SERIES_LOG="$RESULT_ROOT/cold-sync-series-controller.log"

readonly UBUNTU_BINARY="$RELEASE_ROOT/ubuntu24.04/discreted"
readonly UNIVERSAL_BINARY="$RELEASE_ROOT/linux-universal/discreted"
readonly UBUNTU_SHA256=7037d5aed0446419fa7f36b0ced03e51ea4c8cafc02217d66568f8bf4063d6fd
readonly UNIVERSAL_SHA256=6296755aad63d66f80150383a2a30a15876f766fa05d68733653f0c1063ae30e

# Balanced order: A B B A | B A A B, where A=Ubuntu-native and B=Universal.
readonly ORDER=(ubuntu24.04 linux-universal linux-universal ubuntu24.04 linux-universal ubuntu24.04 ubuntu24.04 linux-universal)

exec > >(tee -a "$SERIES_LOG") 2>&1

log() {
  printf '%s %s\n' "$(date --utc --iso-8601=ns)" "$*"
}

write_environment() {
  local run_id=$1
  local variant=$2
  local binary=$3
  local expected_sha=$4
  local data_dir=$5
  local result_dir=$6
  local env_tmp

  env_tmp=$(mktemp "$STATE_ROOT/current.env.XXXXXX")
  cat > "$env_tmp" <<EOF
BENCH_RUN_ID=$run_id
BENCH_VARIANT=$variant
BENCH_BINARY=$binary
BENCH_EXPECTED_SHA256=$expected_sha
BENCH_DATA_DIR=$data_dir
BENCH_RESULT_DIR=$result_dir
BENCH_P2P_PORT=9330
BENCH_RPC_PORT=9331
EOF
  chown root:root "$env_tmp"
  chmod 0644 "$env_tmp"
  mv "$env_tmp" "$STATE_ROOT/current.env"
}

if [[ $(id -u) -ne 0 ]]; then
  echo "run-cold-sync-series.sh must run as root" >&2
  exit 1
fi

install -d -o root -g root -m 0755 "$STATE_ROOT"
install -d -o serveradmin -g serveradmin -m 0755 "$DATA_ROOT/snapshots" "$RESULT_ROOT/runs"

if systemctl is-active --quiet "$DAEMON_UNIT" || pgrep -x discreted >/dev/null 2>&1; then
  echo "refusing to start: a Discrete benchmark daemon is already active" >&2
  exit 1
fi

if [[ ! -r "$COMMON_P2P_STATE" ]]; then
  echo "missing common stopped p2p snapshot: $COMMON_P2P_STATE" >&2
  exit 1
fi

printf 'release=%s\norder=%s\nstarted_utc=%s\n' "$RELEASE" "${ORDER[*]}" "$(date --utc --iso-8601=ns)" > "$RESULT_ROOT/cold-sync-series-metadata.txt"
sha256sum "$UBUNTU_BINARY" "$UNIVERSAL_BINARY" "$COMMON_P2P_STATE" >> "$RESULT_ROOT/cold-sync-series-metadata.txt"

for index in "${!ORDER[@]}"; do
  ordinal=$(printf '%02d' "$((index + 1))")
  variant=${ORDER[$index]}
  if [[ "$variant" == "ubuntu24.04" ]]; then
    short_variant=ubuntu
    binary=$UBUNTU_BINARY
    expected_sha=$UBUNTU_SHA256
  else
    short_variant=universal
    binary=$UNIVERSAL_BINARY
    expected_sha=$UNIVERSAL_SHA256
  fi

  run_id="cold-${ordinal}-${short_variant}"
  data_dir="$DATA_ROOT/$run_id"
  result_dir="$RESULT_ROOT/runs/$run_id"

  if [[ -e "$data_dir" || -e "$result_dir" ]]; then
    echo "refusing to overwrite existing run path: $data_dir or $result_dir" >&2
    exit 1
  fi

  log "RUN_START run_id=$run_id variant=$variant"
  install -d -o serveradmin -g serveradmin -m 0755 "$data_dir" "$result_dir"
  install -o serveradmin -g serveradmin -m 0644 "$COMMON_P2P_STATE" "$data_dir/p2pstate.bin"
  write_environment "$run_id" "$variant" "$binary" "$expected_sha" "$data_dir" "$result_dir"

  {
    printf 'pre_run_utc=%s\n' "$(date --utc --iso-8601=ns)"
    uname -a
    lscpu
    free -b
    df -B1 /
    uptime
    sha256sum "$binary" "$data_dir/p2pstate.bin"
  } > "$result_dir/host-pre-run.txt"

  sync
  printf '3\n' > /proc/sys/vm/drop_caches
  date --utc --iso-8601=ns > "$result_dir/caches-dropped-utc.txt"

  systemctl reset-failed "$DAEMON_UNIT" "$MONITOR_UNIT" >/dev/null 2>&1 || true
  systemctl start "$DAEMON_UNIT" "$MONITOR_UNIT"
  date +%s%N > "$result_dir/controller-start-return-epoch-ns.txt"

  deadline=$((SECONDS + 600))
  synced=0
  while (( SECONDS < deadline )); do
    if ! systemctl is-active --quiet "$DAEMON_UNIT"; then
      log "RUN_FAILURE run_id=$run_id daemon_became_inactive"
      systemctl status "$DAEMON_UNIT" --no-pager -l || true
      exit 1
    fi

    info=$(curl --silent --show-error --max-time 2 http://127.0.0.1:9331/getinfo 2>/dev/null || true)
    if [[ -n "$info" ]] && jq -e . >/dev/null 2>&1 <<< "$info"; then
      height=$(jq -r '.height // 0' <<< "$info")
      last_known=$(jq -r '.last_known_block_index // 0' <<< "$info")
      outgoing=$(jq -r '.outgoing_connections_count // 0' <<< "$info")
      if (( last_known > 100 && height >= last_known + 1 && outgoing > 0 )) && grep -q 'SYNCHRONIZED OK' "$result_dir/discreted.log"; then
        synced=1
        printf '%s\n' "$info" > "$result_dir/sync-detected-getinfo.json"
        date +%s%N > "$result_dir/sync-detected-epoch-ns.txt"
        log "SYNC_DETECTED run_id=$run_id height=$height last_known=$last_known outgoing=$outgoing"
        break
      fi
    fi
    sleep 1
  done

  if (( synced == 0 )); then
    log "RUN_FAILURE run_id=$run_id sync_timeout"
    timeout 330 systemctl stop "$DAEMON_UNIT" || true
    exit 1
  fi

  sleep 5
  curl --silent --show-error --max-time 3 http://127.0.0.1:9331/getinfo > "$result_dir/pre-stop-getinfo.json"
  date +%s%N > "$result_dir/stop-start-epoch-ns.txt"
  set +e
  timeout 330 systemctl stop "$DAEMON_UNIT"
  stop_rc=$?
  set -e
  date +%s%N > "$result_dir/stop-end-epoch-ns.txt"
  printf '%s\n' "$stop_rc" > "$result_dir/systemctl-stop-exit-code.txt"

  if (( stop_rc != 0 )); then
    log "RUN_FAILURE run_id=$run_id systemctl_stop_rc=$stop_rc"
    exit 1
  fi

  monitor_deadline=$((SECONDS + 60))
  while systemctl is-active --quiet "$MONITOR_UNIT" && (( SECONDS < monitor_deadline )); do
    sleep 0.1
  done
  if systemctl is-active --quiet "$MONITOR_UNIT"; then
    log "RUN_FAILURE run_id=$run_id monitor_did_not_exit"
    exit 1
  fi

  systemctl show "$DAEMON_UNIT" > "$result_dir/systemd-daemon-post-run.txt"
  systemctl show "$MONITOR_UNIT" > "$result_dir/systemd-monitor-post-run.txt"
  find "$data_dir" -type f -print0 | sort -z | xargs -0 sha256sum > "$result_dir/data-sha256.txt"
  du -B1 -s "$data_dir" > "$result_dir/data-size-bytes.txt"
  df -B1 / > "$result_dir/filesystem-post-run.txt"
  dmesg --ctime | tail -n 200 > "$result_dir/dmesg-tail.txt"

  stop_start=$(<"$result_dir/stop-start-epoch-ns.txt")
  stop_end=$(<"$result_dir/stop-end-epoch-ns.txt")
  stop_seconds=$(awk -v s="$stop_start" -v e="$stop_end" 'BEGIN {printf "%.6f", (e-s)/1000000000}')
  log "RUN_COMPLETE run_id=$run_id stop_seconds=$stop_seconds data_bytes=$(cut -f1 "$result_dir/data-size-bytes.txt")"

  sleep 10
done

date --utc --iso-8601=ns > "$RESULT_ROOT/cold-sync-series-completed-utc.txt"
log "SERIES_COMPLETE runs=${#ORDER[@]}"
