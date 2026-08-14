#!/usr/bin/env bash
set -Eeuo pipefail

COMPAT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly COMPAT_DIR
readonly COMPAT_CANONICAL="${COMPAT_DIR}/../modules/host/bootstrap/run.sh"

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    exec bash "${COMPAT_CANONICAL}" "$@"
fi

# shellcheck source=modules/host/bootstrap/run.sh
source "${COMPAT_CANONICAL}"
