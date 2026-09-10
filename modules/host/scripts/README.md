# Host scripts

Canonical operational scripts for applying configuration, enforcing IPv4-only state, auditing
ports, validating the host, and maintaining Fail2Ban and nftables.

Scripts must use strict error handling, produce useful diagnostics, avoid hidden state, and remain
safe to repeat where practical. Root-level `scripts/` files are compatibility entrypoints only.
