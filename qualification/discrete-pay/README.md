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
After that test passes, `reboot-test.py prepare <exact-handoff>` installs the
exported exact units only if no conflicting system units exist, rechecks payment
and TLS, and enables one temporary target. Reboot the explicitly assigned host,
then run `reboot-test.py verify` and `reboot-test.py cleanup`. Cleanup checks file
hashes, removes only its own test units and retains all fixture and backup data.
The reboot qualification does not turn these test launchers into production units.

The HTTPS receiver uses the public test certificate with explicit CA trust and
hostname verification. No purchased domain, DNS mutation, public RPC, real funds,
existing wallet, SSH change or alteration of Buyback is involved.

Status on 2026-09-07: native Linux, the complete systemd/TLS/crash/retry/restore
scenario and actual reboot passed on the isolated Debian host. Temporary units
were removed afterwards. `regression.sh` then passed typecheck, 306 tests/29 files
and compiled gateway/worker smoke. Only the exact run evidence establishes this
scope; it is not a production or public-network release qualification.

The first service attempt exposed the Nginx default FastCGI temporary path outside
the allowed directory. The second exposed retained failed transient units after
intentional shutdown. Explicit in-fixture temp paths, intentional-stop handling
and guarded transient cleanup corrected these fixture issues. The third complete
attempt passed; failed evidence was retained. Pay application code was unchanged.

Secret-free results are `service-evidence.json` and `reboot-evidence.json` under
the qualification root. The Pay repository's dated no-domain qualification report
records exact native source/binary/evidence hashes and detailed remaining gates.
Real external alert routing, public certificate issuance and ordinary-wallet UI
payment remain separate evidence boundaries even after these fixtures pass.
