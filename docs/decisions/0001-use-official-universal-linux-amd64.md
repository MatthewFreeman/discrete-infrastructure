# ADR 0001: Use the official Universal Linux amd64 asset

- Status: Accepted
- Date: 2026-08-01
- Scope: Discrete Linux deployments on Debian 12 and Ubuntu Server 24.04
- Evidence release: Discrete `v.0.9.5`, commit `818aeb694280242c0f0472c0bca6f670e741c9a1`

## Context

Upstream publishes separate official Ubuntu 24.04 amd64 and Universal Linux amd64 assets. A second
deployment path is justified only if the Ubuntu-native asset provides a material compatibility,
performance, memory, or lifecycle benefit on Ubuntu 24.04.

The decision was tested on the same Ubuntu VPS with balanced A/B order and matched blockchain
state, then followed by paired Universal tests on equally sized Ubuntu 24.04 and Debian 12 VPSs at
4 GiB, a 1 GiB kernel cap, and a 512 MiB kernel cap. Tests included repeated cold/warm runs,
steady idle windows, active-peer graceful stops, restarts, and real reboots.

## Decision

Use the exact official Universal Linux amd64 asset through one Linux deployment path for both
supported distributions. Verify the release tag, archive SHA256, reported version, and executed
binary SHA256 during qualification and deployment.

Do not create or maintain a performance-motivated Ubuntu-native branch. Ubuntu-native remains a
valid optional upstream artifact for users who specifically want its smaller download and dynamic
system-library integration, but it is not this repository's deployment default.

Retain 1 GiB as the production RAM minimum. Universal worked under `mem=512M` on both tested
systems, but that is boundary evidence for the current chain and workload, not sufficient lifetime
headroom. If operation at that boundary is unavoidable, prefer Debian 12.

Do not add a global Debian THP override from this benchmark. `madvise` lowered RSS and improved some
1 GiB headroom measurements, but direct interleaved testing found additional CPU cost without a
wall-time improvement. At 512 MiB both kernels selected `THP=never` and did not need the override.

## Evidence

- Ubuntu-native had no decisive sync, CPU, startup, idle, RPC, stop, restart, or reboot advantage.
- Universal used 18--26% less RSS than Ubuntu-native in the Ubuntu A/B.
- Ubuntu-native required newer glibc/libstdc++ and did not start on Debian 12; Universal did.
- Cross-OS Universal wall time and responsiveness had no reproducible winner.
- At 512 MiB, both systems completed 24 main runs and two reboot cycles per VPS without OOM,
  SIGILL, crash, or lifecycle failure; Debian retained 66--80 MiB more `MemAvailable`.

Full reports, curated analysis, and raw evidence are indexed in the
[v0.9.5 benchmark suite](../benchmarks/discrete-v0.9.5/README.md).

## Consequences

- One release-selection and deployment path is easier to audit, test, roll back, and automate.
- Static Universal binaries do not automatically inherit system-library security fixes; a rebuilt
  upstream release is required when bundled dependencies need an update.
- Universal archives and binaries are larger than Ubuntu-native.
- The decision does not claim that Debian is universally faster or that 512 MiB is permanently
  adequate.

## Revalidation triggers

Repeat provenance and lifecycle validation for every adopted release. Repeat the comparative
benchmark when upstream materially changes compiler/linker flags, architecture requirements,
cryptography, LMDB/storage, networking, dependency strategy, or shutdown behavior; when supported
CPU/OS targets change; or when chain growth materially changes memory/I/O pressure.
