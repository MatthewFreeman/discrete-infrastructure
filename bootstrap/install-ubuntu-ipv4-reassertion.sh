#!/usr/bin/env bash
set -Eeuo pipefail

COMPAT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly COMPAT_DIR
readonly COMPAT_CANONICAL="${COMPAT_DIR}/../modules/host/bootstrap/install-ubuntu-ipv4-reassertion.sh"

exec bash "${COMPAT_CANONICAL}" "$@"
