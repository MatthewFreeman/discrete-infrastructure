# Discrete Pay application installation

This installs the four compiled Pay applications from the exact pinned internal
Linux-x64 bundle. It does not install a native node/wallet, register an account,
copy spending keys, publish a release, open ports, modify SSH or configure DNS.
The host, tracking-only walletd and node RPC must be provisioned separately.
This is distinct from `qualification/discrete-pay/persistent-test.py`: installed
application units do not import a fixture launcher, test wallet or source checkout.

Current accepted input is the Pay94995a7 bundle manifest SHA256
`120f2b9478d4474d9cb27456aeb9b83d24febadaebdfb1ba887ba1e856f6f589`.
The installer validates every source file and the copied application files.
It creates one new locked-login system identity `discretepay`; existing identities,
unit names and differing files are refused rather than adopted or overwritten.

## Operator inputs

Keep the request outside Git in a root-owned0700 directory, as a root-owned0600
regular single-link JSON file. No symlinks or shell hooks. Top-level fields:

- `bundlePath`: canonical root-controlled extracted bundle directory.
- `environments`: exact facade/gateway/public/worker environment maps documented
  in the Pay runtime guides; explicit opt-in, loopback hosts, ports and limits.
- `worker`: exact worker JSON configuration, including independently trusted
  network/genesis/account and explicit HTTPS destination/IPv4 pairs.
- `keyring`: existing AES256 wrapping-key map, never a wallet seed or spend key.
- `caPem`: null for normal certificate trust, or an approved internal PEM CA.
- `databaseSnapshot` and `journalSnapshot`: both null for a fresh empty database,
  or a coherent pair of root-private SQLite snapshots from stopped writers.
  Live WAL/SHM/journal companions are refused. Never mix snapshots from different
  wallets or capture the gateway and allocation journal at different logical times.

All installed data paths are fixed under `/opt/discrete-pay/private`:
`gateway.sqlite3`, `allocations.sqlite3`, `worker.json`, `keyring.json` and optional
`ca.pem`. The gateway/public/worker must share the same database and network;
facade/worker wallet credentials and gateway/facade capability must match.
The worker config path environment value must point to that installed worker.json.
Listener ports must be distinct; native RPC ports must not overlap them.

`test_install.py` has a complete **synthetic** request construction for schema
reference; its dummy credentials and account must never be deployed.

## Lifecycle

Run the reviewed script as root on Linux with Python3 and systemd:

```sh
python3 install.py prepare /root/pay-input/request.json
python3 install.py verify
python3 install.py start
python3 install.py stop
```

Prepare publishes immutable code, private configuration and disabled units.
It makes no network call to the wallet and starts no application. Interrupted
unit publication may be retried with the same request; differing input refuses.
An earlier preparation failure can leave a protected staging directory/system
identity for inspection: do not delete it or reuse the identity blindly.
Start uses the four real compiled entrypoints, not a development/test server.
Its active-process result is explicitly `started-not-accepted`, not payment or
production acceptance. Stop retains all code, configuration and application data.
No command enables boot startup or silently migrates an existing deployment.

Units are named `discrete-pay-app-{facade,gateway,public,worker}.service` and grouped
under `discrete-pay-app.target`. They run without capabilities under a distinct
UID, with immutable code, private writable application data and loopback-only
listeners. Only the worker gets the operator's additional explicit webhook IP
allowlist. Worker/keyring/CA files are read-only inside the service namespaces.
Raw native RPC remains local. Bind configuration is not a substitute for the
host firewall, TLS reverse proxy or a walletd capability review.

Use the installed Node and operator CLI as `discretepay` to issue merchant keys
and webhook secrets into owned0600 files in the private directory. Follow Pay's
credential/webhook guides; no secret is printed by this installer. Provisioning
does not prove that an already-running worker loaded the same configuration.

Before boot activation, directly verify merchant creation/replay/conflict/auth,
wallet attestation, actual payment state, webhook signature/retry, restart and
backup/restore for the exact environment. Production/public-network activation
requires its own explicit operator decision. Current runtime evidence is recorded
separately after actual qualification; offline tests alone are not acceptance.
