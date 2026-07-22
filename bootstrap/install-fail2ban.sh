#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this script as root or with sudo." >&2
    exit 1
fi

echo "Installing Fail2Ban and systemd journal support..."

apt-get update

DEBIAN_FRONTEND=noninteractive apt-get install -y \
    fail2ban \
    python3-systemd

systemctl enable fail2ban

echo
echo "Installed version:"
fail2ban-client --version

echo
echo "Fail2Ban package is ready."
echo "The Git-managed jail configuration must now be applied."
