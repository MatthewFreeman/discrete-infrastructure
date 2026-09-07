# Discrete Pay dedicated-host profile

Opt-in Debian 12 overlay; default node bootstrap and other hosts are unchanged.
Deploys no payment application.

Follow the canonical prepare/finalize runbook first. Install a dedicated
serveradmin key (0700 SSH directory, 0600 authorized_keys); prove a fresh key-only
login on 22822 and password-authenticated sudo. Retain that connection.
From its root shell, at a clean pinned checkout:

    DISCRETE_MANIFEST=profiles/discrete-pay/manifest.tsv bash scripts/apply-config.sh all
    python3 profiles/discrete-pay/verify.py all

Then test a NEW key-only login, root/password SSH refusal and external closed
TCP/22 and internal ports. Reboot; repeat fresh key/sudo and profile checks.

Only inbound IPv4 TCP 22822, 80, 443 is allowed. HTTP is reserved for ACME and
HTTPS redirect; HTTPS for the Pay edge. Neither listener starts here. Node
P2P/RPC 9330-9332, walletd 9340 and internal app APIs must not be public.
Outbound peer connections remain allowed. IPv6, inbound UDP, root/password SSH,
keyboard-interactive authentication and SSH forwarding are disabled.

Keys, passphrases, sudo and rotated root recovery passwords belong in the
owner's Bitwarden, never Git. Keep a protected local recovery copy until saved.

## Updates and recovery

Use THIS manifest for later SSH/firewall updates. Do not run default install.sh
or baseline verify.sh all on a profiled host: those intentionally require
password SSH and public node RPC ingress. Profile verification reuses only the
unchanged IPv4, Fail2Ban and timesync checks.

The component installer backs up targets and rolls back a component on failed
validation/reload/verification. Keep the tested session open. Validate restored
SSH with sshd -t before reload. Restore firewall using apply-nftables.sh --apply,
never flush all tables. Default-profile restoration reopens password SSH and
RPC ingress; it is emergency recovery, not the intended final state. Retain
provider console access.

A host-policy PASS does not prove HTTPS, alert delivery, backup/restore or a
deployed payment service. This profile is for serveradmin on a dedicated host.
