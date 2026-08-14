#!/usr/bin/env bash
set -Eeuo pipefail

mode="${1:-strict}"

case "${mode}" in
    prepare|strict) ;;
    *)
        printf 'Usage: %s prepare|strict\n' "$0" >&2
        exit 2
        ;;
esac

if [[ -n "${DISCRETE_IPV6_LISTENERS_FILE:-}" ]]; then
    [[ -r "${DISCRETE_IPV6_LISTENERS_FILE}" ]] || {
        printf 'ERROR: Cannot read IPv6 listener fixture: %s\n' \
            "${DISCRETE_IPV6_LISTENERS_FILE}" >&2
        exit 2
    }
    listeners="$(<"${DISCRETE_IPV6_LISTENERS_FILE}")"
else
    listeners="$(ss -6 -H -lntup 2>/dev/null || true)"
fi

if [[ -z "${listeners}" ]]; then
    printf 'none\n'
    exit 0
fi

if [[ "${mode}" == "strict" ]]; then
    printf 'Unexpected IPv6 listeners:\n%s\n' "${listeners}" >&2
    exit 1
fi

unexpected="$(
    awk '
        function loopback_port(    i, value) {
            for (i = 1; i <= NF; i++) {
                if ($i ~ /^\[::1\]:[0-9]+$/) {
                    value = $i
                    sub(/^.*:/, "", value)
                    return value + 0
                }
            }
            return -1
        }

        {
            port = loopback_port()
            if ($1 == "tcp" \
                && $2 == "LISTEN" \
                && port >= 6000 \
                && port <= 6063 \
                && /users:\(\("sshd"/) {
                next
            }
            print
        }
    ' <<<"${listeners}"
)"

if [[ -n "${unexpected}" ]]; then
    printf 'Unexpected IPv6 listeners:\n%s\n' "${unexpected}" >&2
    exit 1
fi

printf 'Transient loopback SSH X11 listener detected:\n%s\n' "${listeners}" >&2
printf 'Fresh SSH sessions have X11 forwarding disabled. Keep this session until fresh IPv4 access works, then close it before finalize.\n' >&2
printf 'transient-x11\n'
