#!/usr/bin/env bash
set -Eeuo pipefail

UBUNTU_RUNNER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly UBUNTU_RUNNER_DIR

# Reuse the validated APT lock-handling wrapper without changing the Debian entrypoint.
# shellcheck source=bootstrap/run.sh
source "${UBUNTU_RUNNER_DIR}/run.sh"

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    case "${1:-}" in
        prepare|finalize)
            bash "${UBUNTU_RUNNER_DIR}/install-ubuntu-ipv4-reassertion.sh"
            ;;
    esac

    exec bash "${UBUNTU_RUNNER_DIR}/ubuntu-24.04-ipv4.sh" "$@"
fi
