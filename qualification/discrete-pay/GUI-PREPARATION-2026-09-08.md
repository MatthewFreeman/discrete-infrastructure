# Isolated ordinary-wallet GUI preparation (not acceptance)

`gui-session.mjs` is an unfinished manual qualification fixture, not a deployment
tool. It copies the retained native/full-journal run-OjCKl5 state and creates a
new GUI profile. It must run as payqual with UMask0077, IPAddressDeny=any,
IPAddressAllow=localhost, RuntimeMaxSec3600 and a control-group cleanup policy.
All fixed 18891/18901..18911/5901 loopback ports and X display99 must be free.
Never point it at public nodes, real wallets or production databases.

Ordinary upstream GUI release v.0.9.8, tag55a582db54d329fc9988bd88209129d2c8ac0a0b,
AppImage SHA256 f90ddac3b033492c878623f6608095363314640e95039fa3d168b4d2327f72cf,
was downloaded from discretecoin/discrete-wallet and verified before extraction
as payqual. This GUI version is not the walletd version. It is separate from the
unchanged walletd8703c16/private difficulty-one daemon and Pay4d2f069 runtime.

Debian12 test host received Xvfb, x11vnc, noVNC, websockify and required display
libraries. No SSH/firewall or public listener rule changed. Always use the pinned
Node24 executable under /opt/discrete-pay-qualification/tools, not apt's Node18.

Run gui-qualification/run-3x8lrp started the GUI process with an empty, isolated
profile configured for its loopback private-testnet node. The initial executed
helper had no startup hash assertions; these were added to the saved helper
after the process-start check. Local node --check passes; the saved variant has
not been run through a GUI interaction. Do not describe process start as screen,
connection, invoice, funding or GUI-payment acceptance.

No GUI interaction, funding or GUI payment occurred. SSH has AllowTcpForwarding=no.
The user was asked whether to permit a temporary serveradmin local forward only
to127.0.0.1:18891, then restore the prohibition. Until an answer, no forwarding
exception is installed and no alternative forwarding mechanism is used.

The transient GUI unit was stopped cleanly (ExecMainStatus0); independent pgrep
found no payqual process and ss found only public SSH22822. Fixture/profile data
and installed GUI packages were retained. Preparation evidence SHA256:
f597d71d5d6a831b2628b9f4630004f0dde0036847e74afad6477ddb4c627580.

Before a future run, verify source/artifact digests, fixed-port availability,
empty new profile, active testnet node and GUI amount precision. Control API
credentials remain only in the mode0600 private handoff. Its /fund operation is
one-shot and must receive an address actually observed in this disposable GUI;
never retry an ambiguous submission. Observe the GUI payment and independently
check exact invoice/transaction/HMAC evidence before calling acceptance passed.

The helper deliberately does not alter host SSH policy or install an enabled
application service. A GUI session is bounded testing, not production.
