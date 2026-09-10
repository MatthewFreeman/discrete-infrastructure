# Host module

Canonical implementation for preparing and maintaining supported Discrete infrastructure hosts.

Supported platforms:

- Debian 12 (bookworm)
- Ubuntu Server 24.04 LTS (noble)

This module owns host bootstrap, SSH, nftables, Fail2Ban, IPv4-only policy, time synchronization,
configuration deployment, and host verification. It does not install the Discrete node.

Operator-facing commands remain available through the stable root entrypoints documented in
[`docs/host/`](../../docs/host/). Do not add implementation logic to those compatibility wrappers.

```text
bootstrap/  Canonical platform bootstrap implementation
configs/    Managed host configuration and deployment manifest
scripts/    Canonical apply, audit, migration, and verification helpers
```
