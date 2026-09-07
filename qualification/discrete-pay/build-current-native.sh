#!/usr/bin/env bash
# Separate disposable current-chain fixture; never a production daemon artifact.
set -euo pipefail
umask 077
test "$(id -un)" = payqual
root=/opt/discrete-pay-qualification
src="$root/current-native-src"
build="$root/current-native-build"
test ! -e "$src"
test -x "$root/current-attestation-binaries/walletd"
cd "$root/imports"
sha256sum --check current-walletd-SHA256SUMS
mkdir "$src"
tar -xf current-walletd-source.tar --no-same-owner -C "$src"
for target in PaymentGate/PaymentServiceJsonRpcMessages.cpp PaymentGate/PaymentServiceJsonRpcMessages.h PaymentGate/PaymentServiceJsonRpcServer.cpp PaymentGate/WalletService.cpp PaymentGate/WalletService.h Wallet/WalletGreen.cpp Wallet/WalletGreen.h CryptoNoteCore/Currency.cpp P2p/NetNode.cpp; do
  sed -i 's/\r$//' "$src/src/$target"
done
git -C "$src" apply --check "$root/imports/current-walletd-attestation.patch" "$root/pay/test/worker-runtime/native-core-loopback.patch" "$root/pay/test/worker-runtime/native-core-difficulty.patch"
git -C "$src" apply "$root/imports/current-walletd-attestation.patch" "$root/pay/test/worker-runtime/native-core-loopback.patch" "$root/pay/test/worker-runtime/native-core-difficulty.patch"
cmake -S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release -DARCH=default -DBUILD_TESTS=OFF -DDISCRETE_BOOST_PREFER_MODULE=ON
cmake --build "$build" --target Daemon --parallel 1
test ! -e "$root/pay/build/native-test/current-bin"
mkdir -p "$root/pay/build/native-test/current-bin/src" "$root/pay/build/native-test/current"
install -m 750 "$build/src/discreted" "$root/pay/build/native-test/current-bin/src/discreted"
install -m 750 "$root/current-attestation-binaries/walletd" "$root/pay/build/native-test/current-bin/src/walletd"
"$root/tools/node-v24.18.1-linux-x64/bin/node" "$root/imports/current-fixture-manifest.mjs"
echo 'PASS: disposable current-base native fixture built; payment qualification still required'
