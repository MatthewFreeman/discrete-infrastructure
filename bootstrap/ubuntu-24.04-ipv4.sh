#!/usr/bin/env bash
set -Eeuo pipefail

UBUNTU_PLATFORM_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly UBUNTU_PLATFORM_DIR

# The Debian implementation remains the validated reference. Ubuntu overrides only the
# platform-specific behavior while reusing the common bootstrap, firewall, deployment,
# rollback, audit, and verification logic.
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

    # Ubuntu 24.04 enables OpenSSH socket activation on standard images. The shared
    # bootstrap manages two temporary ports and then one final port, so use the regular
    # ssh.service model to make configuration reloads deterministic.
    systemctl disable --now ssh.socket >/dev/null 2>&1 || true
    systemctl enable --now ssh.service
    systemctl is-active --quiet ssh.service \
        || die "OpenSSH service mode did not become active."

    systemctl enable fail2ban >/dev/null
}

seed_root_authorized_keys_from_initial_user() {
    local source_user="${BOOTSTRAP_SOURCE_USER:-${SUDO_USER:-}}"
    local source_home
    local source_keys

    [[ -n "${source_user}" && "${source_user}" != "root" ]] || return 0

    if ! id "${source_user}" >/dev/null 2>&1; then
        [[ -z "${BOOTSTRAP_SOURCE_USER:-}" ]] \
            || die "BOOTSTRAP_SOURCE_USER does not exist: ${source_user}"
        return 0
    fi

    source_home="$(getent passwd "${source_user}" | cut -d: -f6)"
    [[ -n "${source_home}" ]] || return 0

    source_keys="${source_home}/.ssh/authorized_keys"
    [[ -s "${source_keys}" ]] || return 0

    if [[ ! -s /root/.ssh/authorized_keys ]]; then
        log "Copying ${source_user} authorized_keys to temporary root SSH access"
        install -d -m 0700 -o root -g root /root/.ssh
        install -m 0600 -o root -g root \
            "${source_keys}" \
            /root/.ssh/authorized_keys
    fi
}

ensure_admin_user() {
    seed_root_authorized_keys_from_initial_user

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

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
