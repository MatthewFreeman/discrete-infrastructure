#!/usr/bin/env bash
# Run after native/service units have stopped, on the disposable Pay host only.
set -euo pipefail
test "$(id -un)" = payqual
cd /opt/discrete-pay-qualification/pay
export PATH="/opt/discrete-pay-qualification/tools/node-v24.18.1-linux-x64/bin:/opt/discrete-pay-qualification/tools/pnpm/node_modules/.bin:$PATH"
test "$(node --version)" = v24.18.1
node --check test/worker-runtime/native-chain-qualification.mjs
node --check ../imports/service-role.mjs
node --check ../imports/service-probe.mjs
pnpm run typecheck
pnpm exec vitest run --maxWorkers=1
pnpm run test:gateway-runtime
pnpm run test:worker-runtime
printf '%s\n' 'PASS: Linux typecheck, complete single-worker test suite and compiled gateway/worker smoke'
