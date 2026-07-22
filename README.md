# Discrete Infrastructure

Infrastructure-as-code repository for deploying and maintaining public Discrete.cash nodes on Debian 12.

## Goals

- Reproducible server bootstrap from a clean Debian 12 installation
- Minimal, measured hardening without pointless complexity
- Version-controlled nftables, SSH, sysctl, systemd, and deployment configuration
- No secrets committed to Git
- Git remains the source of truth

## Repository layout

```text
bootstrap/   Initial host preparation and package installation
nftables/    Firewall rules and deployment helpers
ssh/         SSH server hardening configuration
sysctl/      Kernel and network tuning
systemd/     Service units and overrides
scripts/     Operational and maintenance scripts
docs/        Architecture, runbooks, and recovery procedures
```

## Secrets

Real secrets must never be committed. Production secrets belong under:

```text
/etc/discrete/secrets/
```

Only documented templates and examples may live in this repository.

## Current baseline

- OS: Debian 12 (bookworm)
- SSH port: `22822/tcp`
- Discrete P2P: `9330/tcp`
- Discrete RPC HTTP: `9331/tcp`
- Discrete RPC HTTPS: `9332/tcp`
- Firewall: nftables with default-drop input policy

## Status

Initial repository structure is being established. SSH hardening is the next infrastructure task.
