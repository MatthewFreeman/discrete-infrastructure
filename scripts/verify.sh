#!/usr/bin/env bash
set -Eeuo pipefail

readonly BOOTSTRAP_SSH_PORT="22"
readonly FINAL_SSH_PORT="22822"
readonly HOST_FIREWALL_FAMILY="ip"
readonly HOST_FIREWALL_TABLE="discrete_filter"
readonly FAIL2BAN_FAMILY="ip"
readonly FAIL2BAN_TABLE="f2b-table"
readonly TIME_SYNC_SERVICE="systemd-timesyncd.service"
readonly CONFLICTING_TIME_PACKAGES=(ntp ntpsec chrony openntpd)

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_root() {
    [[ ${EUID} -eq 0 ]] || fail "Run verification as root."
}

package_is_installed() {
    local package="$1"

    dpkg-query -W -f='${Status}\n' "${package}" 2>/dev/null \
        | grep -x 'install ok installed' >/dev/null
}

ipv4_sshd_listener_exists() {
    local port="$1"
    local listeners

    listeners="$(ss -4 -H -lntp 2>/dev/null || true)"

    awk -v expected_port=":${port}" '
        $4 ~ expected_port "$" && /users:\(\("sshd"/ {
            found = 1
        }
        END { exit !found }
    ' <<<"${listeners}"
}

ipv4_tcp_listener_exists() {
    local port="$1"
    local listeners

    listeners="$(ss -4 -H -lntp 2>/dev/null || true)"

    awk -v expected_port=":${port}" '
        $4 ~ expected_port "$" { found = 1 }
        END { exit !found }
    ' <<<"${listeners}"
}

udp_listener_exists() {
    local port="$1"
    local sockets

    sockets="$(ss -H -lnup 2>/dev/null || true)"

    awk -v expected_port=":${port}" '
        $4 ~ expected_port "$" { found = 1 }
        END { exit !found }
    ' <<<"${sockets}"
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
                if (fields[i] == expected_port) { found = 1 }
            }
        }
        END { exit !found }
    ' <<<"${rules}"
}

nft_chain_has_udp_accept() {
    local family="$1"
    local table="$2"
    local chain="$3"
    local rules

    rules="$(nft list chain "${family}" "${table}" "${chain}" 2>/dev/null)" \
        || return 1

    awk '
        /udp dport/ && /accept/ { found = 1 }
        END { exit !found }
    ' <<<"${rules}"
}

wait_for_fail2ban_table() {
    local attempt

    for attempt in {1..40}; do
        if nft list table "${FAIL2BAN_FAMILY}" "${FAIL2BAN_TABLE}" \
            >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.25
    done

    return 1
}

fail2ban_rule_has_tcp_port() {
    local port="$1"
    local rules

    rules="$(nft list table "${FAIL2BAN_FAMILY}" "${FAIL2BAN_TABLE}" 2>/dev/null)" \
        || return 1

    awk -v expected_port="${port}" '
        /tcp dport/ && /@addr-set-sshd/ {
            line = $0
            gsub(/[{},]/, " ", line)
            count = split(line, fields, /[[:space:]]+/)
            for (i = 1; i <= count; i++) {
                if (fields[i] == expected_port) { found = 1 }
            }
        }
        END { exit !found }
    ' <<<"${rules}"
}

verify_ipv4_only() {
    local flag
    local value
    local addresses
    local routes
    local listeners

    [[ -r /etc/sysctl.d/99-discrete-ipv4-only.conf ]] \
        || fail "Managed IPv4-only sysctl policy is missing."

    shopt -s nullglob
    local flags=(/proc/sys/net/ipv6/conf/*/disable_ipv6)
    shopt -u nullglob

    [[ ${#flags[@]} -gt 0 ]] \
        || fail "IPv6 interface sysctl flags are unavailable."

    for flag in "${flags[@]}"; do
        value="$(cat "${flag}")"
        [[ "${value}" == "1" ]] \
            || fail "IPv6 is enabled by ${flag}: ${value}"
    done

    addresses="$(ip -6 -o address show 2>/dev/null || true)"
    routes="$(ip -6 route show table all 2>/dev/null || true)"
    listeners="$(ss -6 -H -lntup 2>/dev/null || true)"

    if [[ -n "${addresses}" ]]; then
        printf 'Unexpected IPv6 addresses:\n%s\n' "${addresses}" >&2
        fail "IPv6 addresses remain."
    fi

    if [[ -n "${routes}" ]]; then
        printf 'Unexpected IPv6 routes:\n%s\n' "${routes}" >&2
        fail "IPv6 routes remain."
    fi

    if [[ -n "${listeners}" ]]; then
        printf 'Unexpected IPv6 listeners:\n%s\n' "${listeners}" >&2
        fail "IPv6 listening sockets remain."
    fi

    printf 'IPv4-only final-state verification passed.\n'
}

verify_no_ufw() {
    if package_is_installed ufw; then
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
    systemctl is-enabled --quiet ssh || fail "SSH service is not enabled."
    systemctl is-active --quiet ssh || fail "SSH service is not active."

    effective="$(sshd -T)"

    grep -x 'addressfamily inet' <<<"${effective}" >/dev/null \
        || fail "OpenSSH is not restricted to AddressFamily inet."

    mapfile -t ports < <(awk '$1 == "port" { print $2 }' <<<"${effective}")
    [[ ${#ports[@]} -eq 1 && "${ports[0]}" == "${FINAL_SSH_PORT}" ]] \
        || fail "Effective SSH ports are not exactly: ${FINAL_SSH_PORT}."

    grep -x 'permitrootlogin no' <<<"${effective}" >/dev/null \
        || fail "Direct root SSH login is not disabled."
    grep -x 'passwordauthentication yes' <<<"${effective}" >/dev/null \
        || fail "SSH password authentication is not enabled."
    grep -x 'pubkeyauthentication yes' <<<"${effective}" >/dev/null \
        || fail "SSH public-key authentication is not enabled."

    ipv4_sshd_listener_exists "${FINAL_SSH_PORT}" \
        || fail "sshd is not listening on IPv4 TCP ${FINAL_SSH_PORT}."

    if ipv4_tcp_listener_exists "${BOOTSTRAP_SSH_PORT}"; then
        fail "A process still listens on temporary IPv4 TCP ${BOOTSTRAP_SSH_PORT}."
    fi

    printf 'SSH final-state verification passed.\n'
}

verify_nftables_common() {
    local chain

    systemctl is-enabled --quiet nftables \
        || fail "nftables service is not enabled."
    systemctl is-active --quiet nftables \
        || fail "nftables service is not active."

    nft list table "${HOST_FIREWALL_FAMILY}" "${HOST_FIREWALL_TABLE}" \
        >/dev/null || fail "IPv4 host firewall table is missing."

    if nft list table inet "${HOST_FIREWALL_TABLE}" >/dev/null 2>&1; then
        fail "Legacy inet discrete_filter table remains."
    fi

    if nft list table ip6 "${HOST_FIREWALL_TABLE}" >/dev/null 2>&1; then
        fail "IPv6 discrete_filter table remains."
    fi

    chain="$(nft list chain "${HOST_FIREWALL_FAMILY}" "${HOST_FIREWALL_TABLE}" input)"
    grep -E 'policy drop' <<<"${chain}" >/dev/null \
        || fail "Host firewall input policy is not drop."

    nft_chain_has_tcp_port ip discrete_filter input "${FINAL_SSH_PORT}" \
        || fail "Firewall does not allow IPv4 SSH TCP ${FINAL_SSH_PORT}."
    nft_chain_has_tcp_port ip discrete_filter input 9330 \
        || fail "Firewall does not allow Discrete P2P TCP 9330."
    nft_chain_has_tcp_port ip discrete_filter input 9331 \
        || fail "Firewall does not allow Discrete RPC HTTP TCP 9331."
    nft_chain_has_tcp_port ip discrete_filter input 9332 \
        || fail "Firewall does not allow Discrete RPC HTTPS TCP 9332."

    if nft_chain_has_udp_accept ip discrete_filter input; then
        fail "Host firewall contains an inbound UDP accept rule."
    fi

    verify_no_ufw
}

verify_nftables_bootstrap() {
    verify_nftables_common

    nft_chain_has_tcp_port ip discrete_filter input "${BOOTSTRAP_SSH_PORT}" \
        || fail "Bootstrap firewall does not allow IPv4 SSH TCP ${BOOTSTRAP_SSH_PORT}."

    printf 'nftables bootstrap-state verification passed.\n'
}

verify_nftables_final() {
    verify_nftables_common

    if nft_chain_has_tcp_port ip discrete_filter input "${BOOTSTRAP_SSH_PORT}"; then
        fail "Final firewall still allows temporary SSH TCP ${BOOTSTRAP_SSH_PORT}."
    fi

    printf 'nftables final-state verification passed.\n'
}

verify_fail2ban_common() {
    systemctl is-enabled --quiet fail2ban \
        || fail "Fail2Ban service is not enabled."
    systemctl is-active --quiet fail2ban \
        || fail "Fail2Ban service is not active."

    grep -Eq '^[[:space:]]*allowipv6[[:space:]]*=[[:space:]]*no[[:space:]]*$' \
        /etc/fail2ban/fail2ban.local \
        || fail "Fail2Ban allowipv6 is not disabled."

    grep -F 'table_family=ip' /etc/fail2ban/jail.local >/dev/null \
        || fail "Fail2Ban nftables action is not restricted to table_family=ip."

    fail2ban-client ping | grep -x 'Server replied: pong' >/dev/null \
        || fail "Fail2Ban control socket did not reply."
    fail2ban-client status sshd >/dev/null \
        || fail "Fail2Ban sshd jail is not active."

    wait_for_fail2ban_table \
        || fail "IPv4 Fail2Ban nftables table was not initialized."

    if nft list table inet "${FAIL2BAN_TABLE}" >/dev/null 2>&1; then
        fail "Legacy inet Fail2Ban table remains."
    fi

    if nft list table ip6 "${FAIL2BAN_TABLE}" >/dev/null 2>&1; then
        fail "IPv6 Fail2Ban table remains."
    fi

    fail2ban_rule_has_tcp_port "${FINAL_SSH_PORT}" \
        || fail "Fail2Ban does not protect IPv4 SSH TCP ${FINAL_SSH_PORT}."
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

verify_time_sync() {
    local package
    local attempt
    local synchronized="no"

    package_is_installed systemd-timesyncd \
        || fail "systemd-timesyncd is not installed."

    for package in "${CONFLICTING_TIME_PACKAGES[@]}"; do
        if package_is_installed "${package}"; then
            fail "Conflicting NTP server package is installed: ${package}."
        fi
    done

    systemctl is-enabled --quiet "${TIME_SYNC_SERVICE}" \
        || fail "systemd-timesyncd is not enabled."
    systemctl is-active --quiet "${TIME_SYNC_SERVICE}" \
        || fail "systemd-timesyncd is not active."

    for attempt in {1..10}; do
        synchronized="$(timedatectl show -p NTPSynchronized --value 2>/dev/null || true)"
        [[ "${synchronized}" == "yes" ]] && break
        sleep 1
    done

    [[ "${synchronized}" == "yes" ]] \
        || fail "Clock does not report NTPSynchronized=yes."

    if udp_listener_exists 123; then
        printf 'Unexpected UDP 123 listeners:\n' >&2
        ss -H -lnup | awk '$4 ~ /:123$/' >&2 || true
        fail "A process still listens on UDP 123."
    fi

    printf 'Time synchronization final-state verification passed.\n'
}

verify_all_final() {
    verify_ipv4_only
    verify_ssh_final
    verify_nftables_final
    verify_fail2ban_final
    verify_time_sync
    printf 'Complete final-state verification passed.\n'
}

usage() {
    cat <<EOF
Usage:
  $0 ipv4
  $0 ssh
  $0 nftables
  $0 fail2ban
  $0 timesync
  $0 nftables-bootstrap
  $0 fail2ban-bootstrap
  $0 all

Final-state checks:
  ipv4, ssh, nftables, fail2ban, timesync, all

Temporary prepare-phase checks:
  nftables-bootstrap, fail2ban-bootstrap
EOF
}

main() {
    require_root

    case "${1:-}" in
        ipv4)
            verify_ipv4_only
            ;;
        ssh)
            verify_ssh_final
            ;;
        nftables)
            verify_nftables_final
            ;;
        fail2ban)
            verify_fail2ban_final
            ;;
        timesync)
            verify_time_sync
            ;;
        nftables-bootstrap)
            verify_ipv4_only
            verify_nftables_bootstrap
            ;;
        fail2ban-bootstrap)
            verify_ipv4_only
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
