#!/usr/bin/env bash
set -Eeuo pipefail

umask 027

readonly ADMIN_USER="${ADMIN_USER:-serveradmin}"

die() {
    echo "ERROR: $*" >&2
    exit 1
}

if [[ ${EUID} -ne 0 ]]; then
    die "Run this script as root or with sudo."
fi

if [[ ! "${ADMIN_USER}" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
    die "Invalid administrative username: ${ADMIN_USER}"
fi

if [[ "${ADMIN_USER}" == "root" ]]; then
    die "ADMIN_USER cannot be root."
fi

if ! command -v sudo >/dev/null 2>&1; then
    echo "Installing sudo..."
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y sudo
fi

if ! command -v adduser >/dev/null 2>&1; then
    die "The adduser command is unavailable."
fi

user_created=0

if id -u "${ADMIN_USER}" >/dev/null 2>&1; then
    echo "Administrative user already exists: ${ADMIN_USER}"
else
    echo "Creating administrative user: ${ADMIN_USER}"

    adduser \
        --disabled-password \
        --gecos "" \
        "${ADMIN_USER}"

    user_created=1
fi

echo "Adding ${ADMIN_USER} to the sudo group..."
usermod -aG sudo "${ADMIN_USER}"

password_state="$(passwd -S "${ADMIN_USER}" | awk '{print $2}')"

if [[ ${user_created} -eq 1 \
   || "${password_state}" == "L" \
   || "${password_state}" == "NP" \
   || "${RESET_ADMIN_PASSWORD:-0}" == "1" ]]; then

    echo
    echo "Set a strong password for ${ADMIN_USER}."
    passwd "${ADMIN_USER}"
fi

echo
echo "Validating sudo configuration..."
visudo -c >/dev/null

echo
echo "Administrative account:"
id "${ADMIN_USER}"

echo
echo "Sudo permissions:"
sudo -l -U "${ADMIN_USER}"

echo
echo "Administrative user is ready: ${ADMIN_USER}"
echo
echo "Root SSH access has NOT been changed."
echo "Test a separate SSH login as ${ADMIN_USER} before disabling root SSH."
