#!/usr/bin/env bash
# Explicitly authorized dedicated Debian host only. No firewall or SSH changes.
set -euo pipefail
umask 027
. /etc/os-release
test "$ID:$VERSION_ID" = debian:12
test "$(uname -m)" = x86_64
test ! -e /opt/discrete-pay-qualification
! id payqual >/dev/null 2>&1
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential cmake git libboost-all-dev libssl-dev pkg-config curl xz-utils
useradd --system --user-group --home-dir /opt/discrete-pay-qualification --shell /usr/sbin/nologin payqual
install -d -m 0750 -o payqual -g payqual /opt/discrete-pay-qualification
runuser -u payqual -- bash <<'BUILD'
set -euo pipefail
umask 077
cd /opt/discrete-pay-qualification
mkdir tools
cd tools
curl --fail --location --proto '=https' --tlsv1.2 -o SHASUMS256.txt https://nodejs.org/dist/v24.18.1/SHASUMS256.txt
curl --fail --location --proto '=https' --tlsv1.2 -o node-v24.18.1-linux-x64.tar.xz https://nodejs.org/dist/v24.18.1/node-v24.18.1-linux-x64.tar.xz
grep ' node-v24.18.1-linux-x64.tar.xz$' SHASUMS256.txt | sha256sum --check -
tar -xf node-v24.18.1-linux-x64.tar.xz
export PATH="$PWD/node-v24.18.1-linux-x64/bin:$PATH"
node --version
npm install --prefix "$PWD/pnpm" pnpm@11.19.0 --ignore-scripts
BUILD
