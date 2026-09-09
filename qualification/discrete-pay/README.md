# No-domain Discrete Pay qualification (not production deployment)

The native load helper accepts target10000 or100000. Opt-in
`DISCRETE_PAY_NATIVE_LOAD_BASE=qualified10000` starts from a **copy** of the
SHA-bound previously qualified10000 fixture, with distinct merchant request keys.
It preserves the default1001-based test, records progress separately as RUNNING,
and never promotes incomplete prefill to PASS. Native prefill checks each returned
index once; ambiguous allocations are not blindly retried. Run it in its own
loopback/resource/time-limited unit and restore any paused private test stack on
both successful and failed completion. This is not proof of sustained load.

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

## Pinned internal Linux candidate — 2026-09-09

`bundle-candidate.py` assembles explicit immutable Pay939d8fe source/runtime
archives with clean FreemanCore8703c16 CI binaries and Node24.18.1. Input hashes
are mandatory. This is an internal candidate, not an installer, release tag,
service activation, or proof of public-network payment compatibility.
No wallet, database, host configuration, token or test-difficulty daemon enters
the bundle. `test_bundle.py` checks archive admission and deterministic envelope.

Qualified archiveSHA256:
`bc88d9fc37d3d0eda727e964abf57bd63a10c76533a39d349dccd7f5e654f40a`.
ManifestSHA256:
`680e736b99800d1d3811896d88ffc9999d16bbd2f6db4844d737f6f3937b441b`.
74 listed files rehashed after extracting the actual archive. Two archive
envelopes matched (not a compiler reproducibility claim). Compiled gateway
creation/replay/auth and worker RPC-failure/restart tests passed from the extracted
package using its bundled Node binary. Operator lifecycle:7PASS/1platformskip.
Version readback matched both bundled Core binaries. Secret-free validation
evidenceSHA256:f2c2b2ca0e8b418bd942fc285fadbe0ab6cd48c642f0cf841bfdd3f2ebf526db.
Identical archive retained off-host. No persistent service changed by these tests.

The clean compatibility mode `isolated-freeman-ci-8703c16` passed empty-wallet
tracking attestation, spending-wallet/unregistered-wallet refusal, empty view-only
send/prepare refusal and mode after restart. This does not prove a registered
public-network payment. Native capacity/lifecycle fixtures remain a separate gate.
