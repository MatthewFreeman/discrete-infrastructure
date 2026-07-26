#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

readonly MODE="${1:-}"
readonly CONFIG="${2:-/etc/nftables.conf}"
readonly TABLE="discrete_filter"

# Supported during migration and rollback:
#   current: table ip discrete_filter
#   previous managed state: table inet discrete_filter
#   oldest state: flush ruleset + table inet filter

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

case "${MODE}" in
    --check|--apply)
        ;;
    *)
        die "Usage: $0 --check|--apply [config-file]"
        ;;
esac

[[ ${EUID} -eq 0 ]] || die "Run as root."
[[ -r "${CONFIG}" ]] || die "Cannot read configuration: ${CONFIG}"

new_ipv4_config=0
previous_inet_config=0
legacy_flush_config=0

if grep -Eq \
    '^[[:space:]]*table[[:space:]]+ip[[:space:]]+discrete_filter[[:space:]]*\{' \
    "${CONFIG}"; then
    new_ipv4_config=1
fi

if grep -Eq \
    '^[[:space:]]*table[[:space:]]+inet[[:space:]]+discrete_filter[[:space:]]*\{' \
    "${CONFIG}"; then
    previous_inet_config=1
fi

if grep -Eq '^[[:space:]]*flush[[:space:]]+ruleset' "${CONFIG}" \
   && grep -Eq \
      '^[[:space:]]*table[[:space:]]+inet[[:space:]]+filter[[:space:]]*\{' \
      "${CONFIG}"; then
    legacy_flush_config=1
fi

if [[ $((new_ipv4_config + previous_inet_config + legacy_flush_config)) -ne 1 ]]; then
    die "Configuration does not define exactly one recognized Discrete firewall format."
fi

temporary_batch="$(mktemp)"
trap 'rm -f "${temporary_batch}"' EXIT

# Remove only Discrete-owned tables before loading the selected configuration.
# Both families are checked so a one-time IPv4 migration and an automatic rollback
# can use the same transaction helper.
for family in ip inet ip6; do
    if nft list table "${family}" "${TABLE}" >/dev/null 2>&1; then
        printf 'delete table %s %s\n' "${family}" "${TABLE}" \
            >> "${temporary_batch}"
    fi
done

# Remove the oldest repository-managed table when it is recognizable. Do not
# delete an unrelated table merely because it is named filter.
legacy_rules="$(nft list table inet filter 2>/dev/null || true)"
if grep -Fq 'comment "Discrete P2P"' <<<"${legacy_rules}" \
   && grep -Eq 'tcp dport 22822' <<<"${legacy_rules}"; then
    printf 'delete table inet filter\n' >> "${temporary_batch}"
fi

cat "${CONFIG}" >> "${temporary_batch}"

case "${MODE}" in
    --check)
        printf 'Checking nftables transaction...\n'
        nft --check --file "${temporary_batch}"
        printf 'nftables transaction is valid.\n'
        ;;
    --apply)
        printf 'Applying nftables transaction...\n'
        nft --file "${temporary_batch}"

        if [[ ${legacy_flush_config} -eq 1 ]] \
           && systemctl is-active --quiet fail2ban; then
            printf 'Legacy ruleset flushed Fail2Ban rules; restoring them.\n'
            bash scripts/restart-fail2ban.sh
        fi

        printf 'nftables transaction applied.\n'
        ;;
esac
