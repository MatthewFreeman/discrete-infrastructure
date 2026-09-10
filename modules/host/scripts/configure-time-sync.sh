#!/usr/bin/env bash
set -Eeuo pipefail

readonly SYNC_SERVICE="systemd-timesyncd.service"
readonly CONFLICTING_PACKAGES=(ntp ntpsec chrony openntpd)
readonly CONFLICTING_SERVICES=(
    ntp.service
    ntpsec.service
    chrony.service
    openntpd.service
)

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

package_is_installed() {
    local package="$1"

    dpkg-query -W -f='${Status}\n' "${package}" 2>/dev/null \
        | grep -x 'install ok installed' >/dev/null
}

udp_listener_exists() {
    local port="$1"
    local sockets

    sockets="$(ss -H -lnup 2>/dev/null || true)"

    awk -v expected_port=":${port}" '
        $4 ~ expected_port "$" {
            found = 1
        }

        END {
            exit !found
        }
    ' <<<"${sockets}"
}

wait_for_time_sync() {
    local attempt
    local synchronized

    for ((attempt = 1; attempt <= 60; attempt++)); do
        synchronized="$(timedatectl show -p NTPSynchronized --value 2>/dev/null || true)"

        if [[ "${synchronized}" == "yes" ]]; then
            return 0
        fi

        sleep 1
    done

    printf 'ERROR: Clock did not report NTPSynchronized=yes within 60 seconds.\n' >&2
    printf '\nCurrent time synchronization state:\n' >&2
    timedatectl status >&2 || true
    printf '\nRecent systemd-timesyncd log:\n' >&2
    journalctl -u "${SYNC_SERVICE}" -n 60 --no-pager >&2 || true

    return 1
}

[[ ${EUID} -eq 0 ]] \
    || fail "Run time synchronization configuration as root."

command -v apt-get >/dev/null 2>&1 \
    || fail "apt-get is unavailable."
command -v ss >/dev/null 2>&1 \
    || fail "The ss command is unavailable."
command -v timedatectl >/dev/null 2>&1 \
    || fail "timedatectl is unavailable."

conflicting_installed=0
for package in "${CONFLICTING_PACKAGES[@]}"; do
    if package_is_installed "${package}"; then
        conflicting_installed=1
        break
    fi
done

if [[ ${conflicting_installed} -eq 1 ]]; then
    printf 'Removing NTP server packages...\n'

    for service in "${CONFLICTING_SERVICES[@]}"; do
        systemctl disable --now "${service}" >/dev/null 2>&1 || true
    done

    DEBIAN_FRONTEND=noninteractive apt-get \
        -o DPkg::Lock::Timeout=300 \
        purge -y \
        "${CONFLICTING_PACKAGES[@]}"
fi

if ! package_is_installed systemd-timesyncd; then
    printf 'Installing systemd-timesyncd...\n'

    apt-get -o DPkg::Lock::Timeout=300 update
    DEBIAN_FRONTEND=noninteractive apt-get \
        -o DPkg::Lock::Timeout=300 \
        install -y systemd-timesyncd
fi

systemctl unmask "${SYNC_SERVICE}" >/dev/null 2>&1 || true
systemctl enable --now "${SYNC_SERVICE}"
systemctl restart "${SYNC_SERVICE}"

systemctl is-enabled --quiet "${SYNC_SERVICE}" \
    || fail "systemd-timesyncd is not enabled."
systemctl is-active --quiet "${SYNC_SERVICE}" \
    || fail "systemd-timesyncd is not active."

wait_for_time_sync \
    || fail "Client-only time synchronization did not become ready."

if udp_listener_exists 123; then
    printf 'ERROR: A process still listens on UDP 123:\n' >&2
    ss -H -lnup | awk '$4 ~ /:123$/' >&2 || true
    fail "NTP server listener remains after time synchronization cleanup."
fi

printf 'Client-only time synchronization is active.\n'
printf 'NTP synchronized: yes\n'
printf 'UDP 123 listener: none\n'
