#!/usr/bin/env bash
set -Eeuo pipefail

component="${1:-all}"

verify_ssh() {
    echo "SSH effective configuration:"
    sshd -T | grep -E \
        '^(port|logingracetime|maxauthtries|x11forwarding|allowagentforwarding|passwordauthentication|permitrootlogin) '
}

case "${component}" in
    all)
        verify_ssh
        ;;
    ssh)
        verify_ssh
        ;;
    *)
        echo "Unknown component: ${component}" >&2
        exit 1
        ;;
esac
