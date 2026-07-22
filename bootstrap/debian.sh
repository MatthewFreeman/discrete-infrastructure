#!/usr/bin/env bash
set -Eeuo pipefail

umask 027

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly STATE_DIR="/var/lib/discrete-infrastructure"
readonly FINALIZED_MARKER="${STATE_DIR}/bootstrap-finalized"
readonly TEMP_SSH_CONFIG="/etc/ssh/sshd_config.d/00-discrete-bootstrap.conf"
readonly DEPLOY_KEY="/root/.ssh/discrete_infrastructure_deploy"
readonly SSH_CONFIG="/root/.ssh/config"
readonly SSH_ALIAS="github-discrete"
readonly SSH_PORT="22822"

ADMIN_USER="${ADMIN_USER:-serveradmin}"

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
        nftables \
        openssh-server \
        python3-systemd \
        sudo

    systemctl enable --now ssh
    systemctl enable fail2ban >/dev/null
}

ensure_admin_user() {
    log "Creating or validating administrative user: ${ADMIN_USER}"

    ADMIN_USER="${ADMIN_USER}" \
        bash "${REPO_DIR}/bootstrap/create-admin.sh"

    local admin_home
    local admin_group

    admin_home="$(getent passwd "${ADMIN_USER}" | cut -d: -f6)"
    admin_group="$(id -gn "${ADMIN_USER}")"

    [[ -n "${admin_home}" ]] || die "Cannot determine home directory for ${ADMIN_USER}."

    install -d \
        -m 0700 \
        -o "${ADMIN_USER}" \
        -g "${admin_group}" \
        "${admin_home}/.ssh"

    if [[ -s /root/.ssh/authorized_keys \
       && ! -e "${admin_home}/.ssh/authorized_keys" ]]; then

        log "Copying root authorized_keys to ${ADMIN_USER}"

        install \
            -m 0600 \
            -o "${ADMIN_USER}" \
            -g "${admin_group}" \
            /root/.ssh/authorized_keys \
            "${admin_home}/.ssh/authorized_keys"
    fi
}

server_appears_finalized() {
    [[ -f /etc/ssh/sshd_config.d/00-discrete.conf ]] \
        && sshd -T 2>/dev/null \
            | grep -qx 'permitrootlogin no'
}

write_temporary_ssh_config() {
    if server_appears_finalized \
       && [[ ! -f "${TEMP_SSH_CONFIG}" ]] \
       && [[ "${FORCE_PREPARE:-0}" != "1" ]]; then

        die "This server already appears finalized. Use '$0 status'. Do not run prepare again."
    fi

    log "Installing temporary SSH configuration"

    cat > "${TEMP_SSH_CONFIG}" <<EOF2
# Temporary bootstrap configuration.
# Removed by: bootstrap/debian.sh finalize

Port ${SSH_PORT}
PermitRootLogin yes
PasswordAuthentication yes
PubkeyAuthentication yes

LoginGraceTime 30
MaxAuthTries 3

X11Forwarding no
AllowAgentForwarding no
EOF2

    chmod 0644 "${TEMP_SSH_CONFIG}"

    sshd -t
    systemctl reload ssh
}

prepare_nftables_service() {
    log "Preparing nftables service"

    systemctl enable nftables >/dev/null

    if ! systemctl is-active --quiet nftables; then
        install \
            -m 0644 \
            "${REPO_DIR}/configs/nftables/nftables.conf" \
            /etc/nftables.conf

        nft --check --file /etc/nftables.conf

        if nft list table inet discrete_filter >/dev/null 2>&1; then
            nft delete table inet discrete_filter
        fi

        systemctl reset-failed nftables >/dev/null 2>&1 || true
        systemctl start nftables
    fi
}

repository_full_name() {
    local remote_url
    local repo_path

    remote_url="$(git -C "${REPO_DIR}" remote get-url origin)"

    if [[ "${remote_url}" =~ ^https://([^/@]+@)?github\.com/(.+)$ ]]; then
        repo_path="${BASH_REMATCH[2]}"
    elif [[ "${remote_url}" =~ ^ssh://git@github\.com/(.+)$ ]]; then
        repo_path="${BASH_REMATCH[1]}"
    elif [[ "${remote_url}" =~ ^git@[^:]+:(.+)$ ]]; then
        repo_path="${BASH_REMATCH[1]}"
    else
        die "Cannot derive GitHub repository from origin: ${remote_url}"
    fi

    repo_path="${repo_path%.git}"

    [[ "${repo_path}" == */* ]] \
        || die "Invalid GitHub repository path: ${repo_path}"

    printf '%s\n' "${repo_path}"
}

write_deploy_ssh_config() {
    local temporary_config

    install -d -m 0700 /root/.ssh
    touch "${SSH_CONFIG}"
    chmod 0600 "${SSH_CONFIG}"

    temporary_config="$(mktemp)"

    awk '
        $0 == "# BEGIN discrete-infrastructure deploy key" {
            skip = 1
            next
        }
        $0 == "# END discrete-infrastructure deploy key" {
            skip = 0
            next
        }
        !skip {
            print
        }
    ' "${SSH_CONFIG}" > "${temporary_config}"

    cat >> "${temporary_config}" <<EOF2

# BEGIN discrete-infrastructure deploy key
Host ${SSH_ALIAS}
    HostName github.com
    User git
    IdentityFile ${DEPLOY_KEY}
    IdentitiesOnly yes
    BatchMode yes
# END discrete-infrastructure deploy key
EOF2

    install -m 0600 "${temporary_config}" "${SSH_CONFIG}"
    rm -f "${temporary_config}"
}

ensure_deploy_key() {
    local repo_name
    local ssh_remote

    repo_name="$(repository_full_name)"
    ssh_remote="git@${SSH_ALIAS}:${repo_name}.git"

    install -d -m 0700 /root/.ssh

    if [[ ! -f "${DEPLOY_KEY}" ]]; then
        log "Generating dedicated GitHub deploy key"

        ssh-keygen \
            -q \
            -t ed25519 \
            -N "" \
            -C "discrete-infrastructure-$(hostname)-deploy" \
            -f "${DEPLOY_KEY}"
    fi

    chmod 0600 "${DEPLOY_KEY}"
    chmod 0644 "${DEPLOY_KEY}.pub"

    write_deploy_ssh_config

    if git ls-remote "${ssh_remote}" HEAD >/dev/null 2>&1; then
        git -C "${REPO_DIR}" remote set-url origin "${ssh_remote}"

        log "Read-only GitHub deploy key is working"
        printf 'Origin: %s\n' "${ssh_remote}"
        return 0
    fi

    printf '\n'
    printf 'The deploy key is not registered in GitHub yet.\n'
    printf 'Add this PUBLIC key to the repository as a read-only deploy key:\n\n'
    cat "${DEPLOY_KEY}.pub"
    printf '\n'
    printf 'GitHub path:\n'
    printf '  Repository Settings -> Deploy keys -> Add deploy key\n'
    printf '  Leave "Allow write access" DISABLED.\n'

    return 1
}

apply_prepare_components() {
    log "Applying nftables configuration"
    bash "${REPO_DIR}/scripts/apply-config.sh" nftables

    log "Applying Fail2Ban configuration"
    bash "${REPO_DIR}/scripts/apply-config.sh" fail2ban

    log "Verifying prepared services"
    bash "${REPO_DIR}/scripts/verify.sh" nftables
    bash "${REPO_DIR}/scripts/verify.sh" fail2ban
}

confirm_admin_ssh_test() {
    if [[ "${ADMIN_SSH_CONFIRMED:-0}" == "1" ]]; then
        return
    fi

    local confirmation

    printf '\n'
    printf 'Before finalizing, confirm that a NEW SSH session works:\n'
    printf '  user: %s\n' "${ADMIN_USER}"
    printf '  port: %s\n' "${SSH_PORT}"
    printf 'and that "sudo -i" reaches root.\n\n'

    read -r -p "Type '${ADMIN_USER}' to confirm that test: " confirmation

    [[ "${confirmation}" == "${ADMIN_USER}" ]] \
        || die "Administrative SSH test was not confirmed."
}

finalize_ssh() {
    local temporary_backup=""

    if [[ -f "${TEMP_SSH_CONFIG}" ]]; then
        temporary_backup="$(mktemp)"
        cp -a "${TEMP_SSH_CONFIG}" "${temporary_backup}"
        rm -f "${TEMP_SSH_CONFIG}"
    fi

    if ! bash "${REPO_DIR}/scripts/apply-config.sh" ssh; then
        if [[ -n "${temporary_backup}" && -f "${temporary_backup}" ]]; then
            install -m 0644 "${temporary_backup}" "${TEMP_SSH_CONFIG}"
            sshd -t
            systemctl reload ssh
        fi

        rm -f "${temporary_backup}"
        die "Final SSH configuration failed. Temporary root SSH access was restored."
    fi

    rm -f "${temporary_backup}"
}

prepare() {
    [[ ! -e "${FINALIZED_MARKER}" ]] \
        || die "Bootstrap is already finalized. Use '$0 status'."

    install_base_packages
    ensure_admin_user
    write_temporary_ssh_config
    prepare_nftables_service
    apply_prepare_components

    local deploy_key_ready="no"

    if ensure_deploy_key; then
        deploy_key_ready="yes"
    fi

    printf '\n'
    printf '============================================================\n'
    printf 'PREPARE PHASE COMPLETE\n'
    printf '============================================================\n'
    printf 'SSH port:             %s\n' "${SSH_PORT}"
    printf 'Administrative user:  %s\n' "${ADMIN_USER}"
    printf 'Root SSH login:        temporarily allowed\n'
    printf 'Deploy key ready:      %s\n' "${deploy_key_ready}"
    printf '\n'
    printf 'Keep this root session open.\n'
    printf 'Open a NEW SSH session as %s on port %s and test:\n' \
        "${ADMIN_USER}" "${SSH_PORT}"
    printf '  sudo -i\n'
    printf '  whoami\n'
    printf '\n'
    printf 'After the deploy key is added and the admin login is tested, run:\n'
    printf '  ADMIN_USER=%q bash %q finalize\n' \
        "${ADMIN_USER}" "${REPO_DIR}/bootstrap/debian.sh"
}

finalize() {
    install_base_packages

    id "${ADMIN_USER}" >/dev/null 2>&1 \
        || die "Administrative user does not exist: ${ADMIN_USER}"

    id -nG "${ADMIN_USER}" \
        | tr ' ' '\n' \
        | grep -qx sudo \
        || die "${ADMIN_USER} is not a member of sudo."

    ensure_deploy_key \
        || die "Register the printed deploy key in GitHub, then run finalize again."

    confirm_admin_ssh_test

    log "Applying final SSH configuration"
    finalize_ssh

    log "Reapplying persistent firewall and Fail2Ban configuration"
    bash "${REPO_DIR}/scripts/apply-config.sh" nftables
    bash "${REPO_DIR}/scripts/apply-config.sh" fail2ban

    log "Running complete verification"
    bash "${REPO_DIR}/scripts/verify.sh" all

    install -d -m 0755 "${STATE_DIR}"
    date --utc --iso-8601=seconds > "${FINALIZED_MARKER}"
    chmod 0644 "${FINALIZED_MARKER}"

    printf '\n'
    printf '============================================================\n'
    printf 'BOOTSTRAP FINALIZED\n'
    printf '============================================================\n'
    printf 'Administrative SSH:    %s@server:%s\n' \
        "${ADMIN_USER}" "${SSH_PORT}"
    printf 'Direct root SSH:       disabled\n'
    printf 'Firewall:              inet discrete_filter\n'
    printf 'Fail2Ban:              active\n'
    printf 'Git origin:            %s\n' \
        "$(git -C "${REPO_DIR}" remote get-url origin)"
    printf '\n'
    printf 'Keep the current session open while performing two final tests:\n'
    printf '  1. A new %s SSH session succeeds.\n' "${ADMIN_USER}"
    printf '  2. A new root SSH session is denied.\n'
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

    printf '\nSSH effective configuration:\n'
    sshd -T \
        | grep -E \
            '^(port|permitrootlogin|passwordauthentication|pubkeyauthentication|logingracetime|maxauthtries) '

    printf '\nnftables tables:\n'
    nft list tables

    printf '\nFail2Ban:\n'
    if systemctl is-active --quiet fail2ban; then
        fail2ban-client ping
        fail2ban-client status sshd
    else
        systemctl status fail2ban --no-pager -l || true
    fi

    printf '\nGit working tree:\n'
    git -C "${REPO_DIR}" status --short
}

usage() {
    cat <<EOF2
Usage:
  ADMIN_USER=serveradmin $0 prepare
  ADMIN_USER=serveradmin $0 finalize
  ADMIN_USER=serveradmin $0 status

prepare:
  Installs packages, creates the admin account, moves SSH to port ${SSH_PORT},
  keeps root SSH temporarily enabled, applies nftables and Fail2Ban, and
  generates a read-only GitHub deploy key.

finalize:
  Requires a tested admin SSH login and a registered deploy key. It removes
  temporary root SSH access, applies all final configurations, and verifies
  the complete baseline.

status:
  Displays the effective SSH, nftables, Fail2Ban, Git, and bootstrap state.
EOF2
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

main "$@"
