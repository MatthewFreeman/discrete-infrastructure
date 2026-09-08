#!/usr/bin/env bash
# Disposable current-base compatibility candidate. No consensus/testnet overlays.
set -euo pipefail
umask 077
test "$(id -un)" = payqual
root=/opt/discrete-pay-qualification
cd "$root/imports"
sha256sum --check current-walletd-SHA256SUMS
src="$root/current-walletd-src-2"
build="$root/current-walletd-build-2"
test ! -e "$src"
mkdir "$src"
tar -xf current-walletd-source.tar --no-same-owner -C "$src"
# Windows-produced Git archive has CRLF. Normalize only the seven patch targets.
for target in PaymentGate/PaymentServiceJsonRpcMessages.cpp PaymentGate/PaymentServiceJsonRpcMessages.h PaymentGate/PaymentServiceJsonRpcServer.cpp PaymentGate/WalletService.cpp PaymentGate/WalletService.h Wallet/WalletGreen.cpp Wallet/WalletGreen.h; do
  sed -i 's/\r$//' "$src/src/$target"
done
git -C "$src" apply --check "$root/imports/current-walletd-attestation.patch"
git -C "$src" apply "$root/imports/current-walletd-attestation.patch"
cmake -S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release -DARCH=default -DBUILD_TESTS=OFF -DDISCRETE_BOOST_PREFER_MODULE=ON
cmake --build "$build" --target PaymentGateService --parallel 1
echo 'PASS: current-base walletd candidate compilation only; runtime qualification still required'
