# GUI continuation: manual seed-confirmation step

User authorized the previously described temporary destination-restricted SSH
forward and completing all relevant tests. No production or real funds in scope.
Baseline: Pay6db92212e4f60b96ae60135648eb29f981046bd6;
Infrastructure91943b33e6c053a56943a96d5f873901829a8faf; both worktrees clean.
Pay final CI34249114068 rechecked PASS; CorePR31 OPEN at8703c16, no merge/release.

Temporary SSH Match User serveradmin exception permits local forwarding only
to127.0.0.1:18891; GatewayPorts=no, PasswordAuthentication=no, PermitRootLogin=no.
Independent key/sudo connection after reload passed. Actual direct-tcpip channel
to private node RPC127.0.0.1:18901 was administratively refused. Only public TCP
listener remains SSH22822. No public VNC, walletd, Pay or node port was opened.
The exception's exact normalized SHA256 is
7055d3ffb5697933f6554a9e9bec21d6698d93b281135d78d127ab72a9358b00.

Rollback was armed BEFORE installing the exception:
pay-gui-forward-rollback.timer invokes hash-checked restore-gui-forward.sh after
30 minutes. The local gui-tunnel.py binds only127.0.0.1:18891 and expires after
25 minutes. Test GUI service has RuntimeMaxSec3600, UMask0077, payqual identity,
IPAddressDeny=any and IPAddressAllow=localhost. These timers are safety bounds,
not evidence that cleanup has already happened; refresh actual state on resume.

GUI fixture copy: gui-qualification/run-8Gqvfk, private chain tip100. Source GUI
helper SHA2560b40054f954e318d846ef75eb07778a0626364bbf766953445707b7c275ff970.
Ordinary upstream GUIv.0.9.8 and native/Pay hashes are the pinned prerequisites
described in GUI-PREPARATION-2026-09-08.md. The saved hash-guarded helper launched.

Observed through noVNC browser canvas: wallet welcome screen; Create wallet;
new file gui.wallet in the fresh GUI profile; generated testnet tdisc address
and zero available balance. GUI then requires mnemonic repetition. No seed was
entered, copied into code or persisted in this report. User was asked to enter
it directly into Repeat and press OK; do not transmit it through chat. Escape
did not dismiss this dialog. No GUI funding or outgoing payment has occurred.

Private merchant HTTP created invoice inv_95608cfeff3b4e61913b0dc769e6fe48,
short deposit28-1-GHT6-10002-T, amount10 atomic (0.10 XDS, decimal precision2),
required confirmations2. No GUI payment or signed webhook acceptance is claimed.
The one-hour invoice may expire before resume; create a fresh isolated invoice
when required without deleting or rewriting the old one.

Immediate continuation: check timers/processes and current browser; complete
user seed-confirmation handoff, observe GUI receive address, fund only that
disposable wallet once, mine bounded blocks, exercise short-address GUI payment,
then independently verify Pay confirmation/HMAC/replay. Never infer the GUI
path from an RPC-only transaction or automate around a required credential handoff.
After interaction, stop test unit/tunnel and restore the exact exception; verify
AllowTcpForwarding=no and original public listener policy. Retain fixture data.

Other remaining service gates are unchanged: sustained native100000/large-journal
load, actual operator destination/delivery, pinned distributable Freeman bundle,
then separately public-network/production qualification. Domain remains deferred.
These helpers depend on the owner's protected resume_host adapter for SSH;
credentials and private session handoff must remain outside repositories.
