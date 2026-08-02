# Discrete v0.9.5 Universal на Ubuntu 24.04 і Debian 12 при 512 MiB

Дата тесту: 31 липня — 1 серпня 2026 року (UTC).

## Висновок

**Так: офіційна Universal-збірка Discrete v0.9.5 фактично працює і на Ubuntu Server 24.04, і на Debian 12 при kernel cap `mem=512M`.** Усі 24 основні запуски (6 cold + 6 warm на кожній ОС) та по два reboot-цикли на кожній VPS завершилися без crash, SIGILL, OOM або lifecycle failure.

Але рівноцінними ці ОС при такому обмеженні назвати не можна:

- швидкість ноди, daemon RSS, network throughput і RPC практично однакові;
- Debian залишає системі приблизно на 66 MiB більше `MemAvailable` під cold sync і на 80 MiB більше під warm idle;
- абсолютний найгірший зафіксований запас становив 200.3 MiB на Ubuntu і 274.5 MiB на Debian у cold runs;
- Debian мав значно менше host-wide block reads; це перевага всієї ОС/host workload, а не доведена різниця в коді `discreted`;
- у виміряних cold/warm вікнах не було swap-in/out узагалі. Під час reboot-validation Ubuntu мала 780–1036 KiB зайнятого swap, Debian — 0.

Практична рекомендація для VPS класу 512 MiB: **Debian 12 + офіційна Universal-збірка**. Ubuntu 24.04 теж працює, але витрачає помітно більше дефіцитної системної пам'яті й не компенсує це end-to-end швидкістю.

512 MiB не варто оголошувати безумовним production minimum лише за цим тестом. Це підтверджена працездатність для поточного blockchain state, поточного набору peers і наявного swap. Для запасу під ріст chain, оновлення ОС, логування та довший soak розумнішим мінімумом лишається 1 GiB.

## Точний артефакт

На обох VPS у кожному запуску використовувався один і той самий офіційний binary:

| Поле | Значення |
|---|---|
| Release | `v.0.9.5` |
| Tagged commit | `818aeb694280242c0f0472c0bca6f670e741c9a1` |
| Asset | `discrete-cli-linux-universal-v.0.9.5.tar.gz` |
| Archive SHA256 | `32be929365fffd480ee8bfffe9c060cb7121a000b87e4a190df77bea11558cb8` |
| Executed version | `Discrete v0.9.5.669-818aeb69` |
| Binary SHA256 | `6296755aad63d66f80150383a2a30a15876f766fa05d68733653f0c1063ae30e` |

Очікуваний binary SHA записаний у 26 незалежних `host-pre-run.txt` / `host-pre-reboot.txt` файлах. Рухомий `master`, власні компіляції та Ubuntu-native asset у цьому cross-OS тесті не використовувалися.

## Умови

| Параметр | Ubuntu | Debian |
|---|---:|---:|
| ОС / kernel | Ubuntu 24.04, `6.8.0-136-generic` | Debian 12, `6.1.0-50-amd64` |
| vCPU | 2 | 2 |
| CPU | AMD EPYC-Rome, family 23 model 49 stepping 0 | те саме |
| CPU flags | AES, AVX, AVX2, SHA-NI та інші — однакові | однакові |
| Physical RAM VPS | 4 GB | 4 GB |
| Активне обмеження | kernel `mem=512M` | kernel `mem=512M` |
| Фактичний `MemTotal` | 468,024 KiB (457.1 MiB) | 467,304 KiB (456.4 MiB) |
| Swap | 2,457,596 KiB | 2,457,596 KiB |
| THP під 512 MiB | `never` | `never` |

Обидва ядра автоматично виставили Transparent Huge Pages у `never`. Тому окремий Debian `madvise` follow-up при 512 MiB не створив би іншої тестової умови й не проводився.

Це були дві окремі VPS з однаковою видимою CPU-моделлю, family/model/stepping, microcode і flags. Це суттєво чистіше за порівняння різних CPU, але не доводить, що провайдер розмістив їх на одному фізичному EPYC або однаково завантажених hypervisor/storage nodes.

## Методика

- 6 одночасних cold-пар із порожнім versioned data directory та контрольним sync до висоти понад 4500;
- 6 одночасних warm-пар з побайтово перевіреним canonical snapshot height 4656;
- порядок старту чергувався Ubuntu-first / Debian-first;
- у warm-парах вимірювальне вікно відкривалося лише після двох послідовних збігів live height і top hash;
- кожна warm-пара містила 120 секунд steady/idle;
- `hide-my-port=yes`: приймалися тільки runs з outgoing peers і нульовими incoming peers;
- на одній VPS ніколи не працювали два daemon одночасно й data directories не ділилися;
- кожен run збирав process CPU/RSS/faults/context switches, process I/O, host block/network counters, `MemAvailable`, swap/reclaim/OOM, PSI та RPC latency;
- після кожного run виконувався graceful `systemctl stop`;
- окремо перевірено два reboot-цикли, включно з stop → restart → active peers → reboot у другому циклі;
- висновок не базується на одному короткому запуску.

Статистика нижче — paired Ubuntu-minus-Debian. Для шести пар використано exact paired bootstrap 95% CI по всіх `6^6` resamples та exact two-sided sign-flip test по всіх `2^6` assignments. При `n=6` найменше можливе двостороннє `p` дорівнює 0.03125; ці значення не треба перетворювати на магічний доказ причинності.

## Cold sync

| Метрика, середнє 6 runs | Ubuntu | Debian | Ubuntu − Debian | Оцінка |
|---|---:|---:|---:|---|
| Wall time до target | 64.143 s | 62.662 s | +1.481 s | CI перетинає 0, `p=0.781`; переможця нема |
| CPU на observed block | 10.428 ms | 10.229 ms | +1.94% | невеликий сигнал на користь Debian, `p=0.0625` |
| Process RSS, середнє | 60,057 KiB | 58,991 KiB | +1,065 KiB | практично однаково |
| Process peak RSS | 89,037 KiB | 88,145 KiB | +892 KiB | CI перетинає 0 |
| `MemAvailable`, середнє | 237,722 KiB | 300,743 KiB | −63,021 KiB | стабільна перевага Debian |
| Середнє per-run minimum `MemAvailable` | 217,630 KiB | 285,601 KiB | −67,971 KiB (−66.4 MiB) | `p=0.03125` |
| RPC mean | 21.987 ms | 21.664 ms | +0.324 ms | різниці нема |
| Graceful stop | 1.060 s | 1.058 s | +0.002 s | різниці нема |

Абсолютний minimum `MemAvailable` серед усіх cold samples:

- Ubuntu: 205,144 KiB (200.3 MiB);
- Debian: 281,092 KiB (274.5 MiB).

В усіх 12 cold runs: `pswpin=0`, `pswpout=0`, `pgscan_kswapd=0`, `pgscan_direct=0`, `oom_kill=0`; memory PSI був фактично нульовим.

## Warm startup та 120-second idle

| Метрика, середнє 6 runs | Ubuntu | Debian | Ubuntu − Debian | Оцінка |
|---|---:|---:|---:|---|
| First RPC | 4.308 s | 4.380 s | −0.072 s | Ubuntu швидша на 72 ms; вимірювано, але операційно дріб'язково |
| Sync-ready | 8.471 s | 8.186 s | +0.286 s | CI торкається 0, доведеного переможця нема |
| Idle CPU, % одного core | 0.0686% | 0.0645% | +0.0041 pp | абсолютна різниця мізерна |
| Idle RSS, середнє | 31,091 KiB | 31,174 KiB | −84 KiB | однаково |
| Idle `MemAvailable`, середнє | 254,567 KiB | 319,386 KiB | −64,819 KiB | Debian легший як система |
| Середнє per-run idle minimum `MemAvailable` | 234,140 KiB | 315,592 KiB | −81,452 KiB (−79.5 MiB) | `p=0.03125` |
| Idle RPC mean | 0.531 ms | 0.502 ms | +0.029 ms | статистично послідовно, практично несуттєво |
| Idle RPC p95 | 0.677 ms | 0.668 ms | +0.009 ms | різниці нема |

Абсолютний minimum `MemAvailable` за повний lifetime warm runs:

- Ubuntu: 226,700 KiB (221.4 MiB);
- Debian: 309,756 KiB (302.5 MiB).

Ubuntu мала 12 KiB уже зайнятого swap у warm samples, але `pswpin` і `pswpout` не змінилися в жодному run. Це не swap activity ноди. В обох ОС `pgscan`, `pgsteal` і `oom_kill` залишилися нульовими.

## Disk і network

| Host-wide метрика | Ubuntu | Debian | Коментар |
|---|---:|---:|---|
| Cold block read IOPS | 13.00 | 2.18 | Ubuntu вища в усіх парах |
| Cold block reads | 0.302 MiB/s | 0.047 MiB/s | `p=0.03125` |
| Warm idle block read IOPS | 5.03 | 0.17 | Ubuntu вища в усіх парах |
| Warm idle block reads | 0.134 MiB/s | 0.0037 MiB/s | `p=0.03125` |
| Cold network RX | 806.66 KiB/s | 806.62 KiB/s | однаково |
| Cold network TX | 12.70 KiB/s | 12.66 KiB/s | однаково |
| Warm network RX | 2.24 KiB/s | 2.29 KiB/s | однаково |
| Warm network TX | 2.53 KiB/s | 2.52 KiB/s | однаково |

Block counters зняті з однаково визначеного root device `vda`, але вони host-wide: сюди входять kernel та всі системні сервіси, не лише `discreted`. Тому це валідний аргумент, що конкретна Debian VPS мала легший storage workload, але не доказ, що Universal binary виконує інший обсяг логічного I/O на Debian.

## Stop, restart і reboot

Усі cold/warm runs мали `stop_rc=0`, outgoing peers перед stop і `fatal_pattern_matches=0`.

| Reboot validation | Ubuntu | Debian |
|---|---:|---:|
| Нових унікальних boot IDs | 2 | 2 |
| Cycle 1 RPC/peers | height 4764, 2 outgoing | height 4887, 8 outgoing |
| Cycle 2 RPC/peers | height 4887, 8 outgoing | height 4887, 8 outgoing |
| `MemAvailable` cycle 1 / 2 | 237,664 / 258,508 KiB | 317,404 / 336,732 KiB |
| Swap used cycle 1 / 2 | 780 / 1036 KiB | 0 / 0 KiB |
| Final graceful stop | success | success |
| Crash/SIGILL/fatal pattern | 0 | 0 |

Cycle 2 включав контрольований graceful stop, повторний `mem=512M` arm, restart до активного RPC/peers і reboot активної ноди. Після тесту обидві VPS повернуті до штатного 4-GB boot; тимчасовий GRUB drop-in і rollback unit/scripts видалені, benchmark services disabled/inactive, daemon і benchmark ports відсутні, попередні `current.env` та harness відновлені побайтово/SHA256.

Обмеження reboot-даних: monitor писав TSV у `/run`, а cleanup зупинив його одразу після daemon, не давши виконати фінальний copy у result directory. Тому для reboot є boot IDs, RPC, peers, `MemAvailable`, swap snapshots, systemd/journal/dmesg і lifecycle result, але немає секундних VM deltas. Це instrumentation bug; він не приховується у висновку.

## Crash і CPU compatibility

Пошук по всіх зібраних `.log` і `.txt` не знайшов `OOM`, `Killed process`, `SIGILL`, illegal instruction, segfault, core dump або kernel panic. Обидві VPS експонували однакові AES/AVX2/SHA-NI flags, і binary відпрацював усі runs стабільно.

## Межі висновку

- `mem=512M` — kernel cap на 4-GB VPS, а не окремий тариф провайдера з фізичними 512 MiB; фактичний `MemTotal` був близько 456–457 MiB.
- На обох VPS лишався swap 2.34 GiB. Cold/warm runs його не використовували, але Ubuntu використала близько 1 MiB після reboot.
- Chain height під час тесту був приблизно 4502–4887. Майбутній blockchain state може вимагати більше RAM/disk cache.
- Idle-вікно тривало 120 секунд, а не дні. Це boundary validation, не довгий production soak.
- Incoming peers були навмисно відсутні; перевірено outgoing peer workload.
- Live P2P network створює шум у wall time, тому CPU/block, matched warm barrier і повтори важливіші за один stopwatch result.
- Дві VPS мали однакову видиму CPU-конфігурацію, але фізичний host і його сусіди невідомі.

## Відтворення та сирі результати

- [`cold-per-run.csv`](../analysis/universal-cross-os-512m/cold-per-run.csv) — 12 cold runs;
- [`warm-per-run.csv`](../analysis/universal-cross-os-512m/warm-per-run.csv) — 12 warm runs;
- [`comparison-statistics.json`](../analysis/universal-cross-os-512m/comparison-statistics.json) — усі paired summaries;
- [`reboot-validation.json`](../analysis/universal-cross-os-512m/reboot-validation.json) — reboot acceptance evidence;
- [`raw-file-sha256.txt`](../analysis/universal-cross-os-512m/raw-file-sha256.txt) — SHA256 manifest 862 sanitized raw-файлів;
- [public evidence archive](../artifacts/README.md) — metadata, logs, TSV, RPC, systemd, dmesg, smaps/status і snapshot checks under `outputs/cross-os-512m-v0.9.5/raw/`;
- analyzer: [`analyze_crossos_512m.py`](../reproduce/work/analysis/analyze_crossos_512m.py).

Команда повторного аналізу з кореня workspace:

```powershell
python .\work\analysis\analyze_crossos_512m.py
```

GitHub, release assets, package publishing і завершений VPS bootstrap не змінювалися.
