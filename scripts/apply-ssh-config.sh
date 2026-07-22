#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly SOURCE_FILE="${REPO_ROOT}/configs/ssh/00-discrete.conf"
readonly TARGET_FILE="/etc/ssh/sshd_config.d/00-discrete.conf"
readonly BACKUP_FILE="${TARGET_FILE}.bak"

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this script as root or with sudo." >&2
  exit 1
fi

if [[ ! -f "${SOURCE_FILE}" ]]; then
  echo "Missing source file: ${SOURCE_FILE}" >&2
  exit 1
fi

install -d -m 0755 /etc/ssh/sshd_config.d

if [[ -f "${TARGET_FILE}" ]]; then
  cp -a -- "${TARGET_FILE}" "${BACKUP_FILE}"
else
  rm -f -- "${BACKUP_FILE}"
fi

rollback() {
  echo "SSH configuration validation failed. Rolling back." >&2
  if [[ -f "${BACKUP_FILE}" ]]; then
    mv -f -- "${BACKUP_FILE}" "${TARGET_FILE}"
  else
    rm -f -- "${TARGET_FILE}"
  fi
  sshd -t || true
}

trap rollback ERR

install -m 0644 -- "${SOURCE_FILE}" "${TARGET_FILE}"
sshd -t
systemctl reload ssh

trap - ERR
rm -f -- "${BACKUP_FILE}"

echo "SSH configuration applied successfully."
sshd -T | grep -E '^(port|logingracetime|maxauthtries|x11forwarding|allowagentforwarding|passwordauthentication|permitrootlogin) '
