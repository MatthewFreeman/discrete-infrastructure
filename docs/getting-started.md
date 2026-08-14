# Getting started

Choose the task you are actually performing.

## Prepare a supported host

Start with the [host platform chooser](host/bootstrap-platforms.md). Debian 12 and Ubuntu Server
24.04 LTS have separate, clean-room-validated runbooks. Do not mix their commands.

## Install a Discrete node

Production node installation automation is not available yet. The accepted release artifact and
benchmark evidence are documented in the [node index](node/README.md), but qualification evidence
is not an installer.

## Bring an independently configured VPS

A future node preflight will assess supported operating-system, architecture, systemd, resource,
port, time-sync, and service-conflict requirements without mutating the host. Until that exists,
the supported path is the validated host bootstrap.

Always check [component status](component-status.md) before following planned documentation.
