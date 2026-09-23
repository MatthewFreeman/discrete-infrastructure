# Discrete Infrastructure

Infrastructure, deployment automation, and operational runbooks for the Discrete ecosystem.

This repository is public. Cloning and pulling over HTTPS require no GitHub account, personal
access token, deploy key, username, or password.

Start with the [getting-started guide](docs/getting-started.md). Current implementation and
validation status is tracked in one place: [component status](docs/component-status.md).

## Available now

The host module prepares a clean supported VPS for later Discrete services.

| Operating system | Status | Runbook |
|---|---|---|
| Debian 12 (bookworm) | Supported and clean-room validated | [`docs/host/bootstrap-from-zero.md`](docs/host/bootstrap-from-zero.md) |
| Ubuntu Server 24.04 LTS (noble) | Supported and clean-room validated | [`docs/host/bootstrap-ubuntu-24.04-from-zero.md`](docs/host/bootstrap-ubuntu-24.04-from-zero.md) |

The short operator commands remain stable even though canonical implementation now lives under
`modules/host/`:

```text
bootstrap/run.sh
bootstrap/run-ubuntu-24.04.sh
install.sh
install-ubuntu-24.04.sh
scripts/audit-ports.sh
```

Do not mix commands from different operating-system runbooks.

## Node work

The official Universal Linux amd64 asset is the accepted default for Debian 12 and Ubuntu 24.04.
The measured decision and reproducible evidence remain at their stable published paths:

- [ADR 0001](docs/decisions/0001-use-official-universal-linux-amd64.md)
- [Discrete v0.9.5 benchmark suite](docs/benchmarks/discrete-v0.9.5/README.md)

Node deployment, lifecycle automation, and default-on updates are separate planned work. Benchmark
qualification does not mean that a production node installer already exists.

## Repository layout

```text
modules/host/   Canonical host bootstrap, configuration, installers, and verification
modules/node/   Node deployment contract and future implementation entrypoint
docs/host/      Host platform selection and clean-room runbooks
docs/node/      Node documentation index and lifecycle plan
docs/decisions/ Repository-wide architecture decisions
docs/benchmarks/Published measurement evidence at stable URLs
bootstrap/      Stable compatibility entrypoints for existing operator commands
scripts/        Stable compatibility entrypoints and installed-service paths
```

Root compatibility entrypoints contain no independent implementation. New logic belongs in the
matching module.

## Design rules

- Preserve Debian 12 and Ubuntu 24.04 as separately validated host paths.
- Keep the network baseline strictly IPv4-only.
- Prefer minimal, measured hardening over copied tuning folklore.
- Keep application source code in its own repository; this repository owns deployment and
  operations.
- Add a module, profile, or shared abstraction only when real implementation requires it.
- Never commit secrets or production credentials.
- Git remains the source of truth.

## Validation

GitHub Actions validates Bash syntax, ShellCheck, OpenSSH, nftables, Fail2Ban, the IPv4-only
configuration contract, platform separation, compatibility entrypoints, and repository layout.

CI does not replace clean-room testing on newly created VPS instances. A structural change must not
be described as behaviorally validated until the documented Debian and Ubuntu operator sequences
have been exercised again.

## Secrets

Real secrets belong outside Git under:

```text
/etc/discrete/secrets/
```

Only documented templates and examples may live in this repository.

## Current host baseline

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
