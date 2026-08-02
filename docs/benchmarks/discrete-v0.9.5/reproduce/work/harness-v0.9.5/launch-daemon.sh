#!/usr/bin/env bash
set -euo pipefail

readonly ENV_FILE=/opt/discrete-benchmark/state/v.0.9.5/current.env

if [[ ! -r "$ENV_FILE" ]]; then
  echo "missing benchmark environment: $ENV_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

: "${BENCH_RUN_ID:?}"
: "${BENCH_VARIANT:?}"
: "${BENCH_BINARY:?}"
: "${BENCH_EXPECTED_SHA256:?}"
: "${BENCH_DATA_DIR:?}"
: "${BENCH_RESULT_DIR:?}"
: "${BENCH_P2P_PORT:?}"
: "${BENCH_RPC_PORT:?}"

if [[ "$BENCH_VARIANT" != "ubuntu24.04" && "$BENCH_VARIANT" != "linux-universal" ]]; then
  echo "invalid variant: $BENCH_VARIANT" >&2
  exit 1
fi

if [[ ! -x "$BENCH_BINARY" ]]; then
  echo "binary is not executable: $BENCH_BINARY" >&2
  exit 1
fi

actual_sha256=$(sha256sum "$BENCH_BINARY" | awk '{print $1}')
if [[ "$actual_sha256" != "$BENCH_EXPECTED_SHA256" ]]; then
  echo "binary SHA256 mismatch: expected=$BENCH_EXPECTED_SHA256 actual=$actual_sha256" >&2
  exit 1
fi

if pgrep -x discreted >/dev/null 2>&1; then
  echo "another discreted process is already running" >&2
  pgrep -a -x discreted >&2 || true
  exit 1
fi

install -d -m 0755 "$BENCH_DATA_DIR" "$BENCH_RESULT_DIR"

date +%s%N > "$BENCH_RESULT_DIR/launch-epoch-ns.txt"
{
  printf 'run_id=%s\n' "$BENCH_RUN_ID"
  printf 'variant=%s\n' "$BENCH_VARIANT"
  printf 'binary=%s\n' "$BENCH_BINARY"
  printf 'binary_sha256=%s\n' "$actual_sha256"
  printf 'data_dir=%s\n' "$BENCH_DATA_DIR"
  printf 'result_dir=%s\n' "$BENCH_RESULT_DIR"
  printf 'p2p_port=%s\n' "$BENCH_P2P_PORT"
  printf 'rpc_port=%s\n' "$BENCH_RPC_PORT"
  printf 'started_utc=%s\n' "$(date --utc --iso-8601=ns)"
} > "$BENCH_RESULT_DIR/run-metadata.txt"

exec "$BENCH_BINARY" \
  --data-dir "$BENCH_DATA_DIR" \
  --log-file "$BENCH_RESULT_DIR/discreted.log" \
  --log-level 2 \
  --no-console \
  --rpc-bind-ip 127.0.0.1 \
  --rpc-bind-port "$BENCH_RPC_PORT" \
  --p2p-bind-ip 0.0.0.0 \
  --p2p-bind-port "$BENCH_P2P_PORT" \
  --p2p-external-port "$BENCH_P2P_PORT"
