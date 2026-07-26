#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this installer as root or with sudo." >&2
    exit 1
fi

bash "${REPO_ROOT}/scripts/configure-ipv4-only.sh"
bash "${REPO_ROOT}/scripts/configure-time-sync.sh"
"${REPO_ROOT}/scripts/apply-config.sh" all
"${REPO_ROOT}/scripts/verify.sh" all
