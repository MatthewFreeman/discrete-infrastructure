#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

print_or_none() {
    local value="$1"

    if [[ -n "${value}" ]]; then
        printf '%s\n' "${value}"
    else
        printf '(none)\n'
    fi
}

[[ ${EUID} -eq 0 ]] || fail "Run the port audit as root."

for command in ss ip nft; do
    command -v "${command}" >/dev/null 2>&1 \
        || fail "The ${command} command is unavailable."
done

ipv4_tcp="$(ss -4 -H -lntp 2>/dev/null | LC_ALL=C sort -k4,4 || true)"
ipv4_udp="$(ss -4 -H -lnup 2>/dev/null | LC_ALL=C sort -k4,4 || true)"
ipv6_addresses="$(ip -6 -o address show 2>/dev/null || true)"
ipv6_routes="$(ip -6 route show table all 2>/dev/null || true)"
ipv6_listeners="$(ss -6 -H -lntup 2>/dev/null | LC_ALL=C sort -k4,4 || true)"

printf 'IPv4 TCP listening sockets:\n'
printf '%s\n' '---------------------------'
print_or_none "${ipv4_tcp}"

printf '\nIPv4 UDP listening sockets:\n'
printf '%s\n' '---------------------------'
print_or_none "${ipv4_udp}"

printf '\nIPv6 interface flags:\n'
printf '%s\n' '---------------------'
shopt -s nullglob
flags=(/proc/sys/net/ipv6/conf/*/disable_ipv6)
shopt -u nullglob
[[ ${#flags[@]} -gt 0 ]] || fail "IPv6 interface sysctl flags are unavailable."

for flag in "${flags[@]}"; do
    value="$(cat "${flag}")"
    printf '%-18s %s\n' "$(basename "$(dirname "${flag}")")" "${value}"
    [[ "${value}" == "1" ]] \
        || fail "IPv6 is enabled by ${flag}: ${value}"
done

printf '\nIPv6 addresses:\n'
printf '%s\n' '---------------'
print_or_none "${ipv6_addresses}"

printf '\nIPv6 routes:\n'
printf '%s\n' '------------'
print_or_none "${ipv6_routes}"

printf '\nIPv6 listening sockets:\n'
printf '%s\n' '-----------------------'
print_or_none "${ipv6_listeners}"

[[ -z "${ipv6_addresses}" ]] || fail "IPv6 addresses remain."
[[ -z "${ipv6_routes}" ]] || fail "IPv6 routes remain."
[[ -z "${ipv6_listeners}" ]] || fail "IPv6 listening sockets remain."

if awk '$4 ~ /:123$/ { found = 1 } END { exit !found }' <<<"${ipv4_udp}"; then
    printf '\nUnexpected IPv4 UDP 123 listeners:\n' >&2
    awk '$4 ~ /:123$/' <<<"${ipv4_udp}" >&2
    fail "The client-only baseline must not listen on UDP 123."
fi

printf '\nActive nftables tables:\n'
printf '%s\n' '-----------------------'
nft list tables

printf '\nHost firewall input chain:\n'
printf '%s\n' '--------------------------'
nft -a list chain ip discrete_filter input

if nft list table inet discrete_filter >/dev/null 2>&1; then
    fail "Legacy inet discrete_filter table remains."
fi

if nft list table ip6 discrete_filter >/dev/null 2>&1; then
    fail "IPv6 discrete_filter table remains."
fi

if nft list table inet f2b-table >/dev/null 2>&1; then
    fail "Legacy inet Fail2Ban table remains."
fi

if nft list table ip6 f2b-table >/dev/null 2>&1; then
    fail "IPv6 Fail2Ban table remains."
fi

printf '\nIPv4-only verification passed.\n'
printf 'Port audit result: PASS\n'
printf '%s\n' \
    'A provider DHCP client may legitimately listen on IPv4 UDP 68.'
printf '%s\n' \
    'This local audit does not prove provider-firewall or Internet reachability.'
