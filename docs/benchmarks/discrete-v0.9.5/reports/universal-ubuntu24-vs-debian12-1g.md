# Discrete v0.9.5 Universal: Ubuntu 24.04 проти Debian 12 при 1 GiB RAM

Дата завершення: 2026-07-31 (America/Los_Angeles)

## Остаточний висновок

Для Universal-збірки Discrete v0.9.5 на VPS з 1 GiB RAM Ubuntu 24.04 не має переваги. Навпаки, Debian 12 у перевіреній конфігурації залишає більше системної доступної пам'яті та споживає трохи менше CPU на блок, не програючи за доведеним wall time, startup, idle, RPC або lifecycle.

Попередній висновок на користь Ubuntu був хибним, бо спирався переважно на RSS процесу `discreted`. На Ubuntu RSS daemon справді нижчий зі штатним `THP=madvise`, але вся Ubuntu-система використовує більше пам'яті. Для VPS з малою RAM правильна метрика — `MemAvailable` і pressure/reclaim/swap/OOM усієї системи, а не RSS одного процесу.

Практична рекомендація:

- для 1-GiB VPS з поточним blockchain state: **Debian 12 + Universal v0.9.5**;
- штатний Debian `THP=always` уже має достатній запас і не потребує патча;
- опціональний `THP=madvise` на Debian дає ще приблизно 25–41 MiB worst-case `MemAvailable`, але коштує близько 1.59% CPU на блок;
- навіть з `madvise` Debian у цьому тесті залишився приблизно на 1.66% економнішим за Ubuntu за CPU/block;
- окремий Ubuntu-native deployment path усе ще не виправданий.

## Provenance

На обох ОС запускався один і той самий офіційний static Universal-бінарник:

| Поле | Значення |
|---|---|
| Release | `v.0.9.5` |
| Tagged commit | `818aeb694280242c0f0472c0bca6f670e741c9a1` |
| Asset | `discrete-cli-linux-universal-v.0.9.5.tar.gz` |
| Archive SHA256 | `32be929365fffd480ee8bfffe9c060cb7121a000b87e4a190df77bea11558cb8` |
| Executed version | `Discrete v0.9.5.669-818aeb69` |
| Binary SHA256 | `6296755aad63d66f80150383a2a30a15876f766fa05d68733653f0c1063ae30e` |
| ELF Build ID | `5f4075f2aab7b402e6858f652a992b681700af85` |

Upstream evidence: [`../provenance/v0.9.5-upstream.json`](../provenance/v0.9.5-upstream.json).

## Як отримано 1 GiB без CPU-лотереї хостера

Нові дешеві VPS могли потрапити на різні покоління EPYC і зіпсувати A/B. Тому використано вже вирівняні VPS:

- 2 vCPU;
- `AMD EPYC-Rome Processor`;
- family 23, model 49, stepping 0;
- microcode `0x1000065`;
- однакові CPU flags;
- 100 GB NVMe;
- Ubuntu kernel 6.8 та Debian kernel 6.1.

На обох тимчасово додано kernel boot parameter `mem=1G`. Після reboot:

| Host | `MemTotal` | Swap |
|---|---:|---:|
| Ubuntu 24.04 | 983,356 KiB | 2,457,596 KiB |
| Debian 12 | 982,636 KiB | 2,457,596 KiB |

Різниця видимої RAM — лише 720 KiB. Swap був однаковим і порожнім на старті. Після тестів `mem=1G` видалено, GRUB перевірено, обидві VPS перезавантажено назад у приблизно 4-GiB режим.

## Метод

Виконано 48 daemon runs:

- 6 paired cold runs зі штатними THP: Ubuntu `madvise`, Debian `always`;
- 6 paired warm/idle runs зі штатними THP;
- 6 paired cold runs з `madvise` на обох ОС;
- 6 paired warm/idle runs з `madvise` на обох ОС.

Кожна пара містить один Ubuntu і один Debian run. Порядок старту чергувався: три Ubuntu-first і три Debian-first у кожній серії.

Умови:

- той самий binary SHA256 і конфіг;
- cold runs — порожній blockchain state, однаковий P2P seed, target height 4500;
- warm runs — однаковий canonical snapshot h4656, live height/hash barrier і 120 секунд idle;
- page cache очищувався перед запуском;
- inbound peers: 0;
- два daemon не ділили data directory або порти;
- щосекунди збиралися process CPU/RSS/faults/I/O, `MemAvailable`, cache, swap, reclaim counters, `oom_kill` і PSI;
- статистика: paired Ubuntu-minus-Debian, exact sign-flip test і exact paired bootstrap CI по всіх `6^6` resamples.

## Результат зі штатними THP

### Cold sync

| Метрика, mean | Ubuntu | Debian | Висновок |
|---|---:|---:|---|
| Normalized wall до h4500 | 62.039 s | 62.617 s | різниця не доведена; CI −7.08…+5.80 s |
| CPU / block | 10.508 ms | 10.177 ms | Debian −3.25%; усі 6 пар одного знаку |
| Process average RSS | 59,899 KiB | 67,381 KiB | Ubuntu process нижчий |
| Process peak RSS | 90,476 KiB | 106,751 KiB | Ubuntu process нижчий |
| System mean `MemAvailable` | 634,816 KiB | 661,967 KiB | **Debian +27,151 KiB** |
| System minimum `MemAvailable` | 601,963 KiB | 630,503 KiB | **Debian +28,540 KiB** |

### Warm resume та 120-second idle

| Метрика, mean | Ubuntu | Debian | Висновок |
|---|---:|---:|---|
| First RPC | 4.231 s | 4.233 s | однаково |
| Sync-ready | 7.792 s | 7.955 s | різниця не доведена |
| Idle process CPU / 120 s | 0.097 s | 0.095 s | однаково |
| Idle process average RSS | 30,083 KiB | 53,125 KiB | Ubuntu process нижчий |
| Lifetime process HWM | 36,307 KiB | 61,630 KiB | Ubuntu process нижчий |
| System mean `MemAvailable` | 651,997 KiB | 666,943 KiB | **Debian +14,946 KiB** |
| System minimum `MemAvailable` | 622,242 KiB | 652,119 KiB | **Debian +29,877 KiB** |
| RPC mean | 0.583 ms | 0.551 ms | 0.032 ms різниці, практично несуттєво |

Ключовий факт: нижчий RSS daemon на Ubuntu не означає більший запас RAM VPS. Debian мав більше `MemAvailable` у всіх шести cold і всіх шести warm парах.

## Debian `THP=madvise`

Після тимчасового перемикання Debian на `madvise` обидві ОС мали однакову THP policy.

### Cross-OS при однаковому `madvise`

| Метрика | Ubuntu | Debian | Висновок |
|---|---:|---:|---|
| Cold normalized wall | 60.903 s | 57.545 s | різниця не доведена; CI перетинає 0 |
| Cold CPU / block | 10.354 ms | 10.185 ms | Debian −1.66% |
| Cold peak RSS | 88,695 KiB | 88,789 KiB | однаково |
| Cold mean `MemAvailable` | 632,412 KiB | 675,347 KiB | Debian +42,936 KiB |
| Cold minimum `MemAvailable` | 598,908 KiB | 652,779 KiB | Debian +53,871 KiB |
| Warm idle average RSS | 30,613 KiB | 30,445 KiB | однаково |
| Warm mean `MemAvailable` | 646,014 KiB | 695,681 KiB | Debian +49,668 KiB |
| Warm minimum `MemAvailable` | 615,454 KiB | 686,741 KiB | Debian +71,287 KiB |

### Причинний ефект `madvise − always` на Debian

Ефект скориговано на зміну одночасної Ubuntu-control між двома серіями:

| Метрика | Скоригований ефект | Висновок |
|---|---:|---|
| Cold wall time | −3.94 s | не доведено; CI −13.46…+5.16 s |
| CPU / block | +0.162 ms, **+1.59%** | відтворюваний CPU-компроміс |
| Cold peak RSS | −16,181 KiB, −15.16% | відтворюване зменшення |
| Cold minimum `MemAvailable` | +25,331 KiB | напрям корисний; exact p=0.0625 |
| Warm idle average RSS | −23,209 KiB, −43.69% | відтворюване зменшення |
| Warm minimum `MemAvailable` | +41,409 KiB, +6.35% | відтворюване збільшення |

Отже, на 1 GiB `madvise` вже дає не лише красивіший process RSS, а й реальний додатковий системний запас. Але current workload не створює memory pressure навіть зі штатним `always`, тому це опціональна future-headroom настройка, а не необхідний fix.

## Memory pressure

У всіх 48 daemon runs:

- maximum swap used: 0;
- `pswpin`/`pswpout`: 0;
- `pgscan_kswapd`/`pgscan_direct`: 0;
- OOM kills: 0;
- memory PSI: фактично 0;
- найнижчий зафіксований `MemAvailable` у native cold series: 589,620 KiB.

Тобто при перевіреній висоті/розмірі blockchain 1 GiB не є граничною конфігурацією. Вона має понад пів гігабайта запасу на обох ОС.

## Stop, restart та reboot

На обох VPS виконано два reboot-цикли з enabled daemon/monitor та активними peers:

- після кожного reboot з'явився новий boot ID;
- `mem=1G` залишився активним;
- daemon автоматично стартував;
- blockchain height збігався;
- 8–9 outgoing peers, inbound 0;
- swap usage 0;
- final graceful stop 0;
- fatal patterns 0;
- services після cleanup disabled/inactive;
- `current.env` відновлено byte-identical;
- процесів і тестових listeners після cleanup немає.

Raw reboot evidence is preserved under `outputs/cross-os-1g-v0.9.5/raw/reboot` in the [public evidence archive](../artifacts/README.md).

## Обмеження

- `mem=1G` точно обмежує видиму ядру RAM і зберігає однаковий CPU, але це не повна емуляція окремого 1-GiB тарифу хостера з іншим hypervisor placement або I/O shaping.
- Live P2P network створює wall-time noise; paired simultaneous runs, однаковий state і чергування start order його зменшують, але не усувають.
- Ubuntu та Debian мають різні production kernels; результат порівнює реальні ОС, а не ізольований userspace.
- Blockchain state під час тесту був приблизно h4500–4853. Майбутнє зростання LMDB/state може змінити memory profile; цей тест не доводить довічну придатність 1 GiB.
- Перевірено AMD EPYC Rome. Intel та інші CPU не входять у цей висновок.
- Exact p-value при шести парах має мінімальний двосторонній крок `0.03125`; малі відмінності не слід переінтерпретувати.

## Evidence

- Native and `madvise` raw cold/warm series: [public evidence archive](../artifacts/README.md), under `outputs/cross-os-1g-v0.9.5/raw/`.
- Per-run native cold: [`cold-per-run.csv`](../analysis/universal-cross-os-1g/cold-per-run.csv).
- Per-run `madvise` cold: [`cold-madvise-per-run.csv`](../analysis/universal-cross-os-1g/cold-madvise-per-run.csv).
- Per-run native warm: [`warm-per-run.csv`](../analysis/universal-cross-os-1g/warm-per-run.csv).
- Per-run `madvise` warm: [`warm-madvise-per-run.csv`](../analysis/universal-cross-os-1g/warm-madvise-per-run.csv).
- Paired and causal statistics: [`comparison-statistics.json`](../analysis/universal-cross-os-1g/comparison-statistics.json).
- Reproducible analyzer: [`analyze_crossos_1g.py`](../reproduce/work/analysis/analyze_crossos_1g.py).

Пов'язаний 4-GiB cross-OS report: [`universal-ubuntu24-vs-debian12-4g.md`](universal-ubuntu24-vs-debian12-4g.md).

GitHub, release assets, package publishing і production bootstrap не змінювалися.
