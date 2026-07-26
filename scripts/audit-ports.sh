#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ ${EUID} -eq 0 ]] \
    || fail "Run the port audit as root."

command -v ss >/dev/null 2>&1 \
    || fail "The ss command is unavailable."
command -v nft >/dev/null 2>&1 \
    || fail "The nft command is unavailable."

printf 'TCP listening sockets:\n'
printf '%s\n' '----------------------'
if ! ss -H -lntp | LC_ALL=C sort -k4,4; then
    fail "Could not read TCP listening sockets."
fi

udp_sockets="$(ss -H -lnup 2>/dev/null || true)"

printf '\nUDP listening sockets:\n'
printf '%s\n' '----------------------'
printf '%s\n' "${udp_sockets}" | LC_ALL=C sort -k4,4

if awk '$4 ~ /:123$/ { found = 1 } END { exit !found }' <<<"${udp_sockets}"; then
    printf '\nUnexpected UDP 123 listeners:\n' >&2
    awk '$4 ~ /:123$/' <<<"${udp_sockets}" >&2
    fail "The client-only baseline must not listen on UDP 123."
fi

printf '\nActive nftables tables:\n'
printf '%s\n' '-----------------------'
nft list tables

printf '\nHost firewall input chain:\n'
printf '%s\n' '--------------------------'
nft -a list chain inet discrete_filter input

printf '\nPort audit complete.\n'
printf '%s\n' \
    'Review every wildcard, public-address, and VPS-interface listener.'
printf '%s\n' \
    'A provider DHCP client may legitimately listen on UDP 68.'
printf '%s\n' \
    'This local audit does not prove provider-firewall or Internet reachability.'
