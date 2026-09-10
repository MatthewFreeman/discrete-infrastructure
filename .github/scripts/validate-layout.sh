#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

required_paths=(
    modules/host/README.md
    modules/host/install.sh
    modules/host/install-ubuntu-24.04.sh
    modules/host/bootstrap/run.sh
    modules/host/bootstrap/run-ubuntu-24.04.sh
    modules/host/bootstrap/debian-ipv4.sh
    modules/host/bootstrap/ubuntu-24.04-ipv4.sh
    modules/host/configs/manifest.tsv
    modules/host/scripts/apply-config.sh
    modules/host/scripts/audit-ports.sh
    modules/host/scripts/verify.sh
    modules/node/README.md
    docs/getting-started.md
    docs/component-status.md
    docs/roadmap.md
    docs/host/bootstrap-from-zero.md
    docs/host/bootstrap-ubuntu-24.04-from-zero.md
    docs/node/README.md
    docs/decisions/0001-use-official-universal-linux-amd64.md
    docs/benchmarks/discrete-v0.9.5/README.md
)

for path in "${required_paths[@]}"; do
    [[ -e "${path}" ]] || fail "Required canonical path is missing: ${path}"
done

[[ ! -e configs ]] || fail 'Top-level configs/ must not contain canonical implementation.'

declare -A wrappers=(
    [install.sh]='modules/host/install.sh'
    [install-ubuntu-24.04.sh]='modules/host/install-ubuntu-24.04.sh'
    [bootstrap/create-admin.sh]='modules/host/bootstrap/create-admin.sh'
    [bootstrap/debian-ipv4.sh]='modules/host/bootstrap/debian-ipv4.sh'
    [bootstrap/install-fail2ban.sh]='modules/host/bootstrap/install-fail2ban.sh'
    [bootstrap/install-ubuntu-ipv4-reassertion.sh]='modules/host/bootstrap/install-ubuntu-ipv4-reassertion.sh'
    [bootstrap/run.sh]='modules/host/bootstrap/run.sh'
    [bootstrap/run-ubuntu-24.04.sh]='modules/host/bootstrap/run-ubuntu-24.04.sh'
    [bootstrap/ubuntu-24.04-ipv4.sh]='modules/host/bootstrap/ubuntu-24.04-ipv4.sh'
    [scripts/apply-config.sh]='modules/host/scripts/apply-config.sh'
    [scripts/apply-nftables.sh]='modules/host/scripts/apply-nftables.sh'
    [scripts/audit-ports.sh]='modules/host/scripts/audit-ports.sh'
    [scripts/check-ipv6-listeners.sh]='modules/host/scripts/check-ipv6-listeners.sh'
    [scripts/configure-ipv4-only.sh]='modules/host/scripts/configure-ipv4-only.sh'
    [scripts/configure-time-sync.sh]='modules/host/scripts/configure-time-sync.sh'
    [scripts/restart-fail2ban.sh]='modules/host/scripts/restart-fail2ban.sh'
    [scripts/verify.sh]='modules/host/scripts/verify.sh'
)

for wrapper in "${!wrappers[@]}"; do
    canonical="${wrappers[${wrapper}]}"
    [[ -f "${wrapper}" ]] || fail "Compatibility entrypoint is missing: ${wrapper}"
    [[ -x "${wrapper}" ]] || fail "Compatibility entrypoint is not executable: ${wrapper}"
    grep -F "${canonical}" "${wrapper}" >/dev/null \
        || fail "Compatibility entrypoint does not delegate to ${canonical}: ${wrapper}"

    line_count="$(wc -l < "${wrapper}")"
    (( line_count <= 20 )) \
        || fail "Compatibility entrypoint contains too much logic: ${wrapper}"
done

declare -A moved_docs=(
    [docs/bootstrap-from-zero.md]='host/bootstrap-from-zero.md'
    [docs/bootstrap-platforms.md]='host/bootstrap-platforms.md'
    [docs/bootstrap-ubuntu-24.04-from-zero.md]='host/bootstrap-ubuntu-24.04-from-zero.md'
    [nftables/README.md]='docs/host/components/nftables.md'
    [ssh/README.md]='docs/host/components/ssh.md'
    [sysctl/README.md]='docs/host/components/sysctl.md'
    [systemd/README.md]='docs/host/components/systemd.md'
)

for stub in "${!moved_docs[@]}"; do
    target="${moved_docs[${stub}]}"
    [[ -f "${stub}" ]] || fail "Compatibility documentation stub is missing: ${stub}"
    grep -F "${target}" "${stub}" >/dev/null \
        || fail "Compatibility documentation stub does not link to ${target}: ${stub}"
done

if git grep -n -E '\$\{REPO_DIR\}/(bootstrap|configs|scripts)' -- modules/host; then
    fail 'Canonical host implementation still addresses module files through REPO_DIR.'
fi

if git grep -n -E 'docs/node/(benchmarks|decisions)' -- .; then
    fail 'Published benchmark or ADR paths were replaced instead of preserved.'
fi

bash -c 'source bootstrap/run.sh; declare -F apt-get >/dev/null'
bash -c 'source bootstrap/debian-ipv4.sh; declare -F verify_repository_preflight >/dev/null'
bash -c 'source bootstrap/ubuntu-24.04-ipv4.sh; declare -F check_platform >/dev/null'

printf 'Unexpected legacy references: 0\n'
printf 'Approved compatibility wrappers: %s\n' "${#wrappers[@]}"
printf 'Repository layout audit: PASS\n'
