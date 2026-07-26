#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR

apt-get() {
    local real_apt_get="/usr/bin/apt-get"
    local lock_timeout="${APT_LOCK_TIMEOUT_SECONDS:-300}"
    local retry_interval=5
    local deadline
    local output
    local status

    [[ "${lock_timeout}" =~ ^[1-9][0-9]*$ ]] || {
        printf 'ERROR: APT_LOCK_TIMEOUT_SECONDS must be a positive integer.\n' >&2
        return 2
    }

    [[ -x "${real_apt_get}" ]] || {
        printf 'ERROR: Real apt-get executable is unavailable: %s\n' \
            "${real_apt_get}" >&2
        return 127
    }

    deadline=$((SECONDS + lock_timeout))

    while true; do
        output="$(mktemp)"

        if "${real_apt_get}" \
            -o "DPkg::Lock::Timeout=${lock_timeout}" \
            "$@" 2>&1 | tee "${output}"; then
            status=0
        else
            status=${PIPESTATUS[0]}
        fi

        if [[ ${status} -eq 0 ]]; then
            rm -f "${output}"
            return 0
        fi

        if ! grep -E \
            'Could not get lock|Unable to acquire.*lock|Unable to lock directory|Could not open lock file' \
            "${output}" >/dev/null; then
            rm -f "${output}"
            return "${status}"
        fi

        rm -f "${output}"

        if (( SECONDS >= deadline )); then
            printf 'ERROR: APT lock wait exceeded %s seconds.\n' \
                "${lock_timeout}" >&2
            return "${status}"
        fi

        printf '\n==> Package manager is busy; retrying in %s seconds\n' \
            "${retry_interval}" >&2
        sleep "${retry_interval}"
    done
}

export -f apt-get

exec bash "${SCRIPT_DIR}/debian-ipv4.sh" "$@"
