# No-domain Discrete Pay qualification (not production deployment)

Only for an explicitly assigned, isolated Debian 12 amd64 host. The Pay host
firewall/SSH profile is a prerequisite and is not changed by this fixture.
Use a fresh unprivileged `payqual` account and `/opt/discrete-pay-qualification`.
The preparation script creates them once; it must not be blindly rerun.

Source archives are exported locally from immutable approved Pay/Core commits,
uploaded through pinned SSH, and checked against locally generated SHA256SUMS.
No GitHub token is needed on the VPS. `build.sh` installs pinned Pay dependencies
and compiles the existing opt-in Core test fixture. Native source has historical
CRLF; normalize only the two fixture files before applying the exact patches.
`manifest.py` compares every archived source with the extracted build input and
checks the two exact changes before recording executable hashes. These binaries
use testnet difficulty 1 and are **not** public-network release artifacts.

Run the Pay native harness as `payqual` with `DISCRETE_PAY_NATIVE_TEST=isolated-testnet`,
`DISCRETE_PAY_NATIVE_REORG=true`, `DISCRETE_PAY_SERVICE_HANDOFF=true`. Preserve
its secret-free evidence separately from its private wallet/configuration files.
The harness must pass and stop its children before `service-test.py` is invoked
with the exact resulting `service-handoff.json` path.

The service test uses separate transient systemd units, unprivileged identities,
strict filesystem protections and kernel loopback-only ingress/egress. It tests
existing-payment replay, wallet outage/recovery reporting, another disposable
native payment, forced worker death/restart, signed HTTPS retry, online SQLite
backup and cold full-state restore. The pre-restore original is retained under
a sibling `.pre-restore` path. Its finally block stops only its exact named units.
Transient units do not establish production boot enablement or deployment.

The HTTPS receiver uses the public test certificate with explicit CA trust and
hostname verification. No purchased domain, DNS mutation, public RPC, real funds,
existing wallet, SSH change or alteration of Buyback is involved.

Status: implementation under live qualification; only a PASS evidence file from
the exact installed scripts proves completion. Failed stages must be recorded.
Real external alert routing, public certificate issuance and ordinary-wallet UI
payment remain separate evidence boundaries even after these fixtures pass.
