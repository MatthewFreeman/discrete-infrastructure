# Pay operational observer — deployment candidate

No deployment is implied by these files. This is an independent process/account,
not an extension loaded into an existing monitor. Do not copy wallet, database,
merchant, SSH administrator or other service credentials into it.

The design deliberately adapts bounded read-only polling, incident hysteresis
(three failed observations / two successful observations), persistent notification
retry and redacted operator messages. It does not import a financial application.

## Transport and scope

Use a dedicated **forced-command SSH key**, pinned host key, no PTY, forwarding,
agent forwarding, user rc or interactive shell. Only literal `snapshot` is allowed.
This reuses the Pay host's existing SSH listener; no new public Pay HTTP/RPC port,
Telegram webhook or bot command handler is introduced. SSH authenticates both
peers and encrypts the snapshot instead of adding a second HMAC protocol.

`collect.mjs` is a local privileged oneshot with fixed read-only commands for
`discrete-pay-worker.service`. Its sandbox can write only its runtime directory;
it exports sanitized cycle events and unit state, never raw logs. `snapshot.mjs`
is an unprivileged SSH forced command that can only return this root-owned file.
The observer is not in the global `systemd-journal` group and has no sudo rights.
Prove unrelated logs and database/wallet/config files remain unreadable before
activation. A missing worker is explicitly inactive, never a green baseline.
The forced command uses a separate root-owned copy of the verified Node runtime;
it does not require opening access to protected qualification directories.

Current worker invocation filtering prevents a restarted process from looking
good because of old journal lines. Heartbeat older than 180 seconds is stale;
snapshot older than 30 seconds is rejected. Polling is every 10 seconds after the
previous cycle, with a 15-second SSH deadline. Observer and Pay clocks must sync.

Coverage: worker inactive/unreachable, missing/stalled scanner or webhook cycles,
scanner catching-up/reorg/chain/RPC failures. A webhook cycle `success` only means
the loop completed: **individual retry/dead deliveries and queue age are not
covered by the current worker signal**. Do not call this full payment monitoring,
public checkout monitoring or merchant delivery confirmation.

## Monitor host preparation (not executed by this document)

- Separate `paymonitor` system user, no sudo or access to other monitors' files.
- Root-owned immutable `/opt/discrete-pay-monitor/releases/<commit>` with a
  `current` symlink; retain previous release and state before activation.
- Node 22 or 24 at the service's explicitly verified path; do not replace a shared
  runtime. Supplied templates use the observed monitor and qualification paths;
  verify them before installing anywhere else.
- `/etc/discrete-pay-monitor/ssh_config`: root-owned, alias `pay-observer`, exact
  Pay address/port, dedicated key, isolated pinned known-hosts, BatchMode,
  IdentitiesOnly and StrictHostKeyChecking. No ProxyCommand or inherited config.
- `/etc/discrete-pay-monitor/telegram.json`: mode0640 root:paymonitor, shape
  `{"token":"<dedicated bot token>","chatId":"<owner numeric id>"}`. Do not
  reuse another monitor's token by default. No credentials in this repository.
- Validate/install the supplied unit, with MemoryHigh128M/MemoryMax192M,
  CPUQuota10%, TasksMax32. These are planned caps, not measured consumption.
- Validate snapshot restriction, denied forwarding/shell/other-file reads;
  then actual operator delivery, stop/stall/recovery, SSH failure, Telegram retry,
  process restart and co-host regression. Do not stop any unrelated service.

Telegram delivery is at-least-once: an ambiguous response or crash after receiver
acceptance can duplicate an alert; its stable id is retained. The bounded queue
holds both failure and recovery during an outage. Full queue or local I/O failure
stops the observer rather than dropping an incident. An independent watchdog must
detect observer/host failure; two monitors on one VPS share a failure domain.

Rollback: stop/disable **only** `discrete-pay-monitor.service`, restore its own
previous immutable release and validated state/config; revoke only the dedicated
Pay observer key when removing the integration. Do not change co-hosted services.

## Local checks

```
node --test monitoring/discrete-pay/policy.test.mjs
node --check monitoring/discrete-pay/monitor.mjs
node --check monitoring/discrete-pay/snapshot.mjs
```
