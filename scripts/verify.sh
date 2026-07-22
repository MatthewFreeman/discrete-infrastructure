#!/usr/bin/env bash
set -Eeuo pipefail

component="${1:-all}"

require_match() {
    local content="$1"
    local pattern="$2"
    local description="$3"

    if ! grep -Eq "${pattern}" <<<"${content}"; then
        echo "Verification failed: ${description}" >&2
        return 1
    fi
}

verify_ssh() {
    echo "SSH effective configuration:"

    sshd -T | grep -E \
        '^(port|logingracetime|maxauthtries|x11forwarding|allowagentforwarding|passwordauthentication|permitrootlogin) '
}

verify_nftables() {
    echo "nftables service:"

    systemctl is-enabled nftables
    systemctl is-active nftables

    local input_rules
    local forward_rules
    local output_rules

    input_rules="$(nft list chain inet filter input)"
    forward_rules="$(nft list chain inet filter forward)"
    output_rules="$(nft list chain inet filter output)"

    require_match "${input_rules}" \
        'policy drop' \
        'input policy must be drop'

    require_match "${input_rules}" \
        'iifname "lo".*accept' \
        'loopback traffic must be accepted'

    require_match "${input_rules}" \
        'ct state established,related.*accept' \
        'established and related traffic must be accepted'

    require_match "${input_rules}" \
        'ct state invalid.*drop' \
        'invalid traffic must be dropped'

    require_match "${input_rules}" \
        'meta l4proto icmp.*accept' \
        'IPv4 ICMP must be accepted'

    require_match "${input_rules}" \
        'meta l4proto ipv6-icmp.*accept' \
        'IPv6 ICMP must be accepted'

    local port
    for port in 22822 9330 9331 9332; do
        require_match "${input_rules}" \
            "tcp dport ${port}.*accept" \
            "TCP port ${port} must be accepted"
    done

    require_match "${forward_rules}" \
        'policy drop' \
        'forward policy must be drop'

    require_match "${output_rules}" \
        'policy accept' \
        'output policy must be accept'

    echo
    echo "${input_rules}"
    echo
    echo "${forward_rules}"
    echo
    echo "${output_rules}"
    echo
    echo "nftables verification passed."
}

case "${component}" in
    all)
        verify_ssh
        echo
        verify_nftables
        ;;
    ssh)
        verify_ssh
        ;;
    nftables)
        verify_nftables
        ;;
    *)
        echo "Unknown component: ${component}" >&2
        exit 1
        ;;
esac
