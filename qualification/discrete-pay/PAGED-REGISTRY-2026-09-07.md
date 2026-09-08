# Isolated paged-registry qualification — 2026-09-07 Pacific

## Candidates and provenance

- Prior Infrastructure baseline `d13d078596bd90436b1a82b0882f12ffdb1c7f14` and
  Pay `06a589328c7435a52c1ab28189f36983ebace362` remain unchanged on prior branches.
- New Pay PR17 is stacked on PR16. Transport commit `39d3c9b`, validated
  in-memory prefix runtime `8b29cae`, final native test helper
  `88a3825ae7b88de368f7dbec23768d0b650e5dd0`.
- New walletd is Freeman Core `8703c16fa40ffc8456e3d71696b6220b32b4d74a`, based
  on `bee9981`. All eight jobs of CI34181954333 passed. Used Linux universal
  artifact10039317338; walletd SHA256
  `630a033e0b41ebb01d666886948bd9a4affa4c44a299474bc125c3284afc15d1`.
- Node is the prior private-chain fixture at Core3e8ef0ba, with loopback/testnet
  difficulty patches, SHA256
  `fb9408fb76ab54eebd7016c8d997ad9ece39399b4851e8308e86e6fc3725cfb5`.
  Not a public-network or production binary. No new consensus changes.
- Canonical PR29 remains tracking-attestation only, OPEN at bee9981; no new
  canonical pagination PR, merge, release or production deployment authorized.

## Executed evidence

Host144.202.94.185, dedicated payqual user. Separate `/opt/discrete-pay-qualification/pay-paged`
and `pay-paged-tail` trees, separate loopback-only systemd transient units with
IPAddressDeny=any / IPAddressAllow=localhost and resource limits. Existing `/pay`,
old binaries, wallet state and successful recovery artifacts were not overwritten.

- Pay39d3c9b: all four builds and 330 tests on host; native runDQT3zC PASS.
- Pay8b29cae: all four builds and 332 tests on host. First native retryefW4Dy
  passed payment/reorg, then failed test foreign-account wait. Read-only RPC on
  copied stateB3MqMx found registration at50/tip59, just before Core finality10.
- Pay3c39239 test retryCzQ3ab also timed out in the transaction predicate. Copy
  lkCAlF showed registered=true, inclusion49/tip793 and direct transactionstate0.
  The transient false predicate was not logged; do not claim its exact root cause.
  Final helper uses actual account-publication RPC, plus inclusion+10, and checks
  the fresh test payer was unregistered before its paid registration.
- Native runNFdcs1 with unchanged8b29 runtime plus88a3825 helper: PASS, 38 checks;
  unitpay-qualification-paged-tail-3 exited0/inactive. Registration inclusion49,
  observed tip63; payment12345 atomic; three-block native P2P reorg; HMAC HTTPS
  retry after restart; confirmation revocation and reconfirmation exactly once;
  registered foreign tracking-wallet quarantine and original-wallet recovery;
  legacy999->1000 gate/replay; paged allocation1001, invalid page/stale-count/
  foreign-account refusal, and exact replay after journal reopen.
- Local88a3825: typecheck, 332 tests/30 files, all four builds, compiled gateway
  and worker smoke PASS. CI34183990611 Ubuntu/Windows also PASS at the same head.

Sanitized JSON copies are in `evidence/paged-*.json`. Original host NFdcs1 JSON
SHA256 `a3cb42fa19a3692f891f9262a4adfc9f711afe1922d50ad7b3737c438d07a912`;
tracked copies add a trailing newline and therefore have their own file hashes.
Original full failed/successful run directories remain server-private. Do not
publish wallet/config/service-handoff files. Diagnostic scripts require copying
the exact owned disposable state and only read RPC; they do not send or mine.

First orchestration failures were a source-tar permission mismatch and missing
pnpm PATH; another isolated check incorrectly denied loopback and was stopped.
Corrected build unit paged-build-3 passed. Failed transient units and journals
remain as evidence; they are not running production failures.

Final read-only host audit: no payqual processes; SSH22822 TCP and DHCP68 UDP
only. No walletd/facade/merchant listener publicly exposed. No real funds or Buyback
processes touched. No app deployed, DNS changed or new secrets published.

## Remaining qualification / rollback

Paged mode is opt-in and still has a100000 resource budget. Native1001 passed;
10000/100000 were modeled through real transport parsing, not native load tests.
Warm RPC reads reuse a validated immutable prefix, but local journal/hash work
is still O(N). Native large-registry gateway latency and long-run load are open.
The previous systemd/TLS/backup/reboot qualification belongs to the legacy mode,
not this new candidate. GUI payment and real operator alert destination/delivery
also remain open; domain deliberately deferred. No tariff/billing implemented.

No schema migration or old-address reuse. Keep both old and new candidates.
After issuing more than1000 addresses, legacy cannot resume new allocations:
retain paged binaries for read/recovery; never delete issued addresses to downgrade.
