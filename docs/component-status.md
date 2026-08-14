# Component status

This is the authoritative readiness register. `Validated` means the documented user-visible
sequence was exercised on the named platform; CI-only checks do not qualify for that status.

| Component | Capability | Debian 12 | Ubuntu 24.04 | Evidence or next step |
|---|---|---|---|---|
| Host | Clean installation bootstrap | Validated | Validated | Platform runbooks under [`docs/host/`](host/README.md) |
| Host | IPv4-only, SSH, nftables, Fail2Ban, time sync | Validated | Validated | Runbook status and port-audit contracts |
| Node | Official Linux artifact selection | Accepted | Accepted | [ADR 0001](decisions/0001-use-official-universal-linux-amd64.md) |
| Node | Discrete v0.9.5 qualification evidence | Published | Published | [Benchmark suite](benchmarks/discrete-v0.9.5/README.md) |
| Node | Production installation | Planned | Planned | Implement `modules/node/` after release adoption |
| Node | Default-on automatic updates and rollback | Planned | Planned | Requires signed/checksummed release policy and lifecycle tests |
| Block explorer | Deployment automation | Backlog | Backlog | No implementation yet |
| Web wallet | Deployment automation | Backlog | Backlog | No implementation yet |
| Commerce integration | Deployment automation | Backlog | Backlog | No implementation yet |
| Connectivity map | Deployment automation | Backlog | Backlog | No implementation yet |

Do not promote `Planned` or `Backlog` based on documentation alone.
