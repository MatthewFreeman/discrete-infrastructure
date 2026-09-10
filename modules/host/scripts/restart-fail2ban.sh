#!/usr/bin/env bash
set -Eeuo pipefail

readonly MAX_ATTEMPTS=20
readonly SLEEP_SECONDS=0.5
readonly TABLE="f2b-table"

echo "Enabling Fail2Ban..."
systemctl enable fail2ban >/dev/null

echo "Stopping Fail2Ban..."
systemctl stop fail2ban

# Remove only Fail2Ban's dedicated table. This guarantees a clean migration
# from the previous inet family to the IPv4-only ip family, even after an
# interrupted or failed daemon shutdown.
for family in ip inet ip6; do
    if nft list table "${family}" "${TABLE}" >/dev/null 2>&1; then
        nft delete table "${family}" "${TABLE}"
    fi
done

echo "Starting Fail2Ban..."
systemctl start fail2ban

echo "Waiting for the Fail2Ban control socket..."

for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
    if response="$(fail2ban-client ping 2>/dev/null)"; then
        printf '%s\n' "${response}"
        echo "Fail2Ban is ready."
        exit 0
    fi

    if systemctl is-failed --quiet fail2ban; then
        echo "Fail2Ban entered the failed state." >&2
        systemctl status fail2ban --no-pager -l >&2 || true
        journalctl -u fail2ban -n 50 --no-pager >&2 || true
        exit 1
    fi

    sleep "${SLEEP_SECONDS}"
done

echo "Fail2Ban did not become ready within 10 seconds." >&2
systemctl status fail2ban --no-pager -l >&2 || true
journalctl -u fail2ban -n 50 --no-pager >&2 || true
exit 1
