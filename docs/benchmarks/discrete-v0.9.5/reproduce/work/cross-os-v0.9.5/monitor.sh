#!/usr/bin/env bash
set -u

readonly ENV_FILE=/opt/discrete-benchmark/state/v.0.9.5/cross-os/current.env
readonly DAEMON_UNIT=discrete-crossos-daemon.service

if [[ ! -r "$ENV_FILE" ]]; then
  echo "missing cross-OS benchmark environment: $ENV_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

: "${BENCH_RUN_ID:?}"
: "${BENCH_RESULT_DIR:?}"
: "${BENCH_RPC_PORT:?}"

runtime_dir="/run/discrete-crossos-benchmark/$BENCH_RUN_ID"
install -d -m 0755 "$runtime_dir" "$BENCH_RESULT_DIR" || exit 1

samples="$runtime_dir/process-host-samples.tsv"
rpc_samples="$runtime_dir/rpc-samples.tsv"
events="$runtime_dir/events.log"

printf 'epoch_ns\tpid\tstate\tutime_ticks\tstime_ticks\tminflt\tmajflt\tthreads\tvsize_bytes\trss_pages\tvmrss_kb\tvmhwm_kb\tvoluntary_ctxt\tnonvoluntary_ctxt\trchar\twchar\tread_bytes\twrite_bytes\tsyscr\tsyscw\topen_fds\tnet_rx_bytes\tnet_tx_bytes\tblock_reads_completed\tblock_sectors_read\tblock_writes_completed\tblock_sectors_written\thost_cpu_user\thost_cpu_nice\thost_cpu_system\thost_cpu_idle\thost_cpu_iowait\thost_cpu_irq\thost_cpu_softirq\thost_cpu_steal\tmem_total_kb\tmem_available_kb\tmem_free_kb\tcached_kb\tswap_total_kb\tswap_free_kb\tvm_pswpin\tvm_pswpout\tvm_pgscan_kswapd\tvm_pgscan_direct\tvm_pgsteal_kswapd\tvm_pgsteal_direct\tvm_oom_kill\tpsi_memory_some_total_us\tpsi_memory_full_total_us\tpsi_io_some_total_us\tpsi_io_full_total_us\tpsi_cpu_some_total_us\n' > "$samples"
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

initial_stat_line=$(<"/proc/$pid/stat")
initial_stat_tail=${initial_stat_line#*) }
read -r -a initial_stat_fields <<< "$initial_stat_tail"
pid_starttime=${initial_stat_fields[19]:-}
if [[ -z "$pid_starttime" ]]; then
  printf '%s daemon_starttime_not_found pid=%s\n' "$(date --utc --iso-8601=ns)" "$pid" >> "$events"
  cp -a "$runtime_dir/." "$BENCH_RESULT_DIR/"
  exit 1
fi

net_dev=$(ip -o route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i=="dev") {print $(i+1); exit}}')
root_source=$(findmnt -n -o SOURCE /)
block_dev=$(lsblk -no PKNAME "$root_source" 2>/dev/null | head -n 1)
[[ -n "$block_dev" ]] || block_dev=$(basename "$root_source" | sed -E 's/[0-9]+$//')
page_size=$(getconf PAGESIZE)
printf '%s daemon_pid=%s net_dev=%s block_dev=%s page_size=%s\n' "$(date --utc --iso-8601=ns)" "$pid" "$net_dev" "$block_dev" "$page_size" >> "$events"

while [[ -r "/proc/$pid/stat" && -r "/proc/$pid/status" && -r "/proc/$pid/io" ]]; do
  epoch_ns=$(date +%s%N)
  if ! stat_line=$(<"/proc/$pid/stat") || [[ -z "$stat_line" ]]; then
    break
  fi
  stat_tail=${stat_line#*) }
  read -r -a stat_fields <<< "$stat_tail"
  if [[ ${stat_fields[19]:-} != "$pid_starttime" ]]; then
    printf '%s daemon_pid_reused pid=%s\n' "$(date --utc --iso-8601=ns)" "$pid" >> "$events"
    break
  fi
  state=${stat_fields[0]:-}
  minflt=${stat_fields[7]:-0}
  majflt=${stat_fields[9]:-0}
  utime_ticks=${stat_fields[11]:-0}
  stime_ticks=${stat_fields[12]:-0}
  threads=${stat_fields[17]:-0}
  vsize_bytes=${stat_fields[20]:-0}
  rss_pages=${stat_fields[21]:-0}

  if ! status_values=$(awk '/^VmRSS:/ {rss=$2} /^VmHWM:/ {hwm=$2} /^voluntary_ctxt_switches:/ {vol=$2} /^nonvoluntary_ctxt_switches:/ {nonvol=$2} END {printf "%s %s %s %s\n", rss+0, hwm+0, vol+0, nonvol+0}' "/proc/$pid/status" 2>/dev/null); then
    break
  fi
  read -r vmrss_kb vmhwm_kb voluntary_ctxt nonvoluntary_ctxt <<< "$status_values"
  if ! io_values=$(awk '/^rchar:/ {rchar=$2} /^wchar:/ {wchar=$2} /^read_bytes:/ {rb=$2} /^write_bytes:/ {wb=$2} /^syscr:/ {syscr=$2} /^syscw:/ {syscw=$2} END {printf "%s %s %s %s %s %s\n", rchar+0, wchar+0, rb+0, wb+0, syscr+0, syscw+0}' "/proc/$pid/io" 2>/dev/null); then
    break
  fi
  read -r rchar wchar read_bytes write_bytes syscr syscw <<< "$io_values"
  open_fds=$(find "/proc/$pid/fd" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)
  net_rx_bytes=$(<"/sys/class/net/$net_dev/statistics/rx_bytes")
  net_tx_bytes=$(<"/sys/class/net/$net_dev/statistics/tx_bytes")
  read -r block_reads _ block_sectors_read _ block_writes _ block_sectors_written _ < "/sys/block/$block_dev/stat"
  read -r _ host_user host_nice host_system host_idle host_iowait host_irq host_softirq host_steal _ < /proc/stat

  read -r mem_total_kb mem_available_kb mem_free_kb cached_kb swap_total_kb swap_free_kb < <(
    awk '/^MemTotal:/ {mt=$2} /^MemAvailable:/ {ma=$2} /^MemFree:/ {mf=$2} /^Cached:/ {c=$2} /^SwapTotal:/ {st=$2} /^SwapFree:/ {sf=$2} END {print mt+0, ma+0, mf+0, c+0, st+0, sf+0}' /proc/meminfo
  )
  read -r vm_pswpin vm_pswpout vm_pgscan_kswapd vm_pgscan_direct vm_pgsteal_kswapd vm_pgsteal_direct vm_oom_kill < <(
    awk '$1=="pswpin" {a=$2} $1=="pswpout" {b=$2} $1=="pgscan_kswapd" {c=$2} $1=="pgscan_direct" {d=$2} $1=="pgsteal_kswapd" {e=$2} $1=="pgsteal_direct" {f=$2} $1=="oom_kill" {g=$2} END {print a+0, b+0, c+0, d+0, e+0, f+0, g+0}' /proc/vmstat
  )
  read -r psi_memory_some psi_memory_full < <(
    awk '{for (i=1; i<=NF; i++) if ($i ~ /^total=/) {split($i,a,"="); if ($1=="some") s=a[2]; else if ($1=="full") f=a[2]}} END {print s+0, f+0}' /proc/pressure/memory
  )
  read -r psi_io_some psi_io_full < <(
    awk '{for (i=1; i<=NF; i++) if ($i ~ /^total=/) {split($i,a,"="); if ($1=="some") s=a[2]; else if ($1=="full") f=a[2]}} END {print s+0, f+0}' /proc/pressure/io
  )
  psi_cpu_some=$(awk '$1=="some" {for (i=1; i<=NF; i++) if ($i ~ /^total=/) {split($i,a,"="); print a[2]+0; exit}}' /proc/pressure/cpu)

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' \
    "$epoch_ns" "$pid" "$state" "$utime_ticks" "$stime_ticks" "$minflt" "$majflt" "$threads" "$vsize_bytes" "$rss_pages" \
    "$vmrss_kb" "$vmhwm_kb" "$voluntary_ctxt" "$nonvoluntary_ctxt" "$rchar" "$wchar" "$read_bytes" "$write_bytes" "$syscr" "$syscw" \
    "$open_fds" "$net_rx_bytes" "$net_tx_bytes" "$block_reads" "$block_sectors_read" "$block_writes" "$block_sectors_written" \
    "$host_user" "$host_nice" "$host_system" "$host_idle" "$host_iowait" "$host_irq" "$host_softirq" "$host_steal" >> "$samples"
  printf '\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$mem_total_kb" "$mem_available_kb" "$mem_free_kb" "$cached_kb" "$swap_total_kb" "$swap_free_kb" \
    "$vm_pswpin" "$vm_pswpout" "$vm_pgscan_kswapd" "$vm_pgscan_direct" "$vm_pgsteal_kswapd" "$vm_pgsteal_direct" "$vm_oom_kill" \
    "$psi_memory_some" "$psi_memory_full" "$psi_io_some" "$psi_io_full" "$psi_cpu_some" >> "$samples"

  rpc_body="$runtime_dir/rpc-body.tmp"
  rpc_meta=$(curl --silent --show-error --max-time 2 --output "$rpc_body" --write-out '%{http_code}\t%{time_total}' "http://127.0.0.1:$BENCH_RPC_PORT/getinfo" 2>>"$events")
  curl_rc=$?
  http_code=${rpc_meta%%$'\t'*}
  time_total=${rpc_meta#*$'\t'}
  if (( curl_rc == 0 )) && [[ "$http_code" == "200" ]] && jq -e . "$rpc_body" >/dev/null 2>&1; then
    jq -r --arg epoch "$epoch_ns" --arg crc "$curl_rc" --arg http "$http_code" --arg latency "$time_total" '[$epoch,$crc,$http,$latency,(.status//""),(.version//""),(.height//0),(.last_known_block_index//0),(.outgoing_connections_count//0),(.incoming_connections_count//0),(.rpc_connections_count//0),(.white_peerlist_size//0),(.grey_peerlist_size//0),(.top_block_hash//"")] | @tsv' "$rpc_body" >> "$rpc_samples"
  else
    printf '%s\t%s\t%s\t%s\t\t\t0\t0\t0\t0\t0\t0\t0\t\n' "$epoch_ns" "$curl_rc" "$http_code" "$time_total" >> "$rpc_samples"
  fi
  sleep 1
done

printf '%s daemon_process_gone pid=%s\n' "$(date --utc --iso-8601=ns)" "$pid" >> "$events"
systemctl show "$DAEMON_UNIT" --no-pager > "$runtime_dir/systemd-final.txt" 2>&1 || true
date --utc --iso-8601=ns > "$runtime_dir/monitor-ended-utc.txt"
cp -a "$runtime_dir/." "$BENCH_RESULT_DIR/"
