#!/usr/bin/env bash
set -Eeuo pipefail

umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_DIR
readonly STATE_DIR="/var/lib/discrete-infrastructure"
readonly FINALIZED_MARKER="${STATE_DIR}/bootstrap-finalized"
readonly TEMP_SSH_CONFIG="/etc/ssh/sshd_config.d/00-discrete-bootstrap.conf"
readonly BOOTSTRAP_SSH_PORT="22"
readonly FINAL_SSH_PORT="22822"
readonly FIREWALL_FAMILY="ip"
readonly FIREWALL_TABLE="discrete_filter"
readonly FAIL2BAN_FAMILY="ip"
readonly FAIL2BAN_TABLE="f2b-table"

ADMIN_USER="${ADMIN_USER:-serveradmin}"
PREPARE_IPV6_LISTENER_STATE="none"

log() {
    printf '\n==> %s\n' "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_root() {
    [[ ${EUID} -eq 0 ]] || die "Run this script as root or through sudo -i."
}

validate_admin_user() {
    [[ "${ADMIN_USER}" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] \
        || die "Invalid ADMIN_USER: ${ADMIN_USER}"
    [[ "${ADMIN_USER}" != "root" ]] \
        || die "ADMIN_USER cannot be root."
}

check_platform() {
    [[ -r /etc/os-release ]] || die "Cannot identify the operating system."

    # shellcheck disable=SC1091
    source /etc/os-release

    [[ "${ID:-}" == "debian" ]] \
        || die "This bootstrap supports Debian only."
    [[ "${VERSION_ID:-}" == "12" ]] \
        || die "This bootstrap is validated for Debian 12, found ${VERSION_ID:-unknown}."
}

install_base_packages() {
    log "Installing base packages"

    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        ca-certificates \
        curl \
        fail2ban \
        git \
        iproute2 \
        nftables \
        openssh-server \
        procps \
        python3-systemd \
        sudo

    systemctl enable --now ssh
    systemctl enable fail2ban >/dev/null
}

configure_host_baseline() {
    log "Applying IPv4-only host policy"
    bash "${REPO_DIR}/scripts/configure-ipv4-only.sh"

    log "Configuring client-only time synchronization"
    bash "${REPO_DIR}/scripts/configure-time-sync.sh"
}

ipv4_listener_exists() {
    local port="$1"
    local require_sshd="${2:-0}"
    local listeners

    listeners="$(ss -4 -H -lntp 2>/dev/null || true)"

    if [[ "${require_sshd}" == "1" ]]; then
        awk -v expected_port=":${port}" '
            $4 ~ expected_port "$" && /users:\(\("sshd"/ { found = 1 }
            END { exit !found }
        ' <<<"${listeners}"
    else
        awk -v expected_port=":${port}" '
            $4 ~ expected_port "$" { found = 1 }
            END { exit !found }
        ' <<<"${listeners}"
    fi
}

wait_for_ipv4_sshd_listener() {
    local port="$1"
    local attempt

    for ((attempt = 1; attempt <= 40; attempt++)); do
        if ipv4_listener_exists "${port}" 1; then
            return 0
        fi
        sleep 0.25
    done

    printf 'ERROR: IPv4 sshd listener on TCP %s did not appear within 10 seconds.\n' \
        "${port}" >&2
    ss -4 -lntp >&2 || true
    journalctl -u ssh -n 40 --no-pager >&2 || true
    return 1
}

wait_for_ipv4_listener_absent() {
    local port="$1"
    local attempt

    for ((attempt = 1; attempt <= 40; attempt++)); do
        if ! ipv4_listener_exists "${port}" 0; then
            return 0
        fi
        sleep 0.25
    done

    return 1
}

verify_no_ipv6_listener() {
    bash "${REPO_DIR}/scripts/check-ipv6-listeners.sh" strict >/dev/null
}

verify_prepare_ipv6_listener_state() {
    PREPARE_IPV6_LISTENER_STATE="$(
        bash "${REPO_DIR}/scripts/check-ipv6-listeners.sh" prepare
    )" || return 1
}

ensure_admin_user() {
    log "Creating or validating administrative user: ${ADMIN_USER}"

    ADMIN_USER="${ADMIN_USER}" \
        bash "${REPO_DIR}/bootstrap/create-admin.sh"

    local admin_home
    local admin_group

    admin_home="$(getent passwd "${ADMIN_USER}" | cut -d: -f6)"
    admin_group="$(id -gn "${ADMIN_USER}")"

    [[ -n "${admin_home}" ]] \
        || die "Cannot determine home directory for ${ADMIN_USER}."

    install -d -m 0700 -o "${ADMIN_USER}" -g "${admin_group}" \
        "${admin_home}/.ssh"

    if [[ -s /root/.ssh/authorized_keys \
       && ! -e "${admin_home}/.ssh/authorized_keys" ]]; then
        log "Copying root authorized_keys to ${ADMIN_USER}"
        install -m 0600 -o "${ADMIN_USER}" -g "${admin_group}" \
            /root/.ssh/authorized_keys \
            "${admin_home}/.ssh/authorized_keys"
    fi
}

server_appears_finalized() {
    local effective

    [[ -f /etc/ssh/sshd_config.d/00-discrete.conf ]] || return 1
    effective="$(sshd -T 2>/dev/null)" || return 1

    grep -x 'addressfamily inet' <<<"${effective}" >/dev/null \
        && grep -x 'port 22822' <<<"${effective}" >/dev/null \
        && grep -x 'permitrootlogin no' <<<"${effective}" >/dev/null
}

write_temporary_ssh_config() {
    if server_appears_finalized \
       && [[ ! -f "${TEMP_SSH_CONFIG}" ]] \
       && [[ "${FORCE_PREPARE:-0}" != "1" ]]; then
        die "This server already appears finalized. Use '$0 status'. Do not run prepare again."
    fi

    log "Installing temporary IPv4 two-port SSH configuration"

    cat > "${TEMP_SSH_CONFIG}" <<EOF
# Temporary IPv4-only bootstrap configuration.
# Removed by: bootstrap/run.sh finalize

AddressFamily inet
Port ${BOOTSTRAP_SSH_PORT}
Port ${FINAL_SSH_PORT}

PermitRootLogin yes
PasswordAuthentication yes
PubkeyAuthentication yes

LoginGraceTime 30
MaxAuthTries 3

X11Forwarding no
AllowAgentForwarding no
EOF

    chmod 0644 "${TEMP_SSH_CONFIG}"
    sshd -t
    systemctl reload ssh

    wait_for_ipv4_sshd_listener "${BOOTSTRAP_SSH_PORT}" \
        || die "sshd is not listening on IPv4 bootstrap port ${BOOTSTRAP_SSH_PORT}."
    wait_for_ipv4_sshd_listener "${FINAL_SSH_PORT}" \
        || die "sshd is not listening on IPv4 final port ${FINAL_SSH_PORT}."
    verify_prepare_ipv6_listener_state \
        || die "OpenSSH exposes an IPv6 listener that is not a transient loopback X11 proxy."
}

build_bootstrap_nftables_config() {
    local source_config="${REPO_DIR}/configs/nftables/nftables.conf"
    local output_config="$1"

    [[ -r "${source_config}" ]] \
        || die "Cannot read nftables source config: ${source_config}"

    awk -v port="${BOOTSTRAP_SSH_PORT}" '
        /^[[:space:]]*tcp dport 22822[[:space:]]/ && !inserted {
            printf "        tcp dport %s counter accept comment \"Temporary bootstrap SSH\"\n", port
            inserted = 1
        }
        { print }
        END { if (!inserted) exit 42 }
    ' "${source_config}" > "${output_config}" \
        || die "Could not create the temporary IPv4 bootstrap firewall."
}

delete_ufw_table_if_present() {
    local family="$1"
    local table="$2"
    local rules

    rules="$(nft list table "${family}" "${table}" 2>/dev/null)" || return 0

    if grep -E '(^|[^[:alnum:]_])ufw6?-' <<<"${rules}" >/dev/null; then
        nft delete table "${family}" "${table}"
    fi
}

remove_ufw() {
    local installed="no"

    if dpkg-query -W -f='${Status}\n' ufw 2>/dev/null \
        | grep -x 'install ok installed' >/dev/null; then
        installed="yes"
    fi

    if command -v ufw >/dev/null 2>&1 || [[ "${installed}" == "yes" ]]; then
        log "Removing UFW so nftables is the only host firewall"
        if command -v ufw >/dev/null 2>&1; then
            ufw --force disable >/dev/null 2>&1 || true
        fi
        systemctl disable --now ufw.service >/dev/null 2>&1 || true

        if [[ "${installed}" == "yes" ]]; then
            DEBIAN_FRONTEND=noninteractive apt-get purge -y ufw
        fi
    fi

    delete_ufw_table_if_present ip filter
    delete_ufw_table_if_present ip6 filter

    assert_nft_table_absent \
        ip \
        filter \
        "Legacy IPv4 filter table remains after UFW cleanup."
    assert_nft_table_absent \
        ip6 \
        filter \
        "Legacy IPv6 filter table remains after UFW cleanup."

    if nft list ruleset | grep -E '(^|[^[:alnum:]_])ufw6?-' >/dev/null; then
        die "Residual UFW rules remain in nftables."
    fi

    return 0
}

install_bootstrap_firewall() (
    local temporary_config

    temporary_config="$(mktemp)"
    trap 'rm -f "${temporary_config}"' EXIT
    build_bootstrap_nftables_config "${temporary_config}"

    log "Validating temporary IPv4 bootstrap firewall"
    bash "${REPO_DIR}/scripts/apply-nftables.sh" --check "${temporary_config}"

    install -m 0644 "${temporary_config}" /etc/nftables.conf
    systemctl enable nftables >/dev/null

    if systemctl is-active --quiet nftables; then
        bash "${REPO_DIR}/scripts/apply-nftables.sh" --apply /etc/nftables.conf
    else
        for family in ip inet ip6; do
            nft list table "${family}" "${FIREWALL_TABLE}" >/dev/null 2>&1 \
                && nft delete table "${family}" "${FIREWALL_TABLE}"
        done
        systemctl reset-failed nftables >/dev/null 2>&1 || true
        systemctl start nftables
    fi

    systemctl is-active --quiet nftables \
        || die "nftables service is not active."

    nft list chain "${FIREWALL_FAMILY}" "${FIREWALL_TABLE}" input \
        | grep -E "tcp dport ${BOOTSTRAP_SSH_PORT}([[:space:]]|$)" >/dev/null \
        || die "Temporary firewall does not allow IPv4 SSH port ${BOOTSTRAP_SSH_PORT}."

    nft list chain "${FIREWALL_FAMILY}" "${FIREWALL_TABLE}" input \
        | grep -E "tcp dport ${FINAL_SSH_PORT}([[:space:]]|$)" >/dev/null \
        || die "Temporary firewall does not allow IPv4 SSH port ${FINAL_SSH_PORT}."
)

prepare_firewall() {
    install_bootstrap_firewall
    remove_ufw
    install_bootstrap_firewall
    log "IPv4 bootstrap firewall is active on TCP ${BOOTSTRAP_SSH_PORT} and ${FINAL_SSH_PORT}"
}

verify_public_repository_access() {
    local origin

    origin="$(git -C "${REPO_DIR}" remote get-url origin 2>/dev/null)" \
        || die "Cannot read Git origin."

    case "${origin}" in
        https://github.com/MatthewFreeman/discrete-infrastructure|https://github.com/MatthewFreeman/discrete-infrastructure.git)
            ;;
        *)
            die "Git origin must be the canonical public repository: ${origin}"
            ;;
    esac

    GIT_TERMINAL_PROMPT=0 git \
        -c credential.helper= \
        -c http.https://github.com/.extraheader= \
        ls-remote "${origin}" HEAD >/dev/null 2>&1 \
        || die "Anonymous HTTPS access to Git origin failed: ${origin}"
}

build_bootstrap_fail2ban_config() {
    local source_config="${REPO_DIR}/configs/fail2ban/jail.local"
    local output_config="$1"

    [[ -r "${source_config}" ]] \
        || die "Cannot read Fail2Ban source config: ${source_config}"

    awk -v bootstrap_port="${BOOTSTRAP_SSH_PORT}" \
        -v final_port="${FINAL_SSH_PORT}" '
        /^[[:space:]]*port[[:space:]]*=[[:space:]]*22822[[:space:]]*$/ && !replaced {
            printf "port = %s,%s\n", bootstrap_port, final_port
            replaced = 1
            next
        }
        { print }
        END { if (!replaced) exit 42 }
    ' "${source_config}" > "${output_config}" \
        || die "Could not create temporary IPv4 two-port Fail2Ban configuration."
}

wait_for_fail2ban_table() {
    local attempt

    for ((attempt = 1; attempt <= 40; attempt++)); do
        if nft list table "${FAIL2BAN_FAMILY}" "${FAIL2BAN_TABLE}" \
            >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.25
    done

    fail2ban-client status sshd >&2 || true
    journalctl -u fail2ban -n 60 --no-pager >&2 || true
    return 1
}

fail2ban_rule_has_port() {
    local port="$1"
    local ruleset

    ruleset="$(nft list table "${FAIL2BAN_FAMILY}" "${FAIL2BAN_TABLE}" 2>/dev/null)" \
        || return 1

    awk -v expected_port="${port}" '
        /tcp dport/ && /@addr-set-sshd/ {
            line = $0
            gsub(/[{},]/, " ", line)
            count = split(line, fields, /[[:space:]]+/)
            for (i = 1; i <= count; i++) {
                if (fields[i] == expected_port) found = 1
            }
        }
        END { exit !found }
    ' <<<"${ruleset}"
}

assert_nft_table_absent() {
    local family="$1"
    local table="$2"
    local error_message="$3"

    if nft list table "${family}" "${table}" >/dev/null 2>&1; then
        die "${error_message}"
    fi

    return 0
}

install_bootstrap_fail2ban() (
    local temporary_config

    temporary_config="$(mktemp)"
    trap 'rm -f "${temporary_config}"' EXIT
    build_bootstrap_fail2ban_config "${temporary_config}"

    log "Applying temporary IPv4 two-port Fail2Ban configuration"
    install -m 0644 "${REPO_DIR}/configs/fail2ban/fail2ban.local" \
        /etc/fail2ban/fail2ban.local
    install -m 0644 "${temporary_config}" /etc/fail2ban/jail.local

    fail2ban-client -t
    bash "${REPO_DIR}/scripts/restart-fail2ban.sh"
    fail2ban-client ping
    fail2ban-client status sshd

    wait_for_fail2ban_table \
        || die "IPv4 Fail2Ban nftables table did not initialize."
    fail2ban_rule_has_port "${BOOTSTRAP_SSH_PORT}" \
        || die "Fail2Ban does not protect bootstrap SSH TCP ${BOOTSTRAP_SSH_PORT}."
    fail2ban_rule_has_port "${FINAL_SSH_PORT}" \
        || die "Fail2Ban does not protect final SSH TCP ${FINAL_SSH_PORT}."

    assert_nft_table_absent \
        inet \
        "${FAIL2BAN_TABLE}" \
        "Legacy inet Fail2Ban table remains."

    printf 'Temporary IPv4 Fail2Ban verification passed.\n'
    return 0
)

apply_prepare_components() {
    prepare_firewall
    install_bootstrap_fail2ban

    log "Verifying prepared IPv4-only services"
    bash "${REPO_DIR}/scripts/verify.sh" nftables-bootstrap
    bash "${REPO_DIR}/scripts/verify.sh" fail2ban-bootstrap
}

confirm_admin_ssh_test() {
    if [[ "${ADMIN_SSH_CONFIRMED:-0}" == "1" ]]; then
        return
    fi

    local confirmation

    printf '\nBefore finalizing, confirm that a NEW IPv4 SSH session works:\n'
    printf '  user: %s\n' "${ADMIN_USER}"
    printf '  port: %s\n' "${FINAL_SSH_PORT}"
    printf 'and that "sudo -i" reaches root.\n\n'

    read -r -p "Type '${ADMIN_USER}' to confirm that test: " confirmation
    [[ "${confirmation}" == "${ADMIN_USER}" ]] \
        || die "Administrative IPv4 SSH test was not confirmed."
}

verify_final_ssh_runtime() {
    local effective
    local ports

    effective="$(sshd -T)" || return 1
    grep -x 'addressfamily inet' <<<"${effective}" >/dev/null || return 1

    mapfile -t ports < <(awk '$1 == "port" { print $2 }' <<<"${effective}")
    [[ ${#ports[@]} -eq 1 && "${ports[0]}" == "${FINAL_SSH_PORT}" ]] || return 1
    grep -x 'permitrootlogin no' <<<"${effective}" >/dev/null || return 1

    wait_for_ipv4_sshd_listener "${FINAL_SSH_PORT}" || return 1
    wait_for_ipv4_listener_absent "${BOOTSTRAP_SSH_PORT}" || return 1
    verify_no_ipv6_listener || return 1
}

finalize_ssh() {
    local temporary_backup=""

    if [[ -f "${TEMP_SSH_CONFIG}" ]]; then
        temporary_backup="$(mktemp)"
        cp -a "${TEMP_SSH_CONFIG}" "${temporary_backup}"
        rm -f "${TEMP_SSH_CONFIG}"
    fi

    if bash "${REPO_DIR}/scripts/apply-config.sh" ssh \
       && verify_final_ssh_runtime; then
        rm -f "${temporary_backup}"
        return 0
    fi

    printf 'ERROR: Final IPv4 SSH state is invalid; restoring temporary access.\n' >&2

    if [[ -n "${temporary_backup}" && -f "${temporary_backup}" ]]; then
        install -m 0644 "${temporary_backup}" "${TEMP_SSH_CONFIG}"
        sshd -t
        systemctl reload ssh
        wait_for_ipv4_sshd_listener "${BOOTSTRAP_SSH_PORT}" || true
        wait_for_ipv4_sshd_listener "${FINAL_SSH_PORT}" || true
    fi

    rm -f "${temporary_backup}"
    die "Final SSH configuration failed. Temporary IPv4 root SSH access was restored."
}

verify_no_ufw() {
    if dpkg-query -W -f='${Status}\n' ufw 2>/dev/null \
        | grep -x 'install ok installed' >/dev/null; then
        die "UFW is still installed."
    fi

    if systemctl is-active --quiet ufw.service 2>/dev/null; then
        die "UFW service is still active."
    fi

    assert_nft_table_absent ip filter "Legacy IPv4 filter table remains."
    assert_nft_table_absent ip6 filter "Legacy IPv6 filter table remains."

    return 0
}

print_network_banner() {
    printf 'Network stack:          IPv4 only\n'
    printf 'IPv6 addresses/routes: none\n'
    printf 'IPv6 listeners:        none\n'
}

prepare() {
    [[ ! -e "${FINALIZED_MARKER}" ]] \
        || die "Bootstrap is already finalized. Use '$0 status'."

    install_base_packages
    configure_host_baseline
    ensure_admin_user
    write_temporary_ssh_config
    apply_prepare_components

    verify_public_repository_access

    printf '\n============================================================\n'
    printf 'PREPARE PHASE COMPLETE\n'
    printf '============================================================\n'
    printf 'Network stack:          IPv4 only\n'
    printf 'IPv6 addresses/routes: none\n'
    if [[ "${PREPARE_IPV6_LISTENER_STATE}" == "transient-x11" ]]; then
        printf 'IPv6 listeners:        transient loopback X11; close original session before finalize\n'
    else
        printf 'IPv6 listeners:        none\n'
    fi
    printf 'SSH ports:             %s and %s\n' \
        "${BOOTSTRAP_SSH_PORT}" "${FINAL_SSH_PORT}"
    printf 'Administrative user:  %s\n' "${ADMIN_USER}"
    printf 'Root SSH login:        temporarily allowed\n'
    printf 'Firewall:              ip discrete_filter\n'
    printf 'UFW:                   removed\n'
    printf 'Fail2Ban table:        ip f2b-table\n'
    printf 'Fail2Ban SSH ports:    %s and %s\n' \
        "${BOOTSTRAP_SSH_PORT}" "${FINAL_SSH_PORT}"
    printf 'Time synchronization: systemd-timesyncd client\n'
    printf 'UDP 123 listener:      none\n'
    printf 'Repository access:     public anonymous HTTPS\n\n'
    printf 'Keep the original IPv4 root session open.\n'
}

finalize() {
    rm -f "${FINALIZED_MARKER}"

    install_base_packages
    configure_host_baseline

    id "${ADMIN_USER}" >/dev/null 2>&1 \
        || die "Administrative user does not exist: ${ADMIN_USER}"
    id -nG "${ADMIN_USER}" | tr ' ' '\n' | grep -x sudo >/dev/null \
        || die "${ADMIN_USER} is not a member of sudo."

    verify_no_ufw

    nft list chain ip discrete_filter input \
        | grep -E "tcp dport ${BOOTSTRAP_SSH_PORT}([[:space:]]|$)" >/dev/null \
        || die "Temporary firewall does not protect IPv4 TCP ${BOOTSTRAP_SSH_PORT}."
    nft list chain ip discrete_filter input \
        | grep -E "tcp dport ${FINAL_SSH_PORT}([[:space:]]|$)" >/dev/null \
        || die "Temporary firewall does not protect IPv4 TCP ${FINAL_SSH_PORT}."

    verify_public_repository_access
    confirm_admin_ssh_test

    log "Applying final IPv4-only SSH configuration"
    finalize_ssh

    log "Applying final IPv4 firewall and Fail2Ban configuration"
    bash "${REPO_DIR}/scripts/apply-config.sh" nftables
    bash "${REPO_DIR}/scripts/apply-config.sh" fail2ban

    remove_ufw
    verify_no_ufw

    log "Running complete IPv4-only verification"
    bash "${REPO_DIR}/scripts/verify.sh" all

    install -d -m 0755 "${STATE_DIR}"
    date --utc --iso-8601=seconds > "${FINALIZED_MARKER}"
    chmod 0644 "${FINALIZED_MARKER}"

    printf '\n============================================================\n'
    printf 'BOOTSTRAP FINALIZED\n'
    printf '============================================================\n'
    print_network_banner
    printf 'Administrative SSH:    %s@server:%s\n' \
        "${ADMIN_USER}" "${FINAL_SSH_PORT}"
    printf 'Direct root SSH:       disabled\n'
    printf 'Temporary SSH port:    closed\n'
    printf 'Firewall:              ip discrete_filter\n'
    printf 'UFW:                   absent\n'
    printf 'Fail2Ban table:        ip f2b-table\n'
    printf 'Fail2Ban:              active\n'
    printf 'Time synchronization: systemd-timesyncd client\n'
    printf 'UDP 123 listener:      none\n'
    printf 'Git origin:            %s\n\n' \
        "$(git -C "${REPO_DIR}" remote get-url origin)"
}

status() {
    printf 'Repository: %s\n' "${REPO_DIR}"
    printf 'Origin:     %s\n' \
        "$(git -C "${REPO_DIR}" remote get-url origin 2>/dev/null || echo unavailable)"
    printf 'Admin user: %s\n' "${ADMIN_USER}"

    if [[ -e "${FINALIZED_MARKER}" ]]; then
        printf 'Bootstrap:  finalized at %s\n' "$(cat "${FINALIZED_MARKER}")"
    else
        printf 'Bootstrap:  not marked finalized\n'
    fi

    printf '\nIPv6 interface flags:\n'
    for flag in /proc/sys/net/ipv6/conf/*/disable_ipv6; do
        printf '%-18s %s\n' "$(basename "$(dirname "${flag}")")" "$(cat "${flag}")"
    done

    printf '\nIPv6 addresses:\n'
    ip -6 -o address show || true
    printf '\nIPv6 routes:\n'
    ip -6 route show table all || true
    printf '\nIPv6 listeners:\n'
    ss -6 -H -lntup || true

    printf '\nSSH effective configuration:\n'
    sshd -T | grep -E \
        '^(addressfamily|port|permitrootlogin|passwordauthentication|pubkeyauthentication|logingracetime|maxauthtries) '

    printf '\nIPv4 listening sockets:\n'
    ss -4 -lntup || true

    printf '\nnftables tables:\n'
    nft list tables

    printf '\nUFW:\n'
    if dpkg-query -W -f='${Status}\n' ufw 2>/dev/null \
        | grep -x 'install ok installed' >/dev/null; then
        printf 'installed\n'
    else
        printf 'absent\n'
    fi

    printf '\nFail2Ban:\n'
    if systemctl is-active --quiet fail2ban; then
        fail2ban-client ping
        fail2ban-client status sshd
    else
        systemctl status fail2ban --no-pager -l || true
    fi

    printf '\nTime synchronization:\n'
    systemctl is-active --quiet systemd-timesyncd.service \
        && printf 'systemd-timesyncd: active\n' \
        || printf 'systemd-timesyncd: inactive\n'
    printf 'NTP synchronized: %s\n' \
        "$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown)"

    printf '\nGit working tree:\n'
    git -C "${REPO_DIR}" status --short
}

usage() {
    cat <<EOF
Usage:
  ADMIN_USER=serveradmin $0 prepare
  ADMIN_USER=serveradmin $0 finalize
  ADMIN_USER=serveradmin $0 status
EOF
}

main() {
    require_root
    validate_admin_user
    check_platform
    cd "${REPO_DIR}"

    case "${1:-}" in
        prepare)
            prepare
            ;;
        finalize)
            finalize
            ;;
        status)
            status
            ;;
        *)
            usage
            exit 2
            ;;
    esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
