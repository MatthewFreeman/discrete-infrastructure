#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR

apt-get() {
    local real_apt_get="${APT_GET_BIN:-/usr/bin/apt-get}"
    local lock_timeout="${APT_LOCK_TIMEOUT_SECONDS:-300}"
    local progress_interval="${APT_LOCK_PROGRESS_SECONDS:-30}"
    local status

    [[ "${lock_timeout}" =~ ^[1-9][0-9]*$ ]] || {
        printf 'ERROR: APT_LOCK_TIMEOUT_SECONDS must be a positive integer.\n' >&2
        return 2
    }

    [[ "${progress_interval}" =~ ^[1-9][0-9]*$ ]] || {
        printf 'ERROR: APT_LOCK_PROGRESS_SECONDS must be a positive integer.\n' >&2
        return 2
    }

    [[ -x "${real_apt_get}" ]] || {
        printf 'ERROR: Real apt-get executable is unavailable: %s\n' \
            "${real_apt_get}" >&2
        return 127
    }

    set +e
    "${real_apt_get}" \
        -o "DPkg::Lock::Timeout=${lock_timeout}" \
        "$@" 2>&1 \
        | awk \
            -v timeout="${lock_timeout}" \
            -v progress_interval="${progress_interval}" '
                /^Waiting for cache lock:/ {
                    now = systime()
                    if (!waiting) {
                        waiting = 1
                        started = now
                        last_progress = now
                        printf "==> Package manager is busy; waiting up to %s seconds\n", timeout
                        fflush()
                    } else if (now - last_progress >= progress_interval) {
                        printf "==> Still waiting for package manager lock (%s seconds elapsed)\n", now - started
                        fflush()
                        last_progress = now
                    }
                    next
                }

                { print; fflush() }
            '
    status=${PIPESTATUS[0]}
    set -e

    return "${status}"
}

export -f apt-get

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    exec bash "${SCRIPT_DIR}/debian-ipv4.sh" "$@"
fi
