#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT
readonly CANONICAL_ENTRYPOINT="${REPO_ROOT}/modules/host/install.sh"

exec bash "${CANONICAL_ENTRYPOINT}" "$@"
