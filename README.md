# Discrete Infrastructure

Infrastructure-as-code repository for deploying and maintaining public Discrete.cash nodes.

## Supported platforms

| Operating system | Status | Runbook |
|---|---|---|
| Debian 12 (bookworm) | Supported and clean-room validated | [`docs/bootstrap-from-zero.md`](docs/bootstrap-from-zero.md) |
| Ubuntu Server 24.04 LTS (noble) | Experimental until clean-room validation succeeds | [`docs/bootstrap-ubuntu-24.04-from-zero.md`](docs/bootstrap-ubuntu-24.04-from-zero.md) |

Start with the platform chooser:

```text
docs/bootstrap-platforms.md
```

Do not mix commands from different operating-system runbooks.

## Goals

- Reproducible server bootstrap from a clean supported installation
- Preserve Debian 12 as the validated reference implementation
- Add explicitly named platform entrypoints instead of ambiguous auto-detection
- Strict IPv4-only network baseline
- Minimal, measured hardening without pointless complexity
- Version-controlled nftables, SSH, sysctl, Fail2Ban, and deployment configuration
- No secrets committed to Git
- Git remains the source of truth

## Authoritative runbooks

Debian 12 keeps the original validated filenames and commands:

```text
docs/bootstrap-from-zero.md
bootstrap/run.sh
install.sh
```

Ubuntu Server 24.04 LTS uses separate filenames:

```text
docs/bootstrap-ubuntu-24.04-from-zero.md
bootstrap/run-ubuntu-24.04.sh
install-ubuntu-24.04.sh
```

Do not bypass or improvise around the selected documented sequence. When implementation and its
matching runbook disagree, correct the runbook first and then correct and retest the implementation.

## Validation

GitHub Actions validates Bash syntax, ShellCheck, OpenSSH, nftables, Fail2Ban, the IPv4-only
configuration contract, and platform-entrypoint separation on every push and pull request.

CI validation does not replace a complete clean-room test on a newly created VPS. Ubuntu 24.04
remains experimental until its runbook, reboot test, and external access audit all succeed.

## Repository layout

```text
bootstrap/   Platform entrypoints and administrative-account setup
configs/     Shared managed SSH, nftables, Fail2Ban, and sysctl configuration
scripts/     Shared deployment, migration, audit, and verification helpers
docs/        Platform selection, architecture, and operational runbooks
```

## Secrets

Real secrets must never be committed. Production secrets belong under:

```text
/etc/discrete/secrets/
```

Only documented templates and examples may live in this repository.

## Common final baseline

- Network stack: IPv4-only
- IPv6 addresses, routes, and listeners: none
- SSH: `22822/tcp` over IPv4
- Discrete P2P: `9330/tcp` over IPv4
- Discrete RPC HTTP: `9331/tcp` over IPv4
- Discrete RPC HTTPS: `9332/tcp` over IPv4
- Inbound UDP: none
- Firewall: nftables `table ip discrete_filter`, default-drop input policy
- Fail2Ban: nftables `table ip f2b-table`
- Time synchronization: client-only `systemd-timesyncd`
