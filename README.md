# Discrete Infrastructure

Infrastructure-as-code repository for deploying and maintaining public Discrete.cash nodes on Debian 12.

## Goals

- Reproducible server bootstrap from a clean Debian 12 installation
- Strict IPv4-only network baseline
- Minimal, measured hardening without pointless complexity
- Version-controlled nftables, SSH, sysctl, Fail2Ban, and deployment configuration
- No secrets committed to Git
- Git remains the source of truth

## Authoritative runbook

All clean-server deployment and recovery work follows:

```text
docs/bootstrap-from-zero.md
```

Do not bypass or improvise around the documented sequence. When implementation and the
runbook disagree, correct the runbook first and then correct and retest the implementation.

## Repository layout

```text
bootstrap/   Bootstrap entrypoint and administrative-account setup
configs/     Managed SSH, nftables, Fail2Ban, and sysctl configuration
scripts/     Deployment, migration, audit, and verification helpers
docs/        Architecture and operational runbooks
```

## Secrets

Real secrets must never be committed. Production secrets belong under:

```text
/etc/discrete/secrets/
```

Only documented templates and examples may live in this repository.

## Current baseline

- OS: Debian 12 (bookworm)
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
