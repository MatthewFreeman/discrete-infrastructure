# Discrete benchmarks

This directory contains measurement-backed deployment decisions and their reproducible evidence.
Benchmark results are versioned by the exact upstream release; moving branches and locally rebuilt
binaries are not accepted as substitutes for release provenance.

## Published suites

| Release | Decision | Reports and evidence |
|---|---|---|
| Discrete `v.0.9.5` | Use the official Universal Linux amd64 asset on Debian 12 and Ubuntu 24.04 | [Benchmark suite](discrete-v0.9.5/README.md) |

The corresponding architecture decision is
[ADR 0001: use the official Universal Linux amd64 asset](../decisions/0001-use-official-universal-linux-amd64.md).

These results describe the tested release, hosts, blockchain state, and live-network conditions.
They are evidence for a deployment decision, not a permanent performance guarantee for later
releases or different hardware.
