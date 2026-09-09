# GUI payment qualification result

Supersedes the manual credential handoff in GUI-HANDOFF-2026-09-09.md: user
completed it, then the actual released GUI created/sent the disposable payment.
Full interaction, exact version and remaining limits are in Pay
docs/gui-payment-qualification-2026-09-09.md. Pay runtime/schema remains4d2f069.

Fixture run-8Gqvfk: invoice inv_95608cfeff3b4e61913b0dc769e6fe48,
short28-1-GHT6-10002-T,10 atomic, GUI fee1 atomic. Transaction:
6d83898b5efdfe3208104ac13e028faa03ceddf412a023ae6ab0eacbecff2131.
GUI showed confirmed and9.89 remaining. Independent SQLite readOnly found one
matching canonical payment in block125 with11 confirmations; integrityok,
foreign-key errors0. Public HTTPconfirmed, target HMAC receipts2,3 repeat scans
without new events or deliveries. Evidence gui-payment.json and gui-payment-db.json.

The older10000-row fixture had historical test events ahead of this payment.
Explicitly bounded loopback drain completed9926 deliveries in328226ms, including
repeated scans. The database audit's pending-count is an earlier snapshot, not
the final queue state; final verification reached idle. Auto-review initially
rejected the mass drain, then allowed it after read-only proof of sole receiver
127.0.0.1:46411 and unit IPAddressDeny=any/Allow=localhost plus exact script guards.
No external recipient or production queue was involved; this is not an SLA.

Original unit shutdown FAILED: GUI ignored SIGTERM,30s systemd timeout killed
parent/GUI. Payment verification files were already persisted, aggregate file
was absent. Corrected only test-harness cleanup, not Pay or GUI wallet source:
save evidence before waits, bounded-child.mjs waits5s then records SIGKILL.
Linux bounded-child.test.mjs2/2 PASS; Windows normal/already-exited PASS and POSIX
ignore test skipped. Actual GUI with a copied post-payment profile was forcibly
stopped in3013ms, unitexit0 (gui-stop-check.json). No GUI-visible reopen claim.

Integrated corrected harness run-JWLbVg exited0 without timeout; all9 child
cleanup results fulfilled, aggregate evidence hash:
2979ac3790fcb909fbd257ef5aa3553c5e989fd222508b2b3254795ec2a76a29.
This fresh run made no payment; it tests cleanup only. Private wallet/profile
copies and original failure logs are retained on the dedicated VPS.

Forwarding restored to no, exact temporary config removed, local tunnelexit0,
no payqual processes, only public TCP SSH22822. No production or canonical merge.

Still open: browser native-URI launch/physical QR, sustained native100000/large
journal tests, real operator alert destination/delivery, pinned distributable
Freeman bundle and separate public-network/production qualification. Operator
destination requested, no general test or seed-confirmation permission blocker.
