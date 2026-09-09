# Operational observer candidate checks — 2026-09-09

Baseline infrastructure: `30b7b9a35a009fa2bbb6f195aef48bd610031330`.
Pay application unchanged at `90434e1e2002ad248e56257a9db831addbd26639`.

## Executed

- Windows, Node24.18.1: policy suite10/10; syntax of monitor/collector/snapshot.
- Linux target host, existing Node22.23.2: same policy suite10/10 and syntax
  checks, in a new unprivileged staging directory. No dependency installation,
  shared runtime replacement, service activation or other service restart.
- Tests cover redaction/current-invocation filtering, stale/malformed/future
  snapshots, inactive worker, scanner failures, hysteresis, ordered failure and
  recovery retention, retry after simulated receiver failure, serialized-state
  restart, queue limits and local I/O failure before external send.

Exact source SHA256 values exercised on Linux:

| File | SHA256 |
| --- | --- |
| policy.mjs | cb36142ee106c862fce572b09f275eca5fe934edffa0fbdc8fbf13b52748546a |
| policy.test.mjs | 0554ae1fcef196bc7599080dddca801df96354846c4feb482aeceb3331809f8c |
| monitor.mjs | 5bd52d8bfd8bad025b5c2ed6cb6dc83f4edf1ae9d85c8c51840582c2f29086b3 |
| collect.mjs | 871efb5d4acd5cec1ba8b9f50e69d818ff20f863f30de637fae926316eedc312 |
| snapshot.mjs | b7f0f3a35b8f8e089923a0697c89079c78bbb9d0d3c4cdbe928441943a0b2305 |

## Not established

- Service installation, real snapshot export/SSH restriction, systemd sandbox
  effectiveness and actual steady-state/co-host resource usage.
- Actual Telegram delivery; a dedicated bot was selected and its token is pending.
- Full process crash recovery, whole-host failure or independent fallback channel.
- Merchant delivery backlog/dead-letter detection, public checkout probes or
  end-to-end payment monitoring (see README's precise coverage limits).

The qualification Pay host has no permanent `discrete-pay-worker.service`.
Do not substitute old successful test logs for a current active-worker signal.
This is saved candidate work, not an activated or fully qualified monitor.
