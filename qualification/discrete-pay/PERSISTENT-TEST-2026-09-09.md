# Persistent private-chain service qualification

The assigned test host now runs compiled Pay applications as independent services,
not just children of a one-shot test harness. This is a persistent **private-chain
test**, not a public-network release or production custody/deployment profile.

Pay application baseline is merged runtime/schema `4d2f06952e2a566df4e92e9ee82b9f38601e0427`;
local Pay reference `90434e1e2002ad248e56257a9db831addbd26639` adds qualification work.
No application source, schema or wallet protocol changed in this step.

## Implementation

`persistent-test.py install <exact-qualified-service-handoff.json>` requires the
stopped paged native fixture and its preceding service/reboot PASS evidence. It
refuses existing installation roots, running fixture processes and conflicting
units. Original files are hashed, copied into a new private `run-persistent-*`
directory and checked unchanged. Only copied JSON/configuration paths are adapted.

The root-owned bundle pins Node, compiled Pay and the fixture role helper by file
SHA256. Native fixture executables, TLS fixture and baseline probe are separately
hashed dependencies; they are NOT public-network binaries. Four Pay units invoke
the compiled facade, gateway, public page and worker directly. Native chain,
tracking wallet, internal HTTPS receiver and edge remain labelled test services.
No signer/miner service is installed and the installer makes no transfers.

All units use the existing unprivileged qualification identity, strict filesystem
protection, empty capabilities, loopback-only kernel network access, bounded tasks
and memory, and restart-on-failure. Configuration environment files are root-only.
The test identity can access the disposable fixture wallets: this is explicitly
NOT the secret separation required for production. Do not import real wallets.

Boot enablement is a separate `enable` operation, requiring an exact-bundle PASS
receipt and active units. `verify` checks unit/bundle/dependency hashes and unchanged
original data. `stop` disables/stops only those hash-matched units, retaining all
data and bundle files; it does not remove unrelated services or alter SSH/firewall.

## Direct runtime evidence

Bundle SHA256 identifier:
`86fffae7782da5ad7df1101c43befe61907a9bef7c9f12498d487de590e17338`.

- Eleven services and their target active; actual compiled Pay entrypoints used.
- Prior native invoice retains confirmed `12346` atomic and its six lifecycle
  events, including the previous reorg. This is replay of an earlier payment,
  not a new transfer or a new reorg experiment.
- Loopback Nginx TLS: short native URI/page, trust/hostname rejection, merchant
  authentication, RPC denial and bounded rate limiting passed.
- Worker restart changes PID; prior amount/events/checkpoint remain unchanged;
  no duplicate receiver receipt appeared in the restart observation window.
- New native allocation `T=1002` for a 17-atomic test invoice through the compiled
  merchant API: create201, same payload retry200/same invoice, changed payload409,
  unauthenticated read401. Probe persists idempotency intent before sending.
- Stopping only the test tracking wallet produces scanner `rpc_unavailable`;
  public payment state/events/checkpoint remain unchanged. Recovery returns
  scanner `success`; gateway/worker restart preserves the new invoice's replay.
- Observer consumes actual worker scanner and webhook-cycle success. This does
  not assert queue/dead-letter health or external merchant delivery for new funds.
- Original fixture hashes and bundle hashes unchanged after these checks.
- Target boot enablement confirmed. A full target restart also recovered all
  services and retained the existing payment and new invoice replay. The initial
  orchestration check read a pre-restart snapshot too soon; the corrected check
  required scanner/webhook timestamps after restart and a successful real API
  replay. No Pay application change was needed.

The private host retains `install.json` and `acceptance.json` under its dedicated
test installation root. These contain local paths and are not public artifacts.
Offline renderer/refusal tests cover environment injection, fixed roles and paths,
loopback confinement, content changes, symlinks and boot acceptance binding.

## Remaining service boundaries

No public ports, domain, public TLS certificate, production wallet, new test
payment, host reboot, public-network bundle, 100000-address sustained-load result,
or production acceptance is established by this step. Previous GUI payment
evidence remains separate. Further native100000/load and distributable
public-network/provisioning work must not be replaced by monitor UI polishing.
