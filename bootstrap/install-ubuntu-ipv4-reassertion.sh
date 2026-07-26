#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_ROOT
readonly SOURCE_UNIT="${REPO_ROOT}/configs/systemd/discrete-ipv4-only-after-network.service"
readonly TARGET_UNIT="/etc/systemd/system/discrete-ipv4-only-after-network.service"
readonly UNIT_NAME="discrete-ipv4-only-after-network.service"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ ${EUID} -eq 0 ]] || fail "Run the Ubuntu IPv4 persistence installer as root."
[[ -r /etc/os-release ]] || fail "Cannot identify the operating system."

ID=""
VERSION_ID=""
# shellcheck disable=SC1091
source /etc/os-release

[[ "${ID:-}" == "ubuntu" ]] || fail "This persistence installer supports Ubuntu only."
[[ "${VERSION_ID:-}" == "24.04" ]] \
    || fail "This persistence installer supports Ubuntu 24.04, found ${VERSION_ID:-unknown}."

[[ -r "${SOURCE_UNIT}" ]] || fail "Managed systemd unit is unavailable: ${SOURCE_UNIT}"
[[ -r "${REPO_ROOT}/scripts/configure-ipv4-only.sh" ]] \
    || fail "Managed IPv4-only configuration script is unavailable."

install -m 0644 "${SOURCE_UNIT}" "${TARGET_UNIT}"
systemctl daemon-reload
systemctl enable "${UNIT_NAME}" >/dev/null

if [[ "${UBUNTU_IPV4_SERVICE_START_NOW:-0}" == "1" ]]; then
    systemctl restart "${UNIT_NAME}"
    systemctl is-active --quiet "${UNIT_NAME}" \
        || fail "Ubuntu post-network IPv4-only service did not become active."
fi

systemctl is-enabled --quiet "${UNIT_NAME}" \
    || fail "Ubuntu post-network IPv4-only service is not enabled."

printf 'Ubuntu post-network IPv4-only enforcement is installed and enabled.\n'
