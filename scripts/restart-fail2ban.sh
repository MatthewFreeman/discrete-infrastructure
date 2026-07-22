#!/usr/bin/env bash
set -Eeuo pipefail

readonly MAX_ATTEMPTS=20
readonly SLEEP_SECONDS=0.5

echo "Enabling Fail2Ban..."
systemctl enable fail2ban >/dev/null

echo "Restarting Fail2Ban..."
systemctl restart fail2ban

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
