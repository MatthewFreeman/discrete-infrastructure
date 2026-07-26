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

readonly BOOTSTRAP_SSH_PORT="22"
readonly FINAL_SSH_PORT="22822"

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

wait_for_tcp_listener() {
    local port="$1"
    local attempt
    local listeners

    for attempt in {1..40}; do
        listeners="$(ss -H -lnt 2>/dev/null || true)"

        if awk -v expected_port=":${port}" '
            $4 ~ expected_port "$" {
                found = 1
            }

            END {
                exit !found
            }
        ' <<<"${listeners}"
        then
            return 0
        fi

        sleep 0.25
    done

    printf 'ERROR: TCP listener on port %s did not appear within 10 seconds.\n' \
        "${port}" >&2

    printf '\nCurrent listeners:\n' >&2
    ss -lntp >&2 || true

    printf '\nRecent SSH service log:\n' >&2
    journalctl -u ssh -n 40 --no-pager >&2 || true

    return 1
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

    [[ -n "${admin_home}" ]] \
        || die "Cannot determine home directory for ${ADMIN_USER}."

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
            | grep -x 'permitrootlogin no' >/dev/null
}

write_temporary_ssh_config() {
    if server_appears_finalized \
       && [[ ! -f "${TEMP_SSH_CONFIG}" ]] \
       && [[ "${FORCE_PREPARE:-0}" != "1" ]]; then

        die "This server already appears finalized. Use '$0 status'. Do not run prepare again."
    fi

    log "Installing temporary two-port SSH configuration"

    cat > "${TEMP_SSH_CONFIG}" <<EOF
# Temporary bootstrap configuration.
# Removed by: bootstrap/debian.sh finalize

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

    wait_for_tcp_listener "${BOOTSTRAP_SSH_PORT}" \
        || die "sshd is not listening on bootstrap port ${BOOTSTRAP_SSH_PORT}."

    wait_for_tcp_listener "${FINAL_SSH_PORT}" \
        || die "sshd is not listening on final port ${FINAL_SSH_PORT}."
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

        {
            print
        }

        END {
            if (!inserted) {
                exit 42
            }
        }
    ' "${source_config}" > "${output_config}" \
        || die "Could not create the temporary bootstrap nftables configuration."
}

remove_ufw() {
    local ufw_installed="no"

    if dpkg-query -W -f='${Status}\n' ufw 2>/dev/null \
        | grep -x 'install ok installed' >/dev/null; then
        ufw_installed="yes"
    fi

    if command -v ufw >/dev/null 2>&1 || [[ "${ufw_installed}" == "yes" ]]; then
        log "Removing UFW so nftables is the only host firewall"

        if command -v ufw >/dev/null 2>&1; then
            ufw --force disable >/dev/null 2>&1 || true
        fi

        systemctl disable --now ufw.service >/dev/null 2>&1 || true

        if [[ "${ufw_installed}" == "yes" ]]; then
            DEBIAN_FRONTEND=noninteractive apt-get purge -y ufw
        fi
    fi

    # Some provider images leave nftables-compat UFW tables behind after the
    # package or service is removed. Delete only tables that clearly contain
    # UFW-owned chains.
    if nft list table ip filter >/tmp/discrete-ufw-ip.$$ 2>/dev/null; then
        if grep -q 'ufw-' /tmp/discrete-ufw-ip.$$; then
            nft delete table ip filter
        fi
    fi
    rm -f /tmp/discrete-ufw-ip.$$

    if nft list table ip6 filter >/tmp/discrete-ufw-ip6.$$ 2>/dev/null; then
        if grep -q 'ufw-' /tmp/discrete-ufw-ip6.$$; then
            nft delete table ip6 filter
        fi
    fi
    rm -f /tmp/discrete-ufw-ip6.$$

    if nft list ruleset | grep 'ufw-' >/dev/null; then
        die "Residual UFW rules are still present in nftables."
    fi
}

install_bootstrap_firewall() (
    local temporary_config

    temporary_config="$(mktemp)"
    trap 'rm -f "${temporary_config}"' EXIT

    build_bootstrap_nftables_config "${temporary_config}"

    log "Validating temporary bootstrap firewall"

    bash "${REPO_DIR}/scripts/apply-nftables.sh" \
        --check "${temporary_config}"

    install -m 0644 "${temporary_config}" /etc/nftables.conf
    systemctl enable nftables >/dev/null

    if systemctl is-active --quiet nftables; then
        bash "${REPO_DIR}/scripts/apply-nftables.sh" \
            --apply /etc/nftables.conf
    else
        # Start the service from the validated persistent config. Remove only
        # our own table first if this is a rerun after an interrupted bootstrap.
        if nft list table inet discrete_filter >/dev/null 2>&1; then
            nft delete table inet discrete_filter
        fi

        systemctl reset-failed nftables >/dev/null 2>&1 || true
        systemctl start nftables
    fi

    systemctl is-active --quiet nftables \
        || die "nftables service is not active."

    nft list chain inet discrete_filter input \
        | grep -E "tcp dport ${BOOTSTRAP_SSH_PORT}([[:space:]]|$)" >/dev/null \
        || die "Temporary firewall does not allow SSH port ${BOOTSTRAP_SSH_PORT}."

    nft list chain inet discrete_filter input \
        | grep -E "tcp dport ${FINAL_SSH_PORT}([[:space:]]|$)" >/dev/null \
        || die "Temporary firewall does not allow SSH port ${FINAL_SSH_PORT}."
)

prepare_firewall() {
    # Build and activate the two-port nftables policy while any provider UFW
    # rules still protect port 22. Then remove UFW and reapply our policy.
    install_bootstrap_firewall
    remove_ufw
    install_bootstrap_firewall

    log "Bootstrap firewall is active on ports ${BOOTSTRAP_SSH_PORT} and ${FINAL_SSH_PORT}"
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

    cat >> "${temporary_config}" <<EOF

# BEGIN discrete-infrastructure deploy key
Host ${SSH_ALIAS}
    HostName github.com
    User git
    IdentityFile ${DEPLOY_KEY}
    IdentitiesOnly yes
    BatchMode yes
    StrictHostKeyChecking accept-new
# END discrete-infrastructure deploy key
EOF

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

        {
            print
        }

        END {
            if (!replaced) {
                exit 42
            }
        }
    ' "${source_config}" > "${output_config}" \
        || die "Could not create temporary two-port Fail2Ban configuration."
}

fail2ban_nftables_rule_has_port() {
    local port="$1"
    local ruleset

    ruleset="$(nft list table inet f2b-table 2>/dev/null)" \
        || return 1

    awk -v expected_port="${port}" '
        /tcp dport/ && /@addr-set-sshd/ {
            line = $0
            gsub(/[{},]/, " ", line)

            count = split(line, fields, /[[:space:]]+/)

            for (i = 1; i <= count; i++) {
                if (fields[i] == expected_port) {
                    found = 1
                }
            }
        }

        END {
            exit !found
        }
    ' <<<"${ruleset}"
}

verify_bootstrap_fail2ban_ports() {
    local port

    for port in "${BOOTSTRAP_SSH_PORT}" "${FINAL_SSH_PORT}"; do
        if ! fail2ban_nftables_rule_has_port "${port}"; then
            printf 'ERROR: Fail2Ban nftables action is not protecting SSH port %s.\n' \
                "${port}" >&2

            printf '\nCurrent Fail2Ban nftables table:\n' >&2
            nft list table inet f2b-table >&2 || true

            return 1
        fi
    done
}

install_bootstrap_fail2ban() (
    local temporary_config

    temporary_config="$(mktemp)"
    trap 'rm -f "${temporary_config}"' EXIT

    build_bootstrap_fail2ban_config "${temporary_config}"

    log "Applying temporary two-port Fail2Ban configuration"

    install -m 0644 "${temporary_config}" /etc/fail2ban/jail.local

    fail2ban-client -t
    bash "${REPO_DIR}/scripts/restart-fail2ban.sh"

    fail2ban-client ping
    fail2ban-client status sshd

    verify_bootstrap_fail2ban_ports \
        || die "Fail2Ban is not protecting both bootstrap SSH ports."
)

apply_prepare_components() {
    prepare_firewall
    install_bootstrap_fail2ban

    log "Verifying prepared services"
    bash "${REPO_DIR}/scripts/verify.sh" nftables
    bash "${REPO_DIR}/scripts/verify.sh" fail2ban

    nft list chain inet discrete_filter input \
        | grep -E "tcp dport ${BOOTSTRAP_SSH_PORT}([[:space:]]|$)" >/dev/null \
        || die "Bootstrap verification lost SSH port ${BOOTSTRAP_SSH_PORT}."
}

confirm_admin_ssh_test() {
    if [[ "${ADMIN_SSH_CONFIRMED:-0}" == "1" ]]; then
        return
    fi

    local confirmation

    printf '\n'
    printf 'Before finalizing, confirm that a NEW SSH session works:\n'
    printf '  user: %s\n' "${ADMIN_USER}"
    printf '  port: %s\n' "${FINAL_SSH_PORT}"
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

verify_no_ufw() {
    if dpkg-query -W -f='${Status}\n' ufw 2>/dev/null \
        | grep -x 'install ok installed' >/dev/null; then
        die "UFW is still installed."
    fi

    if nft list ruleset | grep 'ufw-' >/dev/null; then
        die "UFW rules are still present."
    fi
}

prepare() {
    [[ ! -e "${FINALIZED_MARKER}" ]] \
        || die "Bootstrap is already finalized. Use '$0 status'."

    install_base_packages
    ensure_admin_user
    write_temporary_ssh_config
    apply_prepare_components

    local deploy_key_ready="no"

    if ensure_deploy_key; then
        deploy_key_ready="yes"
    fi

    printf '\n'
    printf '============================================================\n'
    printf 'PREPARE PHASE COMPLETE\n'
    printf '============================================================\n'
    printf 'SSH ports:             %s and %s\n' \
        "${BOOTSTRAP_SSH_PORT}" "${FINAL_SSH_PORT}"
    printf 'Administrative user:  %s\n' "${ADMIN_USER}"
    printf 'Root SSH login:        temporarily allowed\n'
    printf 'UFW:                   removed\n'
    printf 'Fail2Ban SSH ports:    %s and %s\n' \
        "${BOOTSTRAP_SSH_PORT}" "${FINAL_SSH_PORT}"
    printf 'Deploy key ready:      %s\n' "${deploy_key_ready}"
    printf '\n'
    printf 'Keep the original root session open.\n'
    printf 'Verify that a NEW root session still works on port %s.\n' \
        "${BOOTSTRAP_SSH_PORT}"
    printf 'Open a NEW SSH session as %s on port %s and test:\n' \
        "${ADMIN_USER}" "${FINAL_SSH_PORT}"
    printf '  sudo -i\n'
    printf '  whoami\n'
    printf '\n'
    printf 'After the deploy key is added and both access paths are tested, run:\n'
    printf '  ADMIN_USER=%q bash %q finalize\n' \
        "${ADMIN_USER}" "${REPO_DIR}/bootstrap/debian.sh"
}

finalize() {
    install_base_packages

    id "${ADMIN_USER}" >/dev/null 2>&1 \
        || die "Administrative user does not exist: ${ADMIN_USER}"

    id -nG "${ADMIN_USER}" \
        | tr ' ' '\n' \
        | grep -x sudo >/dev/null \
        || die "${ADMIN_USER} is not a member of sudo."

    verify_no_ufw

    nft list chain inet discrete_filter input \
        | grep -E "tcp dport ${BOOTSTRAP_SSH_PORT}([[:space:]]|$)" >/dev/null \
        || die "Bootstrap SSH port ${BOOTSTRAP_SSH_PORT} is not protected by the temporary firewall."

    nft list chain inet discrete_filter input \
        | grep -E "tcp dport ${FINAL_SSH_PORT}([[:space:]]|$)" >/dev/null \
        || die "Final SSH port ${FINAL_SSH_PORT} is not protected by the temporary firewall."

    ensure_deploy_key \
        || die "Register the printed deploy key in GitHub, then run finalize again."

    confirm_admin_ssh_test

    log "Applying final SSH configuration"
    finalize_ssh

    log "Applying final single-port firewall and Fail2Ban configuration"
    bash "${REPO_DIR}/scripts/apply-config.sh" nftables
    bash "${REPO_DIR}/scripts/apply-config.sh" fail2ban

    log "Running complete verification"
    bash "${REPO_DIR}/scripts/verify.sh" all

    if nft list chain inet discrete_filter input \
        | grep -E "tcp dport ${BOOTSTRAP_SSH_PORT}([[:space:]]|$)" >/dev/null; then
        die "Final firewall still exposes temporary SSH port ${BOOTSTRAP_SSH_PORT}."
    fi

    install -d -m 0755 "${STATE_DIR}"
    date --utc --iso-8601=seconds > "${FINALIZED_MARKER}"
    chmod 0644 "${FINALIZED_MARKER}"

    printf '\n'
    printf '============================================================\n'
    printf 'BOOTSTRAP FINALIZED\n'
    printf '============================================================\n'
    printf 'Administrative SSH:    %s@server:%s\n' \
        "${ADMIN_USER}" "${FINAL_SSH_PORT}"
    printf 'Direct root SSH:       disabled\n'
    printf 'Temporary SSH port:    closed\n'
    printf 'UFW:                   absent\n'
    printf 'Firewall:              inet discrete_filter\n'
    printf 'Fail2Ban:              active\n'
    printf 'Git origin:            %s\n' \
        "$(git -C "${REPO_DIR}" remote get-url origin)"
    printf '\n'
    printf 'Keep the current session open while performing two final tests:\n'
    printf '  1. A new %s SSH session succeeds on port %s.\n' \
        "${ADMIN_USER}" "${FINAL_SSH_PORT}"
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

    printf '\nGit working tree:\n'
    git -C "${REPO_DIR}" status --short
}

usage() {
    cat <<EOF
Usage:
  ADMIN_USER=serveradmin $0 prepare
  ADMIN_USER=serveradmin $0 finalize
  ADMIN_USER=serveradmin $0 status

prepare:
  Installs packages, creates the admin account, keeps root SSH on port
  ${BOOTSTRAP_SSH_PORT}, enables admin SSH on port ${FINAL_SSH_PORT}, removes
  UFW, activates the Git-managed nftables baseline with both SSH ports,
  configures Fail2Ban for both temporary SSH ports, and generates a read-only
  GitHub deploy key.

finalize:
  Requires tested root and admin SSH paths plus a registered deploy key.
  It removes temporary root SSH access and port ${BOOTSTRAP_SSH_PORT}, applies
  the final Git-managed configuration, and verifies the complete baseline.

status:
  Displays effective SSH, nftables, UFW, Fail2Ban, Git, and bootstrap state.
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

main "$@"
