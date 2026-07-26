#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_ROOT
readonly MANIFEST="${DISCRETE_MANIFEST:-${REPO_ROOT}/configs/manifest.tsv}"
readonly BACKUP_ROOT="${DISCRETE_BACKUP_ROOT:-/var/backups/discrete-infrastructure}"

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this script as root or with sudo." >&2
    exit 1
fi

if [[ ! -f "${MANIFEST}" ]]; then
    echo "Manifest not found: ${MANIFEST}" >&2
    exit 1
fi

readonly REQUESTED_COMPONENT="${1:-all}"
readonly TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"

mkdir -p "${BACKUP_DIR}"

applied_count=0

declare -a component_order=()
declare -A component_seen=()

while IFS=$'\t' read -r component _source _target _mode _validate _reload _verify; do
    [[ -z "${component}" ]] && continue
    [[ "${component}" == \#* ]] && continue

    if [[ "${REQUESTED_COMPONENT}" != "all" \
       && "${REQUESTED_COMPONENT}" != "${component}" ]]; then
        continue
    fi

    if [[ -z "${component_seen[${component}]:-}" ]]; then
        component_order+=("${component}")
        component_seen["${component}"]=1
    fi
done < "${MANIFEST}"

if [[ ${#component_order[@]} -eq 0 ]]; then
    echo "No matching component found: ${REQUESTED_COMPONENT}" >&2
    exit 1
fi

apply_component_group() {
    local requested="$1"
    local component source target mode validate_cmd reload_cmd verify_cmd
    local expected_reload=""
    local expected_verify=""
    local source_path backup_path
    local index

    local -a sources=()
    local -a targets=()
    local -a modes=()
    local -a validate_cmds=()
    local -a source_paths=()
    local -a backup_paths=()
    local -a target_existed=()
    local -A target_seen=()
    local -A validation_seen=()
    local -a unique_validation_cmds=()

    while IFS=$'\t' read -r component source target mode validate_cmd reload_cmd verify_cmd; do
        [[ -z "${component}" ]] && continue
        [[ "${component}" == \#* ]] && continue
        [[ "${component}" == "${requested}" ]] || continue

        if [[ -n "${target_seen[${target}]:-}" ]]; then
            echo "Duplicate target in component ${requested}: ${target}" >&2
            return 1
        fi
        target_seen["${target}"]=1

        if [[ -z "${expected_reload}" ]]; then
            expected_reload="${reload_cmd}"
        elif [[ "${reload_cmd}" != "${expected_reload}" ]]; then
            echo "Component ${requested} has inconsistent reload commands." >&2
            return 1
        fi

        if [[ -z "${expected_verify}" ]]; then
            expected_verify="${verify_cmd}"
        elif [[ "${verify_cmd}" != "${expected_verify}" ]]; then
            echo "Component ${requested} has inconsistent verification commands." >&2
            return 1
        fi

        source_path="${REPO_ROOT}/${source}"
        if [[ ! -f "${source_path}" ]]; then
            echo "Source file missing: ${source_path}" >&2
            return 1
        fi

        sources+=("${source}")
        targets+=("${target}")
        modes+=("${mode}")
        validate_cmds+=("${validate_cmd}")
        source_paths+=("${source_path}")
    done < "${MANIFEST}"

    if [[ ${#targets[@]} -eq 0 ]]; then
        echo "No manifest rows found for component: ${requested}" >&2
        return 1
    fi

    if [[ -z "${expected_reload}" || -z "${expected_verify}" ]]; then
        echo "Component ${requested} has an empty reload or verification command." >&2
        return 1
    fi

    for validate_cmd in "${validate_cmds[@]}"; do
        if [[ -z "${validate_cmd}" ]]; then
            echo "Component ${requested} has an empty validation command." >&2
            return 1
        fi

        if [[ -z "${validation_seen[${validate_cmd}]:-}" ]]; then
            unique_validation_cmds+=("${validate_cmd}")
            validation_seen["${validate_cmd}"]=1
        fi
    done

    echo
    echo "Applying component: ${requested}"

    for index in "${!targets[@]}"; do
        echo "  ${source_paths[${index}]}"
        echo "  -> ${targets[${index}]}"

        backup_path="${BACKUP_DIR}${targets[${index}]}"
        backup_paths+=("${backup_path}")

        if [[ -e "${targets[${index}]}" ]]; then
            target_existed+=(1)
            mkdir -p "$(dirname -- "${backup_path}")"
            cp -a -- "${targets[${index}]}" "${backup_path}"
        else
            target_existed+=(0)
        fi
    done

    rollback_component() {
        local rollback_index

        echo "Rolling back component: ${requested}" >&2

        for rollback_index in "${!targets[@]}"; do
            if [[ ${target_existed[${rollback_index}]} -eq 1 ]]; then
                mkdir -p "$(dirname -- "${targets[${rollback_index}]}")"
                cp -a -- \
                    "${backup_paths[${rollback_index}]}" \
                    "${targets[${rollback_index}]}"
            else
                rm -f -- "${targets[${rollback_index}]}"
            fi
        done
    }

    for index in "${!targets[@]}"; do
        mkdir -p "$(dirname -- "${targets[${index}]}")"

        if ! install -m "${modes[${index}]}" -- \
            "${source_paths[${index}]}" \
            "${targets[${index}]}"; then

            echo "Install failed for component ${requested}: ${targets[${index}]}" >&2
            rollback_component
            return 1
        fi
    done

    for validate_cmd in "${unique_validation_cmds[@]}"; do
        if ! bash -c "${validate_cmd}"; then
            echo "Validation failed: ${validate_cmd}" >&2
            rollback_component
            return 1
        fi
    done

    if ! bash -c "${expected_reload}"; then
        echo "Reload failed: ${expected_reload}" >&2
        rollback_component
        bash -c "${expected_reload}" || true
        return 1
    fi

    if ! bash -c "${expected_verify}" >/dev/null; then
        echo "Verification failed: ${expected_verify}" >&2
        rollback_component
        bash -c "${expected_reload}" || true
        return 1
    fi

    echo "Component applied successfully: ${requested}"
    applied_count=$((applied_count + 1))
}

for component in "${component_order[@]}"; do
    apply_component_group "${component}"
done

echo
echo "Applied components: ${applied_count}"
echo "Backups: ${BACKUP_DIR}"
