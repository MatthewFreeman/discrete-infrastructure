# Current-base walletd candidate (qualification only)

Baseline: public `discretecoin/discrete` tag `v.0.9.10`, commit
`3e8ef0bad719c6ac6304674f76df52cc5aecbea7`.

The shipped Linux binary was tested twice and omits `tracking` in
`getDepositScheme`, so Pay refuses it. An older Freeman CI build proves the mode
attestation works, but does not justify downgrading the node/wallet release.

`current-walletd-attestation.patch` ports only that RPC field and its getter to
the current source: seven files, 12 inserted and three removed lines. The getter
uses the same `getTrackingMode()` as the existing wallet guard and returns false
for the no-address case. The RPC reads it under the existing `readyEvent` lock.
There is no new key export, spend path, consensus rule, or Pay parser relaxation.
This is a test overlay, not a published Core release or merged Core change.

- Public source archive SHA256:
  `4f2ef82664bbdcbbd2e1b38d20cf2886f35dac59f3dee66c85b00241995564b2`.
- LF patch SHA256:
  `5a0f3262c678b46cfef8758a64018651c01c4d50d7ac1486ec585f7d44ef57b8`.
- All 1660 server source files matched that archive plus exactly the seven
  patched targets, with LF normalization only on those targets.

Build isolation: disposable `payqual` account, separate source/build directories,
one compiler job, 750 MiB memory limit, 2 GiB swap limit, outbound network denied.
The first attempt failed before compilation because the Windows-produced Git
archive contained CRLF. The second normalizes only the seven targets; the first
attempt is retained. No production service or known-good fixture is overwritten.

The `build-current-walletd.sh` result proves compilation only. The opt-in
`DISCRETE_PAY_RELEASE_CHECK=isolated-current-attestation` mode of
`release-compatibility.mjs` separately checks real spending/view-only responses,
Pay refusal codes, zero spend export, empty-wallet send/prepare refusal and
view-only restart. It uses the unmodified official discreted and no real funds,
mining, registration or public peers. A successful mode test is not payment,
registration, reorg, mainnet, or production-release acceptance.

The second build and native mode probe have now passed. Exact candidate walletd
SHA256 is `2b289b1d064df864d1ef55abbd417a78748eb74bdb51665c839cfad0a65e36bc`.
Probe run `H7BUsc` verified `tracking=false` spending refusal, `tracking=true`
view-only mode, expected unregistered-account refusal in Pay parser/facade/scanner,
zero spend export, send/prepare application error 5, and mode persistence after
process restart. The empty-wallet test does not prove refusal with observed funds.
Secret-free result SHA256:
`079a538b0c2f33642c6fada0e5b3c38d9ffe9b8cb924a5d505024a765262679b`.

`build-current-native.sh` and `current-fixture-manifest.mjs` build a SEPARATE
current-base daemon with the established loopback and testnet-difficulty-1
overlays, and pair it with that exact walletd. Pay's native harness opt-in
`DISCRETE_PAY_NATIVE_RELEASE=v0.9.10-attestation` selects separate binary/data
directories and pins the current source commit. Default old-fixture behavior is
unchanged. The complete current fixture passed in `current/run-zNSX1D`:
registration, tracking-only refusal with observed funds, exact 12345 payment,
HMAC retry/restart, wallet outage, four-node depth-3 reorg and reconfirmation,
wrong-wallet quarantine/recovery and the 1000-address limit.
Evidence SHA256 `36d904767fb2c3a1e6585c32be0a5e77201478a6cd1032004fdf834f86d9c12c`.
Test-only daemon SHA256 `fb9408fb76ab54eebd7016c8d997ad9ece39399b4851e8308e86e6fc3725cfb5`.

The current testnet genesis was independently pinned using the unmodified
official daemon (`official-genesis.mjs`). A diagnostic on a copy of the failed
payment run (`current-scan-diagnostic.mjs`) proved inclusion in the second mined
block; current-only confirmation mining now follows actual inclusion height.
The original failed runs remain intact. The old Windows native/reorg flow was
rerun successfully, preserving default behavior.

Current systemd services subsequently passed TLS/auth/denial checks, wallet
outage/recovery, exact additional-payment total 12346, killed-worker restart,
identical HMAC retry, online SQLite backup and cold full-state restore. The
initial launcher path refusal is retained; the launcher now checks the exact
two binary paths associated with the selected fixture, not an arbitrary prefix.

Actual reboot also passed all 12 auto-started roles, exact payment/registry/state
and TLS readback. The exact temporary units were removed afterwards, preserving
all data. Final listeners: SSH TCP22822 and DHCP UDP68 only.
Service evidence SHA256 `0145ce669f35559579e0f9f27f22e4bdfb902fc88ffbf678e51afba90ba6d14a`;
reboot evidence SHA256 `fdd00ebf88ef4491cf4f14ba686a301b4e1c6a46811c64e90c3a83a0a9344321`.
The new cold archive also passed separate encrypted off-host decryption, exact
SQLite readback and wrong-passphrase/tamper refusal; previous backups retained.
That evidence SHA256 is `229801dd12a13d9136d06db39b81e4de8c58e188721b47c57fb029b671041179`.
Full details and remaining public-release/GUI/alert boundaries are in Pay's
`docs/release-and-offhost-check-2026-09-07.md`; this remains a test-only overlay.
