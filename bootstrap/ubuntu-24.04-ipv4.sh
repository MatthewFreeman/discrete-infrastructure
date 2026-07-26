#!/usr/bin/env bash
set -Eeuo pipefail

UBUNTU_PLATFORM_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly UBUNTU_PLATFORM_DIR

# Debian remains the validated reference implementation. Ubuntu overrides only behavior that
# differs on Ubuntu cloud images while reusing the shared firewall, deployment, rollback,
# audit, and verification logic.
# shellcheck source=bootstrap/debian-ipv4.sh
source "${UBUNTU_PLATFORM_DIR}/debian-ipv4.sh"

check_platform() {
    local os_release_file="${UBUNTU_OS_RELEASE_FILE:-/etc/os-release}"
    local ID=""
    local VERSION_ID=""

    [[ -r "${os_release_file}" ]] || die "Cannot identify the operating system."

    # shellcheck disable=SC1090
    source "${os_release_file}"

    [[ "${ID:-}" == "ubuntu" ]] \
        || die "This entrypoint supports Ubuntu only."
    [[ "${VERSION_ID:-}" == "24.04" ]] \
        || die "This bootstrap is validated for Ubuntu 24.04, found ${VERSION_ID:-unknown}."
}

install_base_packages() {
    log "Installing Ubuntu 24.04 base packages"

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

    # Ubuntu 24.04 normally uses OpenSSH socket activation. The bootstrap manages two temporary
    # ports and then one final port, so regular service mode is deterministic and easier to verify.
    systemctl disable --now ssh.socket >/dev/null 2>&1 || true
    systemctl enable --now ssh.service
    systemctl is-active --quiet ssh.service \
        || die "OpenSSH service mode did not become active."

    systemctl enable fail2ban >/dev/null
}

ubuntu_cloud_user_mode() {
    [[ -n "${BOOTSTRAP_SOURCE_USER:-}" ]]
}

ubuntu_temporary_root_login_policy() {
    if ubuntu_cloud_user_mode; then
        printf 'no\n'
    else
        printf 'yes\n'
    fi
}

ensure_admin_user() {
    log "Creating or validating administrative user: ${ADMIN_USER}"

    ADMIN_USER="${ADMIN_USER}" \
        bash "${REPO_DIR}/bootstrap/create-admin.sh"

    local admin_home
    local admin_group
    local admin_keys
    local source_user
    local source_home
    local source_keys

    admin_home="$(getent passwd "${ADMIN_USER}" | cut -d: -f6)"
    admin_group="$(id -gn "${ADMIN_USER}")"

    [[ -n "${admin_home}" ]] \
        || die "Cannot determine home directory for ${ADMIN_USER}."

    install -d -m 0700 -o "${ADMIN_USER}" -g "${admin_group}" \
        "${admin_home}/.ssh"
    admin_keys="${admin_home}/.ssh/authorized_keys"

    if ubuntu_cloud_user_mode; then
        source_user="${BOOTSTRAP_SOURCE_USER}"
        [[ "${source_user}" != "root" ]] \
            || die "BOOTSTRAP_SOURCE_USER must name the original non-root cloud user."
        id "${source_user}" >/dev/null 2>&1 \
            || die "BOOTSTRAP_SOURCE_USER does not exist: ${source_user}"

        source_home="$(getent passwd "${source_user}" | cut -d: -f6)"
        [[ -n "${source_home}" ]] \
            || die "Cannot determine home directory for ${source_user}."
        source_keys="${source_home}/.ssh/authorized_keys"

        if [[ -s "${source_keys}" && ! -e "${admin_keys}" ]]; then
            log "Copying ${source_user} authorized_keys directly to ${ADMIN_USER}"
            install -m 0600 -o "${ADMIN_USER}" -g "${admin_group}" \
                "${source_keys}" \
                "${admin_keys}"
        elif [[ ! -s "${source_keys}" ]]; then
            log "No SSH authorized_keys found for ${source_user}; use the ${ADMIN_USER} password for the fresh login test"
        fi
    elif [[ -s /root/.ssh/authorized_keys && ! -e "${admin_keys}" ]]; then
        log "Copying root authorized_keys to ${ADMIN_USER}"
        install -m 0600 -o "${ADMIN_USER}" -g "${admin_group}" \
            /root/.ssh/authorized_keys \
            "${admin_keys}"
    fi
}

write_temporary_ssh_config() {
    if server_appears_finalized \
       && [[ ! -f "${TEMP_SSH_CONFIG}" ]] \
       && [[ "${FORCE_PREPARE:-0}" != "1" ]]; then
        die "This server already appears finalized. Use '$0 status'. Do not run prepare again."
    fi

    local permit_root_login
    permit_root_login="$(ubuntu_temporary_root_login_policy)"

    log "Installing temporary Ubuntu IPv4 two-port SSH configuration"

    cat > "${TEMP_SSH_CONFIG}" <<EOF
# Temporary Ubuntu IPv4-only bootstrap configuration.
# Removed by: bootstrap/run-ubuntu-24.04.sh finalize

AddressFamily inet
Port ${BOOTSTRAP_SSH_PORT}
Port ${FINAL_SSH_PORT}

PermitRootLogin ${permit_root_login}
PasswordAuthentication yes
PubkeyAuthentication yes

LoginGraceTime 30
MaxAuthTries 3

X11Forwarding no
AllowAgentForwarding no
EOF

    chmod 0644 "${TEMP_SSH_CONFIG}"
    sshd -t
    systemctl reload ssh.service

    wait_for_ipv4_sshd_listener "${BOOTSTRAP_SSH_PORT}" \
        || die "sshd is not listening on IPv4 bootstrap port ${BOOTSTRAP_SSH_PORT}."
    wait_for_ipv4_sshd_listener "${FINAL_SSH_PORT}" \
        || die "sshd is not listening on IPv4 final port ${FINAL_SSH_PORT}."
    verify_prepare_ipv6_listener_state \
        || die "OpenSSH exposes an IPv6 listener that is not a transient loopback X11 proxy."
}

prepare() {
    [[ ! -e "${FINALIZED_MARKER}" ]] \
        || die "Bootstrap is already finalized. Use '$0 status'."

    install_base_packages
    configure_host_baseline
    ensure_admin_user
    write_temporary_ssh_config
    apply_prepare_components

    local deploy_key_ready="no"
    ensure_deploy_key && deploy_key_ready="yes"

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
    if ubuntu_cloud_user_mode; then
        printf 'Temporary SSH user:    %s on TCP %s\n' \
            "${BOOTSTRAP_SOURCE_USER}" "${BOOTSTRAP_SSH_PORT}"
        printf 'Root SSH login:        disabled; root account remains locked\n'
    else
        printf 'Temporary SSH user:    root on TCP %s\n' "${BOOTSTRAP_SSH_PORT}"
        printf 'Root SSH login:        temporarily allowed\n'
    fi
    printf 'Firewall:              ip discrete_filter\n'
    printf 'UFW:                   removed\n'
    printf 'Fail2Ban table:        ip f2b-table\n'
    printf 'Fail2Ban SSH ports:    %s and %s\n' \
        "${BOOTSTRAP_SSH_PORT}" "${FINAL_SSH_PORT}"
    printf 'Time synchronization: systemd-timesyncd client\n'
    printf 'UDP 123 listener:      none\n'
    printf 'Deploy key ready:      %s\n\n' "${deploy_key_ready}"
    printf 'Keep the original IPv4 SSH session open.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
