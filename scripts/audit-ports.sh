#!/usr/bin/env bash
set -Eeuo pipefail

fatal() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'USAGE'
Usage: ./scripts/audit-ports.sh [--verbose]

Print a concise PASS/FAIL audit by default. Use --verbose to append the raw
socket, nftables table, and firewall-chain diagnostics.
USAGE
}

verbose=false
[[ $# -le 1 ]] || fatal "Expected no arguments or --verbose."

case "${1:-}" in
    "") ;;
    -v|--verbose) verbose=true ;;
    -h|--help)
        usage
        exit 0
        ;;
    *) fatal "Unknown argument: ${1}" ;;
esac

checks=0
failures=0

pass() {
    checks=$((checks + 1))
    printf '[PASS] %-27s %s\n' "$1" "$2"
}

fail_check() {
    checks=$((checks + 1))
    failures=$((failures + 1))
    printf '[FAIL] %-27s %s\n' "$1" "$2" >&2

    if [[ -n "${3:-}" ]]; then
        while IFS= read -r line; do
            if [[ -n "${line}" ]]; then
                printf '       %s\n' "${line}" >&2
            fi
        done <<<"$3"
    fi
}

info() {
    printf '[INFO] %-27s %s\n' "$1" "$2"
}

print_or_none() {
    local value="$1"

    if [[ -n "${value}" ]]; then
        printf '%s\n' "${value}"
    else
        printf '(none)\n'
    fi
}

print_verbose_section() {
    local title="$1"
    local value="$2"

    printf '\n%s:\n' "${title}"
    printf '%s\n' '---------------------------'
    print_or_none "${value}"
}

[[ ${EUID} -eq 0 ]] || fatal "Run the port audit as root."

for command in ss ip nft awk grep sort; do
    command -v "${command}" >/dev/null 2>&1 \
        || fatal "The ${command} command is unavailable."
done

ipv4_tcp="$(ss -4 -H -lntp 2>/dev/null | LC_ALL=C sort -k4,4 || true)"
ipv4_udp="$(ss -4 -H -lnup 2>/dev/null | LC_ALL=C sort -k4,4 || true)"
ipv6_addresses="$(ip -6 -o address show 2>/dev/null || true)"
ipv6_routes="$(ip -6 route show table all 2>/dev/null || true)"
ipv6_listeners="$(ss -6 -H -lntup 2>/dev/null | LC_ALL=C sort -k4,4 || true)"

if ! nft_tables="$(nft list tables 2>&1)"; then
    fatal "Could not list nftables tables: ${nft_tables}"
fi

if ! input_chain="$(nft -a list chain ip discrete_filter input 2>&1)"; then
    fatal "Could not read table ip discrete_filter input: ${input_chain}"
fi

printf 'Port and firewall audit\n'
printf '%s\n' '======================='

ssh_22822_count="$(
    awk '$4 ~ /:22822$/ && $0 ~ /"sshd"/ { count++ } END { print count + 0 }' \
        <<<"${ipv4_tcp}"
)"
unexpected_public_tcp="$(
    awk '$4 !~ /^127\./ && !($4 ~ /:22822$/ && $0 ~ /"sshd"/) { print }' \
        <<<"${ipv4_tcp}"
)"

if [[ "${ssh_22822_count}" == "1" && -z "${unexpected_public_tcp}" ]]; then
    pass "Public TCP listeners" "sshd on IPv4 TCP 22822 only"
else
    fail_check \
        "Public TCP listeners" \
        "expected exactly one public sshd listener on TCP 22822" \
        "${ipv4_tcp:-"(none)"}"
fi

tcp_22_listeners="$(awk '$4 ~ /:22$/ { print }' <<<"${ipv4_tcp}")"
if [[ -z "${tcp_22_listeners}" ]]; then
    pass "Temporary SSH port" "no TCP 22 listener"
else
    fail_check "Temporary SSH port" "TCP 22 is still listening" "${tcp_22_listeners}"
fi

udp_123_listeners="$(awk '$4 ~ /:123$/ { print }' <<<"${ipv4_udp}")"
if [[ -z "${udp_123_listeners}" ]]; then
    pass "NTP server port" "no IPv4 UDP 123 listener"
else
    fail_check "NTP server port" "IPv4 UDP 123 must not listen" "${udp_123_listeners}"
fi

unexpected_public_udp="$(
    awk '$4 !~ /^127\./ && $4 !~ /:68$/ { print }' <<<"${ipv4_udp}"
)"
dhcp_68_count="$(awk '$4 ~ /:68$/ { count++ } END { print count + 0 }' <<<"${ipv4_udp}")"

if [[ -z "${unexpected_public_udp}" ]]; then
    if [[ "${dhcp_68_count}" == "0" ]]; then
        pass "Public UDP listeners" "none"
    else
        pass "Public UDP listeners" "UDP 68 DHCP exception only"
        info "UDP 68" "expected on providers that use DHCP"
    fi
else
    fail_check \
        "Public UDP listeners" \
        "only the provider DHCP exception on UDP 68 is permitted" \
        "${unexpected_public_udp}"
fi

shopt -s nullglob
flags=(/proc/sys/net/ipv6/conf/*/disable_ipv6)
shopt -u nullglob
[[ ${#flags[@]} -gt 0 ]] || fatal "IPv6 interface sysctl flags are unavailable."

enabled_ipv6_interfaces=()
for flag in "${flags[@]}"; do
    value="$(cat "${flag}")"
    interface="$(basename "$(dirname "${flag}")")"
    if [[ "${value}" != "1" ]]; then
        enabled_ipv6_interfaces+=("${interface}: ${flag}=${value}")
    fi
done

if [[ ${#enabled_ipv6_interfaces[@]} -eq 0 ]]; then
    pass "IPv6 interface policy" "disabled on all ${#flags[@]} interface scopes"
else
    fail_check \
        "IPv6 interface policy" \
        "IPv6 remains enabled on ${#enabled_ipv6_interfaces[@]} interface scopes" \
        "$(printf '%s\n' "${enabled_ipv6_interfaces[@]}")"
fi

if [[ -z "${ipv6_addresses}" ]]; then
    pass "IPv6 addresses" "none"
else
    fail_check "IPv6 addresses" "addresses remain" "${ipv6_addresses}"
fi

if [[ -z "${ipv6_routes}" ]]; then
    pass "IPv6 routes" "none"
else
    fail_check "IPv6 routes" "routes remain" "${ipv6_routes}"
fi

if [[ -z "${ipv6_listeners}" ]]; then
    pass "IPv6 listeners" "none"
else
    fail_check "IPv6 listeners" "listening sockets remain" "${ipv6_listeners}"
fi

required_tables=(
    "table ip discrete_filter"
    "table ip f2b-table"
)
missing_tables=()
for table in "${required_tables[@]}"; do
    if ! grep -Fxq "${table}" <<<"${nft_tables}"; then
        missing_tables+=("${table}")
    fi
done

unexpected_tables="$(
    grep -Fvx \
        -e "${required_tables[0]}" \
        -e "${required_tables[1]}" \
        <<<"${nft_tables}" || true
)"

if [[ ${#missing_tables[@]} -eq 0 && -z "${unexpected_tables}" ]]; then
    pass "nftables tables" "discrete_filter and f2b-table, IPv4 only"
else
    table_diagnostic="${nft_tables:-"(none)"}"
    if [[ ${#missing_tables[@]} -gt 0 ]]; then
        table_diagnostic+=$'\nMissing: '
        table_diagnostic+="${missing_tables[*]}"
    fi
    fail_check "nftables tables" "required or unexpected tables found" "${table_diagnostic}"
fi

if grep -Eq 'policy drop;' <<<"${input_chain}"; then
    pass "Firewall default policy" "drop"
else
    fail_check "Firewall default policy" "input chain must use policy drop" "${input_chain}"
fi

required_tcp_ports=(22822 9330 9331 9332)
missing_tcp_ports=()
for port in "${required_tcp_ports[@]}"; do
    if ! grep -Eq "tcp dport ${port}([^0-9]|$).*accept" <<<"${input_chain}"; then
        missing_tcp_ports+=("${port}")
    fi
done

accepted_tcp_ports="$(
    sed -nE 's/.*tcp dport ([0-9]+).*accept.*/\1/p' <<<"${input_chain}" \
        | LC_ALL=C sort -n -u || true
)"
unexpected_tcp_ports="$(
    grep -Ev '^(22822|9330|9331|9332)$' <<<"${accepted_tcp_ports}" || true
)"

if [[ ${#missing_tcp_ports[@]} -eq 0 && -z "${unexpected_tcp_ports}" ]]; then
    pass "Firewall TCP allowlist" "22822, 9330, 9331, and 9332 only"
else
    firewall_diagnostic="Accepted TCP ports: ${accepted_tcp_ports:-"(none)"}"
    if [[ ${#missing_tcp_ports[@]} -gt 0 ]]; then
        firewall_diagnostic+=$'\nMissing: '
        firewall_diagnostic+="${missing_tcp_ports[*]}"
    fi
    fail_check \
        "Firewall TCP allowlist" \
        "does not match the required baseline" \
        "${firewall_diagnostic}"
fi

if ${verbose}; then
    printf '\nRaw diagnostics (--verbose)\n'
    printf '%s\n' '==========================='
    print_verbose_section "IPv4 TCP listening sockets" "${ipv4_tcp}"
    print_verbose_section "IPv4 UDP listening sockets" "${ipv4_udp}"
    print_verbose_section "IPv6 addresses" "${ipv6_addresses}"
    print_verbose_section "IPv6 routes" "${ipv6_routes}"
    print_verbose_section "IPv6 listening sockets" "${ipv6_listeners}"
    print_verbose_section "Active nftables tables" "${nft_tables}"
    print_verbose_section "Host firewall input chain" "${input_chain}"
fi

passed=$((checks - failures))
printf '\nSummary\n'
printf '%s\n' '-------'
printf 'Checks passed: %d/%d\n' "${passed}" "${checks}"

if [[ ${failures} -gt 0 ]]; then
    printf 'Port audit result: FAIL (%d checks failed)\n' "${failures}" >&2
    exit 1
fi

printf 'IPv4-only verification passed.\n'
printf 'Port audit result: PASS\n'
printf '%s\n' \
    'Scope note: this local audit does not prove provider-firewall or Internet reachability.'
