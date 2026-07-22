#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

readonly MODE="${1:-}"
readonly CONFIG="${2:-/etc/nftables.conf}"
readonly FAMILY="inet"
readonly TABLE="discrete_filter"
readonly LEGACY_TABLE="filter"

die() {
    echo "ERROR: $*" >&2
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

temporary_batch="$(mktemp)"

cleanup() {
    rm -f "${temporary_batch}"
}

trap cleanup EXIT

new_config=0
legacy_config=0

if grep -Eq \
    '^[[:space:]]*table[[:space:]]+inet[[:space:]]+discrete_filter[[:space:]]*\{' \
    "${CONFIG}"; then
    new_config=1
fi

if grep -Eq '^[[:space:]]*flush[[:space:]]+ruleset' "${CONFIG}" \
   && grep -Eq \
      '^[[:space:]]*table[[:space:]]+inet[[:space:]]+filter[[:space:]]*\{' \
      "${CONFIG}"; then
    legacy_config=1
fi

if [[ ${new_config} -eq 0 && ${legacy_config} -eq 0 ]]; then
    die "Configuration does not define a recognized Discrete firewall table."
fi

if [[ ${new_config} -eq 1 ]]; then
    if nft list table "${FAMILY}" "${TABLE}" >/dev/null 2>&1; then
        printf 'delete table %s %s\n' \
            "${FAMILY}" "${TABLE}" >> "${temporary_batch}"
    fi

    legacy_rules="$(
        nft list table "${FAMILY}" "${LEGACY_TABLE}" 2>/dev/null || true
    )"

    if grep -Fq 'comment "Discrete P2P"' <<<"${legacy_rules}" \
       && grep -Eq 'tcp dport 22822' <<<"${legacy_rules}"; then

        echo "Migrating legacy Discrete firewall table."

        printf 'delete table %s %s\n' \
            "${FAMILY}" "${LEGACY_TABLE}" >> "${temporary_batch}"
    fi
fi

cat "${CONFIG}" >> "${temporary_batch}"

case "${MODE}" in
    --check)
        echo "Checking nftables transaction..."
        nft --check --file "${temporary_batch}"
        echo "nftables transaction is valid."
        ;;

    --apply)
        echo "Applying nftables transaction..."
        nft --file "${temporary_batch}"

        # Compatibility path if apply-config rolls back to the old
        # flush-ruleset configuration.
        if [[ ${legacy_config} -eq 1 ]] \
           && systemctl is-active --quiet fail2ban; then
            echo "Legacy ruleset flushed Fail2Ban rules; restoring them."
            bash scripts/restart-fail2ban.sh
        fi

        echo "nftables transaction applied."
        ;;
esac
