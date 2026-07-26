# Choose the VPS operating system

Use exactly one runbook and its matching commands. Do not mix Debian and Ubuntu entrypoints on the same server.

| Operating system | Support status | Clean-server runbook | Bootstrap entrypoint | Future-update installer |
|---|---|---|---|---|
| Debian 12 (bookworm) | Supported and clean-room validated | [`bootstrap-from-zero.md`](bootstrap-from-zero.md) | `bootstrap/run.sh` | `install.sh` |
| Ubuntu Server 24.04 LTS (noble) | Experimental until clean-room validation succeeds | [`bootstrap-ubuntu-24.04-from-zero.md`](bootstrap-ubuntu-24.04-from-zero.md) | `bootstrap/run-ubuntu-24.04.sh` | `install-ubuntu-24.04.sh` |

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

Do not mark Ubuntu as supported until the complete runbook has succeeded on a newly created Ubuntu Server 24.04 LTS VPS and the final external access tests have been recorded.
