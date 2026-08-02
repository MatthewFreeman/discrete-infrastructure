# Discrete v0.9.5 Linux validation and benchmarks

This suite records the completed comparison of the two official Linux amd64 release assets and the
follow-up validation of the Universal asset on Ubuntu Server 24.04 and Debian 12.

## Decision

Use `discrete-cli-linux-universal-v.0.9.5.tar.gz` through one Linux deployment path.

- The Ubuntu-native build had no measured sync, startup, idle, RPC, or lifecycle advantage that
  justified a separate deployment path.
- Universal used less daemon RSS than Ubuntu-native on Ubuntu 24.04 and ran on both supported
  distributions. Ubuntu-native did not run on Debian 12 because its required glibc/libstdc++
  versions were unavailable.
- Universal had no reproducible end-to-end performance winner between Ubuntu 24.04 and Debian 12.
- Both operating systems worked under a `mem=512M` kernel cap, but Debian retained 66--80 MiB more
  `MemAvailable`. Prefer Debian at that boundary and retain 1 GiB as the production minimum.
- Do not impose a repository-wide Debian THP override from these results. `madvise` reduced RSS but
  also added CPU cost in direct testing, and the low-memory tests did not require it.

See [ADR 0001](../../decisions/0001-use-official-universal-linux-amd64.md) for the operational
decision and revalidation triggers.

## Exact upstream provenance

| Field | Value |
|---|---|
| Release/tag | `v.0.9.5` |
| Tagged commit | `818aeb694280242c0f0472c0bca6f670e741c9a1` |
| Ubuntu asset | `discrete-cli-ubuntu24.04-v.0.9.5.tar.gz` |
| Ubuntu archive SHA256 | `fbed899f7ecf5e02ae7da75c1408f5f64de0c3564a7e5a09d238cb95ce0e6875` |
| Universal asset | `discrete-cli-linux-universal-v.0.9.5.tar.gz` |
| Universal archive SHA256 | `32be929365fffd480ee8bfffe9c060cb7121a000b87e4a190df77bea11558cb8` |
| Ubuntu `discreted` SHA256 | `7037d5aed0446419fa7f36b0ced03e51ea4c8cafc02217d66568f8bf4063d6fd` |
| Universal `discreted` SHA256 | `6296755aad63d66f80150383a2a30a15876f766fa05d68733653f0c1063ae30e` |

The machine-readable record and tagged build inputs are under [provenance](provenance/).

## Reports

1. [Ubuntu-native vs Universal on Ubuntu 24.04](reports/ubuntu-native-vs-universal-ubuntu24.md)
2. [Universal on Ubuntu 24.04 vs Debian 12 at 4 GiB](reports/universal-ubuntu24-vs-debian12-4g.md)
3. [Universal on Ubuntu 24.04 vs Debian 12 at 1 GiB](reports/universal-ubuntu24-vs-debian12-1g.md)
4. [Universal on Ubuntu 24.04 vs Debian 12 at 512 MiB](reports/universal-ubuntu24-vs-debian12-512m.md)

The reports preserve the complete methodology, measurements, statistical treatment, lifecycle
checks, limitations, and final VPS state. Curated CSV/JSON outputs are under [analysis](analysis/).

## Full raw evidence

The deterministic, privacy-sanitized evidence bundle is documented under
[artifacts](artifacts/README.md). It contains 6,067 UTF-8 payload files: raw logs and samples,
derived outputs, harnesses, analyzers, reports, and the exact tagged workflow/CMake inputs.

The archive intentionally contains no Discrete binaries, release archives, SSH private keys,
credentials, or real host/network identifiers. Numeric measurements, release hashes, binary hashes,
block hashes, and benchmark structure are preserved.

## Reproduction

Use [the reproduction guide](reproduce/README.md) to verify the archive, rerun the analyzers, or
rebuild the sanitized archive from the retained private workspace.

## Important limits

- The tests used AMD EPYC Rome guest CPU presentation; Intel and non-AES/non-AVX2 hosts were not
  tested.
- The 512 MiB and 1 GiB conditions used kernel memory caps on 4 GiB VPS instances, not separate
  provider plans. CPU presentation remained stable, but physical host placement was unknown.
- The 512 MiB tests retained 2.34 GiB swap. Cold/warm runs did not swap, but Ubuntu used about 1 MiB
  after reboot validation.
- The observed chain was approximately height 4,500--4,887. Future chain growth can change memory
  and I/O behavior.
- Live peers and shared-host counters introduce noise. Paired runs, balanced order, matched state,
  fixed-height endpoints, and repetition reduce that noise but cannot remove it.
- The 512 MiB reboot monitor lost its per-second TSV during cleanup; boot IDs, systemd/journal,
  RPC, peers, memory/swap snapshots, and lifecycle results remain available.
