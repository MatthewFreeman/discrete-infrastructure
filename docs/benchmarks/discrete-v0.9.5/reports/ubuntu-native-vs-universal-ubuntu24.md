# Discrete v0.9.5: Universal Linux vs Ubuntu 24.04

Дата тесту: 2026-07-31 UTC
Upstream: <https://github.com/discretecoin/discrete>
Release: <https://github.com/discretecoin/discrete/releases/tag/v.0.9.5>
Exact tag commit: `818aeb694280242c0f0472c0bca6f670e741c9a1`

## Висновок

**Рекомендований artifact для Ubuntu Server 24.04: Universal Linux amd64.**

Вимірюваної переваги Ubuntu-native, яка виправдовувала б окремий deployment path, немає:

- full cold sync до однакової висоти 4500: Ubuntu повільніша на 0.42%, тобто фактично нічия;
- CPU time: Ubuntu краща приблизно на 2%, але довірчий інтервал включає як перевагу, так і програш;
- idle CPU: практично однаковий;
- Universal стабільно використовує на 18–26% менше RSS;
- lifecycle, restart і reboot однаково успішні;
- Universal запускається і на Ubuntu 24.04, і на Debian 12; Ubuntu-native на Debian 12 не запускається.

Окрема Ubuntu compilation має лише packaging/operations переваги: artifact значно менший і використовує системні Ubuntu libraries. Це може бути корисно для distro-specific users або політики dynamic security patching, але **не є підставою підтримувати окрему deployment logic**.

## Exact artifacts

| | Ubuntu 24.04 | Universal Linux |
|---|---:|---:|
| Archive | `discrete-cli-ubuntu24.04-v.0.9.5.tar.gz` | `discrete-cli-linux-universal-v.0.9.5.tar.gz` |
| Archive SHA256 | `fbed899f7ecf5e02ae7da75c1408f5f64de0c3564a7e5a09d238cb95ce0e6875` | `32be929365fffd480ee8bfffe9c060cb7121a000b87e4a190df77bea11558cb8` |
| Archive size | 8,331,267 B | 18,861,609 B |
| Executed version | `Discrete v0.9.5.669-818aeb69` | `Discrete v0.9.5.669-818aeb69` |
| Executed `discreted` SHA256 | `7037d5aed0446419fa7f36b0ced03e51ea4c8cafc02217d66568f8bf4063d6fd` | `6296755aad63d66f80150383a2a30a15876f766fa05d68733653f0c1063ae30e` |
| `discreted` size | 3,646,640 B | 8,985,408 B |

Ubuntu archive на 55.83% менший, а Ubuntu daemon на 59.42% менший. Це реальна перевага download/disk footprint, не runtime performance.

## Що фактично відрізняється

### Ubuntu-native

- ELF `DYN`, PIE, GNU ABI, dynamically linked.
- GCC `Ubuntu 13.3.0`.
- Runtime dependencies: OpenSSL 3, `libresolv`, `libstdc++`, `libgcc_s`, glibc, loader і `libm`.
- Вимагає щонайменше `GLIBC_2.38`, `GLIBCXX_3.4.32`, `OPENSSL_3.0.0`.
- Workflow: Ubuntu 24.04 runner, `ARCH=default`, Release, IPO/LTO ON, `-O3 -DNDEBUG`, PIC.

### Universal

- ELF `EXEC`, System V ABI, fully statically linked; dynamic section відсутня, `ldd` повертає `not a dynamic executable`.
- GCC `Alpine 13.2.1` у Alpine 3.19 container.
- Workflow exports `CFLAGS=-O3 -static`, `CXXFLAGS=-O3 -static -static-libstdc++ -static-libgcc`, `LDFLAGS=-static`.
- Немає explicit IPO flag у Universal workflow job.

Root CMake для x86-64 додає `-maes`; `ARCH=default` не додає `-march=native`. Обидва binaries успішно працювали на AMD EPYC Rome з AES і AVX2. Non-AVX2 host цим тестом не покритий.

Raw ELF evidence is preserved under `outputs/raw/v0.9.5/v.0.9.5/provenance/` in the [public evidence archive](../artifacts/README.md).

Exact tagged workflow: [release.yml](../provenance/upstream/release.yml). CMake architecture/AES logic: [CMakeLists.txt](../provenance/upstream/CMakeLists.txt).

## Test host

Primary A/B host:

- Ubuntu Server 24.04.4 LTS, kernel `6.8.0-136-generic`;
- Vultr VM, Microsoft hypervisor;
- 2 vCPU reported as 1 core × 2 threads;
- `AMD EPYC-Rome Processor`, family 23, model 49, stepping 0, microcode `0x1000065`;
- AES, AVX, AVX2; no CPU-specific build was used;
- 4,100,009,984 bytes RAM, 2.34 GiB swap;
- 100 GiB virtual disk, ext4, approximately 84 GiB initially free;
- `kvm-clock`, NTP synchronized;
- nftables/bootstrap configuration was not rewritten.

Debian compatibility host:

- Debian 12, AMD EPYC Rome family/model/stepping/microcode matching the Ubuntu guest presentation;
- 1 vCPU, so it was not used for cross-OS performance claims.

## Methodology

### Cold sync

- 8 complete sync runs from fresh LMDB/genesis.
- A=Ubuntu-native, B=Universal.
- Balanced order: `A B B A | B A A B`.
- Four runs per binary.
- Same VPS, arguments, data layout, ports and common stopped `p2pstate.bin`.
- One daemon at a time; separate immutable run directories.
- `sync` plus Linux page-cache drop before every run.
- 1-second process/RPC/host sampling.
- Comparison endpoint fixed at height 4500, although live tip advanced from 4655 to 4661.
- Metrics collected from `/proc`, RPC `/getinfo`, network counters and `/sys/block/vda/stat`.

### Warm startup and idle

- Canonical stopped snapshot at height 4656.
- Top hash: `9689de6dc8809f47c3547cb5696e3979255ac4453d3b88330b53c18a5ab4810d`.
- `data.mdb` SHA256: `7459fb2adcf2d5ca08aeaddf7c81feea9d5d84d3c97ae4c3e4f7eaf492e4de74`.
- Ubuntu-produced and Universal-produced cold databases at this height were byte-identical.
- 8 runs, reverse-balanced order: `B A A B | A B B A`.
- 15-second stabilization after sync, then exact 60-second idle window.
- Four idle windows / 240 seconds per binary.
- Live chain added 6 blocks during Ubuntu windows and 5 during Universal windows.

### Lifecycle and reboot

- Nine comparative graceful `systemctl stop` operations per binary: four cold, four warm, one reboot.
- Stops were executed with active peers.
- One real OS reboot per binary with benchmark services temporarily enabled.
- After testing, both benchmark units were disabled and inactive.

Harness: [launch-daemon.sh](../reproduce/work/harness-v0.9.5/launch-daemon.sh), [monitor.sh](../reproduce/work/harness-v0.9.5/monitor.sh), [cold controller](../reproduce/work/harness-v0.9.5/run-cold-sync-series.sh), [warm controller](../reproduce/work/harness-v0.9.5/run-warm-idle-series.sh).

## Cold-sync results

Four runs per variant; `±` is sample standard deviation.

| Metric through height 4500 | Ubuntu-native | Universal | Ubuntu relative to Universal |
|---|---:|---:|---:|
| Wall time | 60.853 ± 8.489 s | 60.596 ± 8.498 s | **+0.42% slower** |
| Throughput | 80.97 blocks/s | 81.75 blocks/s | −0.95% |
| CPU user time | 43.455 s | 43.418 s | +0.09% |
| CPU system time | 0.480 s | 1.423 s | −66.3% |
| CPU total time | 43.935 s | 44.840 s | **−2.02%** |
| Average process CPU | 73.22% | 74.99% | −2.36% |
| Peak 1-second CPU | 100.59% | 100.71% | −0.12% |
| Average RSS | 83,846 kB | 66,295 kB | **+26.47%** |
| Peak RSS | 125,411 kB | 106,280 kB | **+18.00%** |
| Minor faults | 22,976 | 187,112 | −87.72% |
| Major faults | 28.0 | 15.25 | +83.61% |
| Process read bytes | 7.62 MB | 12.59 MB | −39.44% |
| Process write bytes | 61.741 MB | 61.744 MB | −0.005% |
| Host network RX | 75.14 MB | 78.14 MB | −3.85% |
| Host network TX | 1.197 MB | 1.158 MB | +3.29% |
| Mean RPC latency during sync | 20.96 ms | 22.20 ms | −5.58% |

Ключове: для wall time exact permutation test дав `p=0.971`; bootstrap 95% interval для різниці Ubuntu−Universal: `−10.12…+10.40 s`. Дані не просто не показують переваги Ubuntu — вони сумісні з великим шумом в обидва боки.

CPU total difference `−0.905 s` на 4500 blocks мала і невпевнена: bootstrap interval `−2.735…+0.765 s`, permutation `p=0.429`.

RSS difference була стабільною в усіх runs: average RSS Ubuntu−Universal `+17,551 kB`, exact permutation `p=0.0286`; peak difference `+19,131 kB`, `p=0.0286`. Через малий `n` це descriptive evidence, але separation повне.

Derived evidence: [cold per-run CSV](../analysis/ubuntu-native-vs-universal/cold-sync-per-run.csv), [cold summary JSON](../analysis/ubuntu-native-vs-universal/cold-sync-summary.json), [comparison statistics](../analysis/ubuntu-native-vs-universal/comparison-statistics.json).

## Warm startup and idle results

| Metric | Ubuntu-native | Universal | Interpretation |
|---|---:|---:|---|
| RPC ready sample | 4.379 s | 4.890 s | 1-second sampling quantization; not decisive |
| P2P init from logs | 4.008632 s | 4.008799 s | identical |
| IGD/UPnP wait | 4.003873 s | 4.004255 s | identical and dominates startup |
| Core init from logs | 2.894 ms | 3.116 ms | 0.222 ms difference, operationally zero |
| Sync detected | 6.137 s | 5.879 s | peer timing noise |
| Idle CPU | 0.0763% | 0.0805% | effectively identical |
| Idle peak 1-second CPU | 1.225% | 1.234% | identical |
| Idle average RSS | 32,999 kB | 26,839 kB | **Universal −18.7% / Ubuntu +22.95%** |
| Idle peak RSS | 33,248 kB | 27,062 kB | **Ubuntu +22.86%** |
| Idle RPC mean | 0.504 ms | 0.575 ms | Ubuntu −0.071 ms; measurable but irrelevant operationally |
| Idle RPC p95 | 0.610 ms | 0.771 ms | Ubuntu −0.161 ms; both sub-millisecond |

Idle CPU difference has permutation `p=0.943` and a bootstrap interval spanning both directions. Idle RSS again had complete separation (`p=0.0286`). Local RPC latency also separated in these runs, but the absolute gain is only 71 microseconds and does not justify packaging/deployment complexity.

Derived evidence: [warm/idle per-run CSV](../analysis/ubuntu-native-vs-universal/warm-idle-per-run.csv), [warm/idle summary JSON](../analysis/ubuntu-native-vs-universal/warm-idle-summary.json).

## Graceful stop, restart and reboot

All comparative stops:

- returned exit code 0;
- contained the `Node stopped.` marker;
- produced no SIGILL, crash, segfault or OOM marker;
- never hit the 300-second systemd timeout.

Observed stop ranges:

| Series | Ubuntu-native | Universal |
|---|---:|---:|
| Cold | 1.024–14.077 s | 0.028–11.427 s |
| Warm/idle | 0.023–6.279 s | 0.022–11.349 s |
| Post-reboot | 1.030 s | 1.029 s |

Long-tail stops occurred in both builds and correlated with live P2P teardown behavior, not with ELF/linkage type. The fixed shutdown bug no longer manifests as a hang.

Both reboot runs:

- changed kernel boot ID;
- automatically started the expected binary;
- verified `/proc/$pid/exe` SHA256;
- reached RPC and synchronized;
- ended at height 4678 with identical top hash `49e52a0c729aacd01110a409f34222e858421eb5923c1f788858fec2b8e7ce66`;
- stopped cleanly with 14–15 peers;
- left no kernel error markers.

Derived evidence: [reboot per-run CSV](../analysis/ubuntu-native-vs-universal/reboot-per-run.csv), [reboot summary JSON](../analysis/ubuntu-native-vs-universal/reboot-summary.json).

## Debian 12 compatibility

On the AMD Rome Debian 12 VPS:

- Universal exited 0 and reported `Discrete v0.9.5.669-818aeb69`.
- Ubuntu-native exited 1 before startup:
  - `GLIBCXX_3.4.32 not found`;
  - `GLIBC_2.38 not found`.
- No SIGILL/kernel crash markers appeared.

Debian compatibility evidence is preserved under `outputs/raw/v0.9.5/debian/compatibility/` in the [public evidence archive](../artifacts/README.md).

## Limitations

- One Ubuntu VPS and one CPU family: AMD EPYC Rome.
- The guest exposes 2 SMT threads of one core; results do not cover larger multi-core scaling.
- Four measured runs per variant per workload. Exact permutation/bootstraps are descriptive, not a universal performance proof.
- Live peers and live chain introduce variance. Reversed order and fixed-height comparison reduce but do not eliminate it.
- Chain was small: approximately 4,500 blocks and 71 MB. Results may not extrapolate to a multi-gigabyte historical database.
- Network and block-device counters are host-wide, not strictly per-process; SSH/system activity is included.
- RPC readiness was sampled at one-second resolution until first success.
- Intel, non-AVX2 and non-AES hosts were not tested.
- Universal static linking improves compatibility but embeds dependencies; security fixes to bundled libraries require a rebuilt release. Ubuntu dynamic linking can inherit compatible system-library security updates. This is an operational tradeoff, not a measured speed advantage.

## Deployment decision

1. Use `discrete-cli-linux-universal-v.0.9.5.tar.gz` as the default artifact on both Ubuntu 24.04 and Debian 12.
2. Keep a single deployment path with exact tag, archive SHA256 and executed-binary SHA256 verification.
3. Do not add an Ubuntu-native deployment branch based on performance; the benchmark does not support it.
4. Treat Ubuntu-native as an optional distro-integrated artifact for users who specifically prefer a smaller download and dynamic system libraries.
5. If future releases materially change compiler flags, LMDB, crypto or networking, repeat the same test rather than inheriting this conclusion blindly.

## Artifact index

- [Upstream provenance JSON](../provenance/v0.9.5-upstream.json)
- [Cold per-run CSV](../analysis/ubuntu-native-vs-universal/cold-sync-per-run.csv)
- [Warm/idle per-run CSV](../analysis/ubuntu-native-vs-universal/warm-idle-per-run.csv)
- [Reboot per-run CSV](../analysis/ubuntu-native-vs-universal/reboot-per-run.csv)
- [Comparison statistics](../analysis/ubuntu-native-vs-universal/comparison-statistics.json)
- [Full raw evidence archive](../artifacts/README.md)

Final VPS state: benchmark daemons stopped; ports 9330–9332 unused by the benchmark; both benchmark units disabled and inactive; all blockchain/run data retained; OS bootstrap left intact.
