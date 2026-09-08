#!/usr/bin/env bash
# Source archives are produced from immutable local Git commits, uploaded over
# pinned SSH and verified before extraction. No GitHub credential on the host.
set -euo pipefail
umask 077
cd /opt/discrete-pay-qualification
test "$(id -un)" = payqual
export PATH="$PWD/tools/node-v24.18.1-linux-x64/bin:$PWD/tools/pnpm/node_modules/.bin:$PATH"
test "$(node --version)" = v24.18.1
cd imports
sha256sum --check SHA256SUMS
cd ..
test ! -e pay
mkdir pay
tar -xf imports/pay-source.tar -C pay
cd pay
node ../tools/pnpm/node_modules/pnpm/bin/pnpm.cjs install --frozen-lockfile
node ../tools/pnpm/node_modules/pnpm/bin/pnpm.cjs run build
mkdir -p build/native-test/freeman-core
tar -xf ../imports/core-source.tar -C build/native-test/freeman-core
sed -i 's/\r$//' build/native-test/freeman-core/src/P2p/NetNode.cpp build/native-test/freeman-core/src/CryptoNoteCore/Currency.cpp
git -C build/native-test/freeman-core apply "$PWD/test/worker-runtime/native-core-loopback.patch" "$PWD/test/worker-runtime/native-core-difficulty.patch"
cmake -S build/native-test/freeman-core -B build/native-test/bin -DCMAKE_BUILD_TYPE=Release -DARCH=default -DBUILD_TESTS=OFF -DDISCRETE_BOOST_PREFER_MODULE=ON
cmake --build build/native-test/bin --target Daemon PaymentGateService --parallel 1
