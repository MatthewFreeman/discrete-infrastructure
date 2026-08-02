#!/usr/bin/env bash
set -u

readonly ENV_FILE=/opt/discrete-benchmark/state/v.0.9.5/current.env
readonly DAEMON_UNIT=discrete-benchmark-daemon.service

if [[ ! -r "$ENV_FILE" ]]; then
  echo "missing benchmark environment: $ENV_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

: "${BENCH_RUN_ID:?}"
: "${BENCH_RESULT_DIR:?}"
: "${BENCH_RPC_PORT:?}"

rpc_sample_every=${BENCH_RPC_SAMPLE_EVERY:-1}
if ! [[ "$rpc_sample_every" =~ ^[1-9][0-9]*$ ]]; then
  echo "invalid BENCH_RPC_SAMPLE_EVERY: $rpc_sample_every" >&2
  exit 1
fi

runtime_dir="/run/discrete-benchmark/$BENCH_RUN_ID"
if ! install -d -m 0755 "$runtime_dir" "$BENCH_RESULT_DIR"; then
  echo "cannot create monitor runtime/result directories" >&2
  exit 1
fi

samples="$runtime_dir/process-host-samples.tsv"
rpc_samples="$runtime_dir/rpc-samples.tsv"
events="$runtime_dir/events.log"

printf 'epoch_ns\tpid\tstate\tutime_ticks\tstime_ticks\tminflt\tmajflt\tthreads\tvsize_bytes\trss_pages\tvmrss_kb\tvmhwm_kb\tvoluntary_ctxt\tnonvoluntary_ctxt\trchar\twchar\tread_bytes\twrite_bytes\tsyscr\tsyscw\topen_fds\tnet_rx_bytes\tnet_tx_bytes\tblock_reads_completed\tblock_sectors_read\tblock_writes_completed\tblock_sectors_written\thost_cpu_user\thost_cpu_nice\thost_cpu_system\thost_cpu_idle\thost_cpu_iowait\thost_cpu_irq\thost_cpu_softirq\thost_cpu_steal\n' > "$samples"
printf 'epoch_ns\tcurl_rc\thttp_code\ttime_total_s\tstatus\tversion\theight\tlast_known_block_index\toutgoing\tincoming\trpc_connections\twhite_peers\tgrey_peers\ttop_block_hash\n' > "$rpc_samples"
printf '%s monitor_start run_id=%s\n' "$(date --utc --iso-8601=ns)" "$BENCH_RUN_ID" > "$events"

pid=0
for _ in $(seq 1 300); do
  pid=$(systemctl show "$DAEMON_UNIT" --property MainPID --value 2>/dev/null || printf '0')
  if [[ "$pid" =~ ^[0-9]+$ ]] && (( pid > 0 )) && [[ -r "/proc/$pid/stat" ]]; then
    break
  fi
  sleep 0.1
done

if (( pid <= 0 )) || [[ ! -r "/proc/$pid/stat" ]]; then
  printf '%s daemon_pid_not_found\n' "$(date --utc --iso-8601=ns)" >> "$events"
  cp -a "$runtime_dir/." "$BENCH_RESULT_DIR/"
  exit 1
fi

printf '%s daemon_pid=%s\n' "$(date --utc --iso-8601=ns)" "$pid" >> "$events"

net_dev=$(ip -o route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i=="dev") {print $(i+1); exit}}')
root_source=$(findmnt -n -o SOURCE /)
block_dev=$(lsblk -no PKNAME "$root_source" 2>/dev/null | head -n 1)
[[ -n "$block_dev" ]] || block_dev=$(basename "$root_source" | sed -E 's/[0-9]+$//')
page_size=$(getconf PAGESIZE)
clock_ticks=$(getconf CLK_TCK)
printf '%s net_dev=%s block_dev=%s page_size=%s clock_ticks=%s\n' "$(date --utc --iso-8601=ns)" "$net_dev" "$block_dev" "$page_size" "$clock_ticks" >> "$events"

sample_index=0
rpc_ready=0
while [[ -r "/proc/$pid/stat" ]]; do
  epoch_ns=$(date +%s%N)
  stat_line=$(<"/proc/$pid/stat")
  stat_tail=${stat_line#*) }
  read -r -a stat_fields <<< "$stat_tail"
  state=${stat_fields[0]:-}
  minflt=${stat_fields[7]:-0}
  majflt=${stat_fields[9]:-0}
  utime_ticks=${stat_fields[11]:-0}
  stime_ticks=${stat_fields[12]:-0}
  threads=${stat_fields[17]:-0}
  vsize_bytes=${stat_fields[20]:-0}
  rss_pages=${stat_fields[21]:-0}

  read -r vmrss_kb vmhwm_kb voluntary_ctxt nonvoluntary_ctxt < <(
    awk '
      /^VmRSS:/ {rss=$2}
      /^VmHWM:/ {hwm=$2}
      /^voluntary_ctxt_switches:/ {vol=$2}
      /^nonvoluntary_ctxt_switches:/ {nonvol=$2}
      END {printf "%s %s %s %s\n", rss+0, hwm+0, vol+0, nonvol+0}
    ' "/proc/$pid/status"
  )

  read -r rchar wchar read_bytes write_bytes syscr syscw < <(
    awk '
      /^rchar:/ {rchar=$2}
      /^wchar:/ {wchar=$2}
      /^read_bytes:/ {rb=$2}
      /^write_bytes:/ {wb=$2}
      /^syscr:/ {syscr=$2}
      /^syscw:/ {syscw=$2}
      END {printf "%s %s %s %s %s %s\n", rchar+0, wchar+0, rb+0, wb+0, syscr+0, syscw+0}
    ' "/proc/$pid/io"
  )

  open_fds=$(find "/proc/$pid/fd" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)
  net_rx_bytes=$(<"/sys/class/net/$net_dev/statistics/rx_bytes")
  net_tx_bytes=$(<"/sys/class/net/$net_dev/statistics/tx_bytes")
  read -r block_reads _ block_sectors_read _ block_writes _ block_sectors_written _ < "/sys/block/$block_dev/stat"
  read -r _ host_user host_nice host_system host_idle host_iowait host_irq host_softirq host_steal _ < /proc/stat

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$epoch_ns" "$pid" "$state" "$utime_ticks" "$stime_ticks" "$minflt" "$majflt" "$threads" "$vsize_bytes" "$rss_pages" \
    "$vmrss_kb" "$vmhwm_kb" "$voluntary_ctxt" "$nonvoluntary_ctxt" "$rchar" "$wchar" "$read_bytes" "$write_bytes" "$syscr" "$syscw" \
    "$open_fds" "$net_rx_bytes" "$net_tx_bytes" "$block_reads" "$block_sectors_read" "$block_writes" "$block_sectors_written" \
    "$host_user" "$host_nice" "$host_system" "$host_idle" "$host_iowait" "$host_irq" "$host_softirq" "$host_steal" >> "$samples"

  if (( rpc_ready == 0 || sample_index % rpc_sample_every == 0 )); then
    rpc_body="$runtime_dir/rpc-body.tmp"
    rpc_meta=$(curl --silent --show-error --max-time 2 --output "$rpc_body" --write-out '%{http_code}\t%{time_total}' "http://127.0.0.1:$BENCH_RPC_PORT/getinfo" 2>>"$events")
    curl_rc=$?
    http_code=${rpc_meta%%$'\t'*}
    time_total=${rpc_meta#*$'\t'}
    if (( curl_rc == 0 )) && [[ "$http_code" == "200" ]] && jq -e . "$rpc_body" >/dev/null 2>&1; then
      if (( rpc_ready == 0 )); then
        rpc_ready=1
        printf '%s rpc_ready\n' "$(date --utc --iso-8601=ns)" >> "$events"
      fi
      jq -r --arg epoch "$epoch_ns" --arg crc "$curl_rc" --arg http "$http_code" --arg latency "$time_total" '
        [$epoch, $crc, $http, $latency, (.status // ""), (.version // ""), (.height // 0),
         (.last_known_block_index // 0), (.outgoing_connections_count // 0), (.incoming_connections_count // 0),
         (.rpc_connections_count // 0), (.white_peerlist_size // 0), (.grey_peerlist_size // 0), (.top_block_hash // "")] | @tsv
      ' "$rpc_body" >> "$rpc_samples"
    else
      printf '%s\t%s\t%s\t%s\t\t\t0\t0\t0\t0\t0\t0\t0\t\n' "$epoch_ns" "$curl_rc" "$http_code" "$time_total" >> "$rpc_samples"
    fi
  fi

  sample_index=$((sample_index + 1))
  sleep 1
done

printf '%s daemon_process_gone pid=%s\n' "$(date --utc --iso-8601=ns)" "$pid" >> "$events"
systemctl show "$DAEMON_UNIT" --no-pager > "$runtime_dir/systemd-final.txt" 2>&1 || true
date --utc --iso-8601=ns > "$runtime_dir/monitor-ended-utc.txt"
cp -a "$runtime_dir/." "$BENCH_RESULT_DIR/"
