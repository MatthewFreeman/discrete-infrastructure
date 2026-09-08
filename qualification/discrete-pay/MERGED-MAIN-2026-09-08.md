# Merged Pay continuation — 2026-09-08 UTC

User explicitly requested Freeman integration, without another development-PR
pause. Pay PR16/17 merged into4d2f069 (tree equals ef98b02; main CI34185877490 PASS),
then documentation e7f76a1 (CI34186678021 PASS). Infrastructure PR33 merged80a4247,
paged evidence integrated e30267d, service qualification d13e9d2; main workflows
passed. Unrelated PR31 and canonical Core PR29 were not merged.

This branch continues directly to development main after checks. Exact tests:

| Evidence | Scope/result |
|---|---|
| evidence/paged-load10000.json | PASS: native10000 issued addresses, four real merchant requests1018/1970/2930/3868ms, new wallet/facade process replay; original confirmed12345/events/checkpoint retained. |
| evidence/paged-service-merged-main.json | PASS on independent1001 fixture: systemd, loopback TLS/auth/limits, wallet outage/recovery, test overpayment12346, worker kill/restart/HMAC retry, online and full cold restore. |
| evidence/paged-reboot-merged-main.json | PASS: actual changed boot ID, exact autostart units, invoice/registry1001/TLS readback; test units removed afterwards. |
| evidence/paged-offhost-merged-main.json | PASS: encrypted off-host backup, correct decrypt/SQLite readback, wrong-passphrase and tamper refusal. |
| evidence/paged-load-short-test-key.json | Retained FAIL from invalid short test idempotency key; fixed helper input, API unchanged. |
| evidence/paged-high-index10000.json | PASS: native payment12345 to T=10000, public seen/confirmed, real HTTPS HMAC503/retry across worker reopen, wallet outage/reopen, no duplicate or neighboring invoice credit. |
| evidence/paged-high-index-funding-timeout.json | Retained FAIL: continuous difficulty-one test mining timed out waiting for funding-balance observation; helper now bounds mining by node height before wallet catch-up. |
| evidence/full-journal10000.json | PASS: eight callers created10000 real HTTP invoices and durable SQLite allocation records, unique T/IDs, reopen/replay/conflict/integrity; fake wallet, explicit test rate10000/minute. |
| evidence/full-journal-default-rate-limit.json | Retained diagnostic FAIL: default120/minute correctly returned429 after120 creations; runtime default unchanged. |
| evidence/full-journal-first-rate-limit.json | Retained initial failure before caller status diagnostics were added. |
| evidence/combined-native10000.json | PASS: native wallet plus10000-row seeded journals, paid_lateT10000,20 native recipients,20 stable scan cycles, real merchantT10001/reopen/replay. |

Merged Pay source was rebuilt at `/opt/discrete-pay-qualification/pay-merged-4d2f069`.
New data copies: native-load/run-mku6hq/state (sourceNFdcs1) and native-ops/run-refv70x9.
Original successful and failed runs preserved. Load used native walletd8703c16
and prior private difficulty1 daemon; binary hashes are in PAGED-REGISTRY-2026-09-07.md.
Load prefill to9996 took1197895ms with8 native callers while Pay was stopped;
full-start4550ms, reopen3867ms. This does not create10000 invoice journal rows,
exercise high-T payment, sustained throughput or native100000.

Original host JSON hashes (tracked copies have a trailing newline):

- load337bbdac87d62a00085b48cfdd25da152a24868ae4f1707d6f59ec0224b642a0
- servicescd2f57530f4f4986d2e0d17c14854a7f9bd1a068643150c2b0129504c4a4a6be
- rebootda329bf4281cd875807ca82514df71b141a2e6af1a2d60d36d86d7684ac49a1a
- cold archive7743642da6f7b6d121ed7e91749c39d33bef0a5ba42d81078d310f189edf5e95

Only qualified paged test units were removed by exact path/hash after reboot.
Effective definitions remain under paged-boot-units, data/backups preserved.
Final host had no payqual processes; SSH22822/DHCP68 only, no public app listener.
No production activation, DNS, real funds or Buyback interaction.

The offhost-backup-windows.py file preserves the executed helper; its working
copy runs in Pay build/server-bootstrap alongside the owner's protected
resume_host adapter. Credentials and encrypted archive stay outside repositories.
The helper is not a portable production backup policy/job.

High-index payment used a fresh `native-high-index/run-udglgA/state` copy of
run-mku6hq/state, same pinned walletd/daemon and Pay4d2f069. It has10000 native
addresses but only seven invoice records. Original evidence SHA256
f02d1e1b0b4e58d1f07e6916e4d256da59d13971bb58258df421145f4b726f25.
First run-Uxcokb and diagnostic copy diagnosis-KmkmAG are retained; diagnosis
found its funding in block64 with available16653 at stopped tip3824. No runtime
fix, original baseline edit, or retry of an ambiguous send. The helper now mines
bounded blocks then waits for wallet scanning. Successful test unit exited0;
no payqual processes or application listeners remained after this batch.

`full-journal-load.mjs` separately exercises actual HTTP/SQLite with a fake wallet
port. Run-51GgjF PASS:10000 invoices and committed allocations in148449ms,
p50/p95/p99/max111/212/226/359ms, full cold reopen271ms. Eight sampled replays,
payload-conflict409, both integrity/foreign-key checks passed. Explicit fixture
rate10000/minute uses existing configuration; default120 remains unchanged.
Original evidence SHA256 f072fd3ff25cd04deee3ad9b7aec5c7a15212c0a16e94129dfb5b195945a87ea.
Do not report its results as native payments or a production load SLA.

Combined `native-combined/run-OjCKl5` uses copied native10000 state and seeds9993
missing test invoice/allocation rows through persistence APIs from validated
native addresses, retaining seven original rows; no native creation in seeding.
NativeT10000 paid_late12345/HTTPS503/retry/reopen PASS,20 other recipients each
confirmed1 atomic with signed webhooks,20 stable scan cycles960..1060ms/mean1008ms
without duplicate events. Actual merchant allocationT10001 took979ms with full
journals; facade/gateway reopen4055ms and replay PASS. Not10000 end-to-end creates
or a long-running mixed workload. Original evidence SHA256
f72d2238205512c5e88a9d5cc8290884551099ae9d939e8ff33237546ab5e02d.
CanonicalPR31 now open at8703c16; CI34189907014 all8 PASS. No merge/release.

Open: native100000 and long-running mixed native-wallet/full-journal load, ordinary GUI-wallet
acceptance, actual operator alert destination/delivery, canonical release and
public-network policy. Domain deliberately deferred. Do not promote local
journal signals or isolated proofs to operator delivery or production readiness.
