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

At this preservation checkpoint the candidate build is still running; no new
candidate runtime result is claimed. See the Pay release report and knowledge
base for later exact binary hashes and results before using it.
