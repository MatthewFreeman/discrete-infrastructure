# Choose the VPS operating system

Use exactly one runbook and its matching commands. Do not mix Debian and Ubuntu entrypoints on the same server.

| Operating system | Support status | Clean-server runbook | Bootstrap entrypoint | Future-update installer |
|---|---|---|---|---|
| Debian 12 (bookworm) | Supported and clean-room validated | [`bootstrap-from-zero.md`](bootstrap-from-zero.md) | `bootstrap/run.sh` | `install.sh` |
| Ubuntu Server 24.04 LTS (noble) | Supported and clean-room validated | [`bootstrap-ubuntu-24.04-from-zero.md`](bootstrap-ubuntu-24.04-from-zero.md) | `bootstrap/run-ubuntu-24.04.sh` | `install-ubuntu-24.04.sh` |

## Debian 12

Debian 12 remains the reference implementation. Its existing filenames and documented commands are intentionally unchanged.

Start here:

```text
docs/bootstrap-from-zero.md
```

## Ubuntu Server 24.04 LTS

Ubuntu has separate, explicitly named entrypoints. The implementation reuses the common verified firewall, SSH policy, Fail2Ban, deployment, rollback, audit, and verification logic, while handling Ubuntu-specific platform validation, OpenSSH socket activation, and initial cloud-user SSH keys separately.

Start here:

```text
docs/bootstrap-ubuntu-24.04-from-zero.md
```

Ubuntu 24.04 is supported and clean-room validated. The recorded fresh-VPS run used Path A and completed reboot plus external access validation. Both access paths converge on the same final infrastructure contract; CI enforces the Path B-specific cloud-user, root-lock, key-transfer, and temporary-access behavior.
