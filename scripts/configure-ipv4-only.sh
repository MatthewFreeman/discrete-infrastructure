#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_ROOT
readonly SOURCE_CONFIG="${REPO_ROOT}/configs/sysctl/99-discrete-ipv4-only.conf"
readonly TARGET_CONFIG="/etc/sysctl.d/99-discrete-ipv4-only.conf"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

package_is_installed() {
    local package="$1"

    dpkg-query -W -f='${Status}\n' "${package}" 2>/dev/null \
        | grep -x 'install ok installed' >/dev/null
}

ensure_tools() {
    local packages=()

    command -v sysctl >/dev/null 2>&1 || packages+=(procps)
    command -v ip >/dev/null 2>&1 || packages+=(iproute2)
    command -v ss >/dev/null 2>&1 || packages+=(iproute2)

    if [[ ${#packages[@]} -gt 0 ]]; then
        printf 'Installing IPv4-only verification tools...\n'
        apt-get -o DPkg::Lock::Timeout=300 update
        DEBIAN_FRONTEND=noninteractive apt-get \
            -o DPkg::Lock::Timeout=300 \
            install -y "${packages[@]}"
    fi
}

verify_interface_flags() {
    local flag
    local value

    shopt -s nullglob
    local flags=(/proc/sys/net/ipv6/conf/*/disable_ipv6)
    shopt -u nullglob

    [[ ${#flags[@]} -gt 0 ]] \
        || fail "IPv6 interface sysctl flags are unavailable."

    for flag in "${flags[@]}"; do
        value="$(cat "${flag}")"
        [[ "${value}" == "1" ]] \
            || fail "IPv6 is still enabled by ${flag}: ${value}"
    done
}

verify_no_ipv6_addresses_or_routes() {
    local addresses
    local routes

    addresses="$(ip -6 -o address show 2>/dev/null || true)"
    routes="$(ip -6 route show table all 2>/dev/null || true)"

    if [[ -n "${addresses}" ]]; then
        printf 'Unexpected IPv6 addresses:\n%s\n' "${addresses}" >&2
        fail "IPv6 addresses remain after applying the IPv4-only policy."
    fi

    if [[ -n "${routes}" ]]; then
        printf 'Unexpected IPv6 routes:\n%s\n' "${routes}" >&2
        fail "IPv6 routes remain after applying the IPv4-only policy."
    fi
}

[[ ${EUID} -eq 0 ]] \
    || fail "Run IPv4-only configuration as root."

[[ -r "${SOURCE_CONFIG}" ]] \
    || fail "Managed IPv4-only sysctl config is unavailable: ${SOURCE_CONFIG}"

ensure_tools

install -m 0644 "${SOURCE_CONFIG}" "${TARGET_CONFIG}"
sysctl --load "${TARGET_CONFIG}"

verify_interface_flags
verify_no_ipv6_addresses_or_routes

printf 'IPv4-only interface policy is active.\n'
printf 'IPv6 addresses: none\n'
printf 'IPv6 routes: none\n'
