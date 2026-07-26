#!/usr/bin/env bash
set -Eeuo pipefail

readonly BOOTSTRAP_SSH_PORT="22"
readonly FINAL_SSH_PORT="22822"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_root() {
    [[ ${EUID} -eq 0 ]] \
        || fail "Run verification as root."
}

tcp_listener_exists() {
    local port="$1"
    local listeners

    listeners="$(ss -H -lntp 2>/dev/null || true)"

    awk -v expected_port=":${port}" '
        $4 ~ expected_port "$" && /users:\(\("sshd"/ {
            found = 1
        }

        END {
            exit !found
        }
    ' <<<"${listeners}"
}

nft_chain_has_tcp_port() {
    local family="$1"
    local table="$2"
    local chain="$3"
    local port="$4"
    local rules

    rules="$(nft list chain "${family}" "${table}" "${chain}" 2>/dev/null)" \
        || return 1

    awk -v expected_port="${port}" '
        /tcp dport/ {
            line = $0
            gsub(/[{},]/, " ", line)

            count = split(line, fields, /[[:space:]]+/)

            for (i = 1; i <= count; i++) {
                if (fields[i] == expected_port) {
                    found = 1
                }
            }
        }

        END {
            exit !found
        }
    ' <<<"${rules}"
}

wait_for_fail2ban_table() {
    local attempt

    for attempt in {1..40}; do
        if nft list table inet f2b-table >/dev/null 2>&1; then
            return 0
        fi

        sleep 0.25
    done

    return 1
}

fail2ban_rule_has_tcp_port() {
    local port="$1"
    local rules

    rules="$(nft list table inet f2b-table 2>/dev/null)" \
        || return 1

    awk -v expected_port="${port}" '
        /tcp dport/ && /@addr-set-sshd/ {
            line = $0
            gsub(/[{},]/, " ", line)

            count = split(line, fields, /[[:space:]]+/)

            for (i = 1; i <= count; i++) {
                if (fields[i] == expected_port) {
                    found = 1
                }
            }
        }

        END {
            exit !found
        }
    ' <<<"${rules}"
}

verify_no_ufw() {
    if dpkg-query -W -f='${Status}\n' ufw 2>/dev/null \
        | grep -x 'install ok installed' >/dev/null; then
        fail "UFW package is still installed."
    fi

    if systemctl is-active --quiet ufw.service 2>/dev/null; then
        fail "UFW service is still active."
    fi

    if nft list table ip filter >/dev/null 2>&1; then
        fail "Legacy IPv4 filter table still exists."
    fi

    if nft list table ip6 filter >/dev/null 2>&1; then
        fail "Legacy IPv6 filter table still exists."
    fi

    if nft list ruleset | grep -E '(^|[^[:alnum:]_])ufw6?-' >/dev/null; then
        fail "Residual UFW chains remain in nftables."
    fi

    printf 'UFW is absent and no legacy UFW tables remain.\n'
}

verify_ssh_final() {
    local effective
    local ports

    sshd -t
    systemctl is-enabled --quiet ssh \
        || fail "SSH service is not enabled."
    systemctl is-active --quiet ssh \
        || fail "SSH service is not active."

    effective="$(sshd -T)"

    mapfile -t ports < <(
        awk '$1 == "port" { print $2 }' <<<"${effective}"
    )

    [[ ${#ports[@]} -eq 1 && "${ports[0]}" == "${FINAL_SSH_PORT}" ]] \
        || fail "Effective SSH ports are not exactly: ${FINAL_SSH_PORT}."

    grep -x 'permitrootlogin no' <<<"${effective}" >/dev/null \
        || fail "Direct root SSH login is not disabled."

    grep -x 'passwordauthentication yes' <<<"${effective}" >/dev/null \
        || fail "SSH password authentication is not enabled."

    grep -x 'pubkeyauthentication yes' <<<"${effective}" >/dev/null \
        || fail "SSH public-key authentication is not enabled."

    tcp_listener_exists "${FINAL_SSH_PORT}" \
        || fail "sshd is not listening on TCP ${FINAL_SSH_PORT}."

    if tcp_listener_exists "${BOOTSTRAP_SSH_PORT}"; then
        fail "sshd still listens on temporary TCP ${BOOTSTRAP_SSH_PORT}."
    fi

    printf 'SSH final-state verification passed.\n'
}

verify_nftables_common() {
    systemctl is-enabled --quiet nftables \
        || fail "nftables service is not enabled."
    systemctl is-active --quiet nftables \
        || fail "nftables service is not active."

    nft list table inet discrete_filter >/dev/null \
        || fail "inet discrete_filter table is missing."

    nft_chain_has_tcp_port inet discrete_filter input "${FINAL_SSH_PORT}" \
        || fail "Firewall does not allow SSH TCP ${FINAL_SSH_PORT}."

    nft_chain_has_tcp_port inet discrete_filter input 9330 \
        || fail "Firewall does not allow Discrete P2P TCP 9330."

    nft_chain_has_tcp_port inet discrete_filter input 9331 \
        || fail "Firewall does not allow Discrete RPC HTTP TCP 9331."

    nft_chain_has_tcp_port inet discrete_filter input 9332 \
        || fail "Firewall does not allow Discrete RPC HTTPS TCP 9332."

    verify_no_ufw
}

verify_nftables_bootstrap() {
    verify_nftables_common

    nft_chain_has_tcp_port inet discrete_filter input "${BOOTSTRAP_SSH_PORT}" \
        || fail "Bootstrap firewall does not allow SSH TCP ${BOOTSTRAP_SSH_PORT}."

    printf 'nftables bootstrap-state verification passed.\n'
}

verify_nftables_final() {
    verify_nftables_common

    if nft_chain_has_tcp_port inet discrete_filter input "${BOOTSTRAP_SSH_PORT}"; then
        fail "Final firewall still allows temporary SSH TCP ${BOOTSTRAP_SSH_PORT}."
    fi

    printf 'nftables final-state verification passed.\n'
}

verify_fail2ban_common() {
    systemctl is-enabled --quiet fail2ban \
        || fail "Fail2Ban service is not enabled."
    systemctl is-active --quiet fail2ban \
        || fail "Fail2Ban service is not active."

    fail2ban-client ping | grep -x 'Server replied: pong' >/dev/null \
        || fail "Fail2Ban control socket did not reply."

    fail2ban-client status sshd >/dev/null \
        || fail "Fail2Ban sshd jail is not active."

    wait_for_fail2ban_table \
        || fail "Fail2Ban nftables table was not initialized."

    fail2ban_rule_has_tcp_port "${FINAL_SSH_PORT}" \
        || fail "Fail2Ban does not protect SSH TCP ${FINAL_SSH_PORT}."
}

verify_fail2ban_bootstrap() {
    verify_fail2ban_common

    fail2ban_rule_has_tcp_port "${BOOTSTRAP_SSH_PORT}" \
        || fail "Fail2Ban does not protect bootstrap SSH TCP ${BOOTSTRAP_SSH_PORT}."

    printf 'Fail2Ban bootstrap-state verification passed.\n'
}

verify_fail2ban_final() {
    verify_fail2ban_common

    if fail2ban_rule_has_tcp_port "${BOOTSTRAP_SSH_PORT}"; then
        fail "Fail2Ban still targets temporary SSH TCP ${BOOTSTRAP_SSH_PORT}."
    fi

    printf 'Fail2Ban final-state verification passed.\n'
}

verify_all_final() {
    verify_ssh_final
    verify_nftables_final
    verify_fail2ban_final
    printf 'Complete final-state verification passed.\n'
}

usage() {
    cat <<EOF
Usage:
  $0 ssh
  $0 nftables
  $0 fail2ban
  $0 nftables-bootstrap
  $0 fail2ban-bootstrap
  $0 all

Final-state checks:
  ssh, nftables, fail2ban, all

Temporary prepare-phase checks:
  nftables-bootstrap, fail2ban-bootstrap
EOF
}

main() {
    require_root

    case "${1:-}" in
        ssh)
            verify_ssh_final
            ;;
        nftables)
            verify_nftables_final
            ;;
        fail2ban)
            verify_fail2ban_final
            ;;
        nftables-bootstrap)
            verify_nftables_bootstrap
            ;;
        fail2ban-bootstrap)
            verify_fail2ban_bootstrap
            ;;
        all)
            verify_all_final
            ;;
        *)
            usage
            exit 2
            ;;
    esac
}

main "$@"
