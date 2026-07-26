#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_ROOT
readonly MANIFEST="${REPO_ROOT}/configs/manifest.tsv"
readonly BACKUP_ROOT="/var/backups/discrete-infrastructure"

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this script as root or with sudo." >&2
    exit 1
fi

if [[ ! -f "${MANIFEST}" ]]; then
    echo "Manifest not found: ${MANIFEST}" >&2
    exit 1
fi

requested_component="${1:-all}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT}/${timestamp}"

mkdir -p "${backup_dir}"

applied_count=0

apply_component() {
    local component="$1"
    local source="$2"
    local target="$3"
    local mode="$4"
    local validate_cmd="$5"
    local reload_cmd="$6"
    local verify_cmd="$7"

    local source_path="${REPO_ROOT}/${source}"
    local backup_path="${backup_dir}${target}"
    local target_existed=0

    if [[ ! -f "${source_path}" ]]; then
        echo "Source file missing: ${source_path}" >&2
        return 1
    fi

    echo
    echo "Applying component: ${component}"
    echo "  ${source_path}"
    echo "  -> ${target}"

    if [[ -e "${target}" ]]; then
        target_existed=1
        mkdir -p "$(dirname -- "${backup_path}")"
        cp -a -- "${target}" "${backup_path}"
    fi

    rollback() {
        echo "Rolling back component: ${component}" >&2

        if [[ ${target_existed} -eq 1 ]]; then
            cp -a -- "${backup_path}" "${target}"
        else
            rm -f -- "${target}"
        fi
    }

    mkdir -p "$(dirname -- "${target}")"
    install -m "${mode}" -- "${source_path}" "${target}"

    if ! bash -c "${validate_cmd}"; then
        echo "Validation failed: ${validate_cmd}" >&2
        rollback
        return 1
    fi

    if ! bash -c "${reload_cmd}"; then
        echo "Reload failed: ${reload_cmd}" >&2
        rollback
        bash -c "${reload_cmd}" || true
        return 1
    fi

    if ! bash -c "${verify_cmd}" >/dev/null; then
        echo "Verification failed: ${verify_cmd}" >&2
        rollback
        bash -c "${reload_cmd}" || true
        return 1
    fi

    echo "Component applied successfully: ${component}"
    applied_count=$((applied_count + 1))
}

while IFS=$'\t' read -r component source target mode validate_cmd reload_cmd verify_cmd; do
    [[ -z "${component}" ]] && continue
    [[ "${component}" == \#* ]] && continue

    if [[ "${requested_component}" != "all" && "${requested_component}" != "${component}" ]]; then
        continue
    fi

    apply_component \
        "${component}" \
        "${source}" \
        "${target}" \
        "${mode}" \
        "${validate_cmd}" \
        "${reload_cmd}" \
        "${verify_cmd}"
done < "${MANIFEST}"

if [[ ${applied_count} -eq 0 ]]; then
    echo "No matching component found: ${requested_component}" >&2
    exit 1
fi

echo
echo "Applied components: ${applied_count}"
echo "Backups: ${backup_dir}"
