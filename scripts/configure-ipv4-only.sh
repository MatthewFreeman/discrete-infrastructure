#!/usr/bin/env bash
set -Eeuo pipefail

COMPAT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly COMPAT_DIR
readonly COMPAT_CANONICAL="${COMPAT_DIR}/../modules/host/scripts/configure-ipv4-only.sh"

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    exec bash "${COMPAT_CANONICAL}" "$@"
fi

source "${COMPAT_CANONICAL}"
