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
or Pay136f63d archives with clean FreemanCore8703c16 CI binaries and Node24.18.1. Input hashes
are mandatory. This is an internal candidate, not an installer, release tag,
service activation, or proof of public-network payment compatibility.
No live wallet, database, host configuration, operational token or test-difficulty
daemon enters the bundle. The Git source archive retains public disposable test
material, including its TLS fixture. `test_bundle.py` checks archive admission
and deterministic envelope.

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

The newer Pay136f63d package includes merchant credentials, webhook provisioning
and durable webhook failure reporting. ArchiveSHA256:
`9f2c8462e2f2aa7291f50e07ad4152f70757146e5759710958b20cc55de87d7c`.
ManifestSHA256:
`a2d5f970819b09ff99e653aaa1efdd82a370f80c3d39341889102c6c48b9d54c`.
All77 manifest entries verified from the extracted archive. Bundled Node ran
compiled gateway/worker smokes, actual worker process HTTPS503/restart/204/dead
letter reporting, merchant credentials7PASS/1platformskip and webhook operator
7PASS/1platformskip. ValidationSHA256:
`10974959d9db6e14b3d66a7be2a57bd8dfc283c330e7baececeb2249eca869f9`.
Exact archive retained off-host, older939d8fe artifact preserved. No persistent
service activation or native/public-network payment is claimed by these smokes.
Mismatched immutable source/runtime pairs are refused before any filesystem work.

## Copied GUI URI preview

`gui-uri-session.mjs` is a no-payment fixture using the already paid GUI profile
copy and the pinned released wallet v.0.9.8 AppImage. It starts two exclusive
loopback private nodes, the Pay public page, Xvfb/noVNC and Firefox. A temporary
XDG profile registers the existing discrete URI route with an isolated testnet
data directory. It performs no mining, funding, signing or payment submission.
Run only in a bounded unprivileged loopback-only unit on the designated test VPS.
NoVNC must remain localhost-only. Do not automate a browser permission handoff.
Page rendering and reaching a browser permission dialog do not prove wallet
prefill; inspect the actual wallet after the user permits the Open Link action.
Stop the exact GUI unit and restore any separately authorized temporary SSH
forwarding exception when the preview ends. Original wallet profile stays intact.

The clean compatibility mode `isolated-freeman-ci-8703c16` passed empty-wallet
tracking attestation, spending-wallet/unregistered-wallet refusal, empty view-only
send/prepare refusal and mode after restart. This does not prove a registered
public-network payment. Native capacity/lifecycle fixtures remain a separate gate.

## Combined high-capacity qualification

`combined-native-journal.mjs` retains its10000 default fixture. The optional
`DISCRETE_PAY_COMBINED_COUNT=100000` requires an exact stopped native-load source
and its successful evidence hash (`DISCRETE_PAY_COMBINED_SOURCE`,
`DISCRETE_PAY_COMBINED_SOURCE_SHA256`). It refuses sources outside the designated
qualification tree. It seeds missing journal/invoice rows from validated native
addresses; this is not100000 merchant HTTP creations. The fixture-only streaming
prefix helper is tested against canonical JSON hashes and does not change Pay.

At100000, the existing ceiling is preserved: extra allocation/retry must return503
without another native address or journal reservation. The retained invoice must
still replay after reopening. Native high-index payment,20 recipient payments,
HTTPS HMAC retry, wallet recovery and a10-minute mixed scan/public/merchant-read/
replay phase are required. Forced native cleanup or failure is not PASS.

Updated default10000 regression passed on2026-09-09: private native late payment,
20 recipients, signed retry, wallet/worker recovery,20 stable scan cycles and
actualT10001/reopen. EvidenceSHA256:
`69284f59c2f7c4c89d5c97d3ebfd2bfb1af7aa423ff3c03c214026d72be232b0`.
The run shared a host with native address generation and had50% CPU quota; its
latencies are not isolated benchmarks or production SLA.100000 path remains
pending its native prerequisite and direct execution.

`combined-sequence.py` is a single bounded continuation of that exact test run,
not a recurring monitor or installer. It waits up to3hours for the existing
native100000 unit to stop cleanly and publish matching success evidence. It does
not stop or retry that prerequisite. Only then does it validate the installed
private stack, durably mark the pause, and start the copied combined fixture in
a separate unprivileged loopback-only unit (700MiB RAM,1GiB swap,3hour limit).
The combined unit and supervisor recovery both restore only the existing private
target. Recovery never starts that target while the prerequisite is running:
before a validated pause there is no restoration marker. Existing markers,
changed installation files, failed native evidence or another test process cause
refusal, not overwrite. Tests cover prerequisite and recovery gates; native
sequence completion still requires direct final evidence and service readback.

## Pinned private application upgrade

`persistent-upgrade.py` is a one-baseline qualification tool, not a production
updater. It pins the installed private state and Pay94995a7 candidate manifest
plus native100000 and extracted-package evidence hashes. Only the facade,
gateway, public web and worker release paths change. Nodes, tracking wallet,
environment, observer, SSH and firewall remain unchanged. Schema differences
refuse this code-only rollback. Old releases, metadata and coherent SQLite
backups remain retained; recovery never rewinds the live ledger database.

Run only as a root-owned, hash-checked helper under a bounded systemd supervisor
whose `ExecStopPost` calls the same helper with `recover`. `trial` deliberately
exits23 after candidate verification; require that failed supervisor result and
the independently checked restored baseline. A separate `activate` attempt is
accepted only after the recorded rollback, replay of the existing invoice,
unchanged financial fingerprint, new application PIDs after restart, all12units
active and fresh scanner/webhook observations. No payment, mining, public port
opening, production activation or broad infrastructure deployment is performed.
Offline tests exercise partial switches, refusal gates, recovery and backup
retry preservation; they do not replace an actual supervised rollback trial.

On2026-09-10 the native100000 prerequisite was directly read back as PASS:
evidenceSHA256`450474e339e6ebeb91e0720c130cb567d0d0e60ca753a8dba34992364d862624`,
four final merchant allocations, wallet/facade reopen and retained original
payment; journal confirmed normal service exit. Cold facade opening was38964ms
and38499ms after reopen on this fixture, not a production SLA.
The initial sequence did NOT run its second phase: systemd garbage-collected the
successful transient prerequisite before the next poll. The supervisor refused
its missing unit. Recovery now accepts that exact audited evidence hash after
unit collection; unknown hashes, malformed/failed evidence or active remaining
process groups still refuse. The loaded-unit checks are unchanged. It waits
boundedly for the named GUI preview before pausing anything. Nine offline gate
tests pass on Linux/Windows; actual recovery reached waiting-gui without stopping
the persistent target. Combined100000 runtime acceptance remains pending.
