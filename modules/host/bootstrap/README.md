# Host bootstrap implementation

Canonical bootstrap implementation for Debian 12 and Ubuntu Server 24.04 LTS.

Public operator commands remain at the repository-root `bootstrap/` paths. Those files are stable
compatibility entrypoints and delegate here. Platform-specific code must remain separate; do not
add ambiguous operating-system auto-detection.

The matching runbooks are under [`docs/host/`](../../../docs/host/).
