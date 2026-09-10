# Standalone application acceptance — 2026-09-10 UTC

Scope: an independent installation on the dedicated PRIVATE-chain test host.
Not a public-network release, production deployment or new real-funds payment.
The original persistent private test stack remained running and unchanged.

## Exact inputs

- Pay runtime: `94995a7c8d7215d1261b79abb83ae7fdda181c58`.
- Bundle manifest SHA256: `120f2b9478d4474d9cb27456aeb9b83d24febadaebdfb1ba887ba1e856f6f589`.
- Bundle archive SHA256: `a6f5e00970f037678c7b3d8b0452d1e95f6c175531d6520d52c65a5f336d92ec`.
- Installer prepare/start source SHA256: `da52119f50eb85a0edfad9b9ffc43fd668db258ead11a205fd036ac1e33a0929`.
- Installer with qualified WAL backup: `02690873d2d912a6ae2218d30968d6e2af058a0c53cc0ee8be3794409cda1ffd`.
- Native tracking walletd SHA256: `630a033e0b41ebb01d666886948bd9a4affa4c44a299474bc125c3284afc15d1`.
- Root-private acceptance record SHA256: `d956e9c99e9dcde48d1262cc40f7c4d2159fc47da2940460922daae7fd388623`.

The four applications ran as a new `discretepay` UID from immutable copied code,
not the fixture launcher. A separately copied tracking-only wallet was the native
input; no spending wallet was installed under that UID. The gateway and allocation
journal were a coherent snapshot pair. Only copied legacy webhook endpoints were
disabled to prevent delivery into the original fixture. This was not the fresh,
empty-database install path and did not create a new signed payment.

## Directly exercised

1. Root-controlled package validation, prepare, same-input prepare replay and
   start of all four real compiled entrypoints. The runtime UID could not read
   either the copied native wallet or the original deployment's private state.
2. Installed merchant-key and webhook operator CLIs: initial issuance, same-intent
   replay and private credential files. API invoice creation allocated native
   T1002; replay returned200, conflicting payload409, missing key401 and a
   different merchant404. The payment page returned200 with the native URI.
3. The test HTTPS receiver verified the signature, rejected delivery with503,
   then accepted the identical delivery ID/body/digest with204 after an actual
   worker stop/start. The new unpaid invoice expired; original paid12346 state
   and event/checkpoint records remained unchanged.
4. Copied tracking-wallet restart and all four application restarts: new process
   IDs, native registry revalidation, same HTTP invoice/address, unchanged
   financial/event fingerprint and fresh current-invocation worker cycles.
5. Quiescent paired backup through SQLite's backup API, integrity/hash validation,
   restoration of both databases with the old main/WAL/SHM files retained, and
   actual post-restore HTTP/native replay with the same fingerprint.
6. Key revocation and repeat revocation; the live API returned401 and replaying
   the old issuance intent could not reactivate the key.
7. Collector source `ff6eabd46001e0197f53c49ecbc5f43d62359565904ddbe3475ce0e798ead30e`
   read both the original and standalone worker with fresh success samples in
   isolated mount namespaces. The active observer and its snapshot were not
   replaced; Telegram/Buyback configuration was not changed.

Linux installer tests:12/12. Windows:9 passed,3 POSIX-only skips. Collector policy
tests:11/11, including original binding, standalone binding and arbitrary-unit
refusal. These offline counts are separate from the actual runtime checks above.

## Failures retained and corrected

- A package below an operator-owned ancestor correctly refused before identity
  creation. The identical pinned archive was extracted under root-controlled
  inputs; the ownership guard was not weakened.
- The host Python lacked the newer tar extraction `filter` argument. The
  qualification-only copier now accepts only explicit regular members from the
  exact archive and refuses links/special files/traversal.
- A cold-copy assumption failed because stopped SQLite writers can leave WAL
  when the last peer was read-only. The installer now captures committed WAL
  through SQLite's backup API; both a WAL regression and actual restore passed.

## Final state and remaining boundary

Only the extra four-app qualification instance, copied tracking wallet and test
receiver were stopped. Installed files, backups, original database sidecars and
proofs were retained. The original12-unit private stack remained active and boot
enabled, with unchanged source data, fresh scanner/webhook-cycle success and no
new public TCP listener. A successful webhook cycle is not a delivery receipt.

Public hostname/certificate/edge and public-network wallet commissioning remain
separate. Domain purchase is deferred by the owner. Physical QR-camera and other
client-platform behavior, power-cut restore, production key ceremony and real
merchant delivery are not established here. The installer does not auto-enable
boot startup, configure public access or provide a generic upgrade/restore CLI.
