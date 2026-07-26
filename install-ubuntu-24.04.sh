#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this installer as root or with sudo." >&2
    exit 1
fi

[[ -r /etc/os-release ]] || {
    echo "ERROR: Cannot identify the operating system." >&2
    exit 1
}

ID=""
VERSION_ID=""
# shellcheck disable=SC1091
source /etc/os-release

[[ "${ID:-}" == "ubuntu" ]] || {
    echo "ERROR: This installer supports Ubuntu only." >&2
    exit 1
}

[[ "${VERSION_ID:-}" == "24.04" ]] || {
    echo "ERROR: This installer supports Ubuntu 24.04, found ${VERSION_ID:-unknown}." >&2
    exit 1
}

# Keep Ubuntu in the same deterministic OpenSSH service mode selected during bootstrap.
systemctl disable --now ssh.socket >/dev/null 2>&1 || true
systemctl enable --now ssh.service

bash "${REPO_ROOT}/scripts/configure-ipv4-only.sh"
bash "${REPO_ROOT}/scripts/configure-time-sync.sh"
"${REPO_ROOT}/scripts/apply-config.sh" all
"${REPO_ROOT}/scripts/verify.sh" all
