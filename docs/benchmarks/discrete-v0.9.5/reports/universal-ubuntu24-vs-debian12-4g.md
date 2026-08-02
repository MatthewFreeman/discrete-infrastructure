# Discrete v0.9.5 Universal: Ubuntu 24.04 проти Debian 12

Дата завершення тесту: 2026-07-31

## Висновок

Одна й та сама офіційна Universal-збірка Discrete v0.9.5 не має відтворюваного переможця за фактичним часом синхронізації, startup/sync-ready, idle-навантаженням, RPC-затримкою або lifecycle-стабільністю між Ubuntu Server 24.04 і Debian 12.

- Debian споживав приблизно на 1.4–3.3% менше process CPU на блок, але це не перетворилося на швидшу синхронізацію за wall time.
- Ubuntu з нативним `THP=madvise` мала значно менший RSS, ніж Debian з нативним `THP=always`.
- Після однакового `THP=madvise` різниця RSS практично зникла: це ефект kernel THP policy, а не різних Universal-бінарників чи «важчого Debian».
- Примусове `THP=madvise` на Debian не є безкоштовною оптимізацією: у прямому interleaved-тесті воно зменшило RSS, але збільшило CPU на блок приблизно на 2.31%, не покращивши wall time.
- Graceful stop, restart та два reboot-цикли пройшли на обох ОС без падінь, зависань або пошкодження стану.

Практичне рішення:

- якщо питання сформульоване як «де Universal швидше?» — доказів переваги жодної ОС немає;
- Debian 12 зі штатним `THP=always` має невелику CPU/block перевагу;
- нижчий process RSS на Ubuntu сам по собі не доводить кращу системну RAM-поведінку; подальший 1-GiB тест із `MemAvailable`, PSI, reclaim і swap показав більший фактичний запас пам'яті на Debian;
- для 4 GiB обидві ОС мають великий запас, тому переходити між ними лише заради цих відмінностей немає сенсу;
- окремий deployment path для Ubuntu-native збірки не виправданий: попередній A/B цієї ж версії вже показав, що Universal на Ubuntu не поступається Ubuntu-native.

## Точна provenance

Тестувався один офіційний tagged release та один і той самий фактично запущений бінарник на обох VPS:

| Поле | Значення |
|---|---|
| Release | `v.0.9.5` |
| Tagged commit | `818aeb694280242c0f0472c0bca6f670e741c9a1` |
| Asset | `discrete-cli-linux-universal-v.0.9.5.tar.gz` |
| SHA256 archive | `32be929365fffd480ee8bfffe9c060cb7121a000b87e4a190df77bea11558cb8` |
| Archive size | 18,861,609 bytes |
| Executed version | `Discrete v0.9.5.669-818aeb69` |
| SHA256 binary | `6296755aad63d66f80150383a2a30a15876f766fa05d68733653f0c1063ae30e` |
| Binary size | 8,985,408 bytes |
| ELF | static amd64 executable |
| ELF Build ID | `5f4075f2aab7b402e6858f652a992b681700af85` |

Upstream-знімок: [`../provenance/v0.9.5-upstream.json`](../provenance/v0.9.5-upstream.json).

## Умови тесту

Обидві VPS мали 2 vCPU, 4 GiB RAM, 100 GB NVMe та однаково видимий AMD EPYC Rome CPU model/flags. Ubuntu працювала на kernel 6.8, Debian — на kernel 6.1. Це навмисно реальні цільові ОС, а не спроба зробити ядра штучно однаковими.

Для кожної синхронної пари:

- використовувався той самий Universal-бінарник і той самий конфігураційний шаблон;
- стартовий blockchain/P2P state був однаковим у межах сценарію;
- демони запускалися одночасно на окремих VPS;
- cold-серії починалися з порожнього blockchain state та завершувалися на контрольній висоті 4500;
- warm-серії відновлювалися з одного canonical snapshot висоти 4656 та переходили у 120-секундне idle-вікно;
- перед cold-запуском очищувався page cache;
- два демони ніколи не ділили один data directory або ті самі порти;
- для кожного запуску зберігалися SHA256, version, systemd result, stop code, fatal-pattern count і метрики процесу.

Першу warm-пару з barrier timeout збережено як raw evidence, але виключено зі статистики. Усі наведені нижче серії містять по шість валідних пар, якщо прямо не зазначено інше.

## Cold sync

### Нативні kernel defaults

Ubuntu мала `THP=madvise`, Debian — `THP=always`.

| Метрика, mean | Ubuntu 24.04 | Debian 12 | Результат |
|---|---:|---:|---|
| Normalized wall time до h4500 | 60.725 s | 58.660 s | різниця не доведена; paired CI перетинає 0 |
| Process CPU / observed block | 10.460 ms | 10.126 ms | Debian −3.30%; усі 6 пар одного знаку |
| Average RSS | 59,535 KiB | 64,999 KiB | Ubuntu −8.41% |
| Peak RSS | 89,391 KiB | 106,795 KiB | Ubuntu −16.30% |

Сира серія `outputs/cross-os-v0.9.5/raw/cold` міститься в [public evidence archive](../artifacts/README.md). Статистика: [`cold-comparison-statistics.json`](../analysis/universal-cross-os-4g/cold-comparison-statistics.json), [`cold-per-run.csv`](../analysis/universal-cross-os-4g/cold-per-run.csv).

### Однаковий `THP=madvise`

| Метрика, mean | Ubuntu 24.04 | Debian 12 | Результат |
|---|---:|---:|---|
| Normalized wall time до h4500 | 62.372 s | 64.430 s | різниця не доведена; paired CI перетинає 0 |
| Process CPU / observed block | 10.599 ms | 10.449 ms | Debian −1.44%; усі 6 пар одного знаку |
| Average RSS | 59,682 KiB | 59,247 KiB | практично однаково |
| Peak RSS | 88,934 KiB | 89,077 KiB | практично однаково |
| Target `AnonHugePages` | 0 | 0 | однаково |

Сира серія `outputs/cross-os-v0.9.5/raw/cold-thp-madvise` міститься в [public evidence archive](../artifacts/README.md). Статистика: [`cold-thp-madvise-statistics.json`](../analysis/universal-cross-os-4g/cold-thp-madvise-statistics.json), [`cold-thp-madvise-per-run.csv`](../analysis/universal-cross-os-4g/cold-thp-madvise-per-run.csv).

Зміна знаку невеликої wall-time різниці між двома серіями — сильний доказ, що заявляти переможця за швидкістю не можна. Натомість нижчий CPU/block на Debian повторився в обох cold-серіях.

## Warm resume та idle

### Нативні kernel defaults

| Метрика, mean | Ubuntu 24.04 | Debian 12 | Результат |
|---|---:|---:|---|
| First RPC | 4.214 s | 4.172 s | практично однаково |
| Sync-ready | 6.531 s | 6.820 s | мала різниця, недостатня для загального performance-висновку |
| Idle CPU за 120 s | 0.078 s | 0.073 s | практично однаково |
| Idle average RSS | 28,189 KiB | 54,441 KiB | Ubuntu −48.22% |
| Idle peak RSS | 29,479 KiB | 62,039 KiB | Ubuntu −52.48% |
| RPC mean | 0.538 ms | 0.500 ms | абсолютна різниця несуттєва |

Сира серія `outputs/cross-os-v0.9.5/raw/warm` міститься в [public evidence archive](../artifacts/README.md). Статистика: [`warm-comparison-statistics.json`](../analysis/universal-cross-os-4g/warm-comparison-statistics.json), [`warm-per-run.csv`](../analysis/universal-cross-os-4g/warm-per-run.csv).

### Однаковий `THP=madvise`

| Метрика, mean | Ubuntu 24.04 | Debian 12 | Результат |
|---|---:|---:|---|
| First RPC | 4.244 s | 4.189 s | практично однаково |
| Sync-ready | 7.274 s | 7.185 s | практично однаково |
| Idle CPU за 120 s | 0.105 s | 0.092 s | різниця 0.013 s, фактично рівень clock-tick quantization |
| Idle average RSS | 29,456 KiB | 29,213 KiB | практично однаково |
| Idle peak RSS | 31,417 KiB | 30,531 KiB | практично однаково |
| RPC mean | 0.571 ms | 0.534 ms | абсолютна різниця несуттєва |

Сира серія `outputs/cross-os-v0.9.5/raw/warm-thp-madvise` міститься в [public evidence archive](../artifacts/README.md). Статистика: [`warm-thp-madvise-statistics.json`](../analysis/universal-cross-os-4g/warm-thp-madvise-statistics.json), [`warm-thp-madvise-per-run.csv`](../analysis/universal-cross-os-4g/warm-thp-madvise-per-run.csv).

## Причина різниці RAM: Transparent Huge Pages

Контрольний smaps-тест змінив лише Debian з `THP=always` на тимчасове `THP=madvise`:

| Debian | RSS наприкінці | Anonymous | AnonHugePages |
|---|---:|---:|---:|
| Native `always` | 65,068 KiB | 56,176 KiB | 49,152 KiB |
| Temporary `madvise` | 28,140 KiB | 19,196 KiB | 0 KiB |

У тому самому `madvise`-запуску Ubuntu завершила з RSS 28,112 KiB: різниця з Debian становила лише 28 KiB. Отже, велика default-RSS різниця причинно пояснюється THP policy.

Raw diagnostic paths are preserved in the [public evidence archive](../artifacts/README.md). Derived evidence: [`thp-causality.json`](../analysis/universal-cross-os-4g/thp-causality.json).

## Чи варто примусово ставити `THP=madvise` на Debian

Для цього виконано окремий прямий причинний тест: 12 синхронних cold-пар, де Debian чергував шість `always` і шість `madvise` за наперед заданим interleaved-порядком, а Ubuntu з незмінним `madvise` служила одночасним контролем зовнішнього шуму.

Ефект `madvise − always` на Debian після поправки на одночасну Ubuntu-контрольну VPS:

| Метрика | Скоригований ефект | Інтерпретація |
|---|---:|---|
| Wall time | −0.255 s (−0.44%) | доказів зміни немає; CI −7.60…+6.91 s |
| CPU / block | +0.240 ms (+2.31%) | відтворюване погіршення; CI +1.22…+3.47% |
| Average RSS | −4,790 KiB (−7.49%) | відтворюване зменшення |
| Peak RSS | −17,675 KiB (−16.31%) | відтворюване зменшення |
| Target `AnonHugePages` | −35,499 KiB (−100%) | huge pages усунено |
| RPC mean | без доведеної зміни | практично однаково |

Тому глобально вносити `THP=madvise` як обов'язкову «оптимізацію Debian» у bootstrap не можна. Це профільний компроміс: менше RAM в обмін на приблизно 2.3% більше process CPU на блок, без доведеного прискорення. Якщо документувати його, то лише як опціональний memory-constrained profile з явним trade-off і перевіркою після reboot.

Сира серія `outputs/cross-os-v0.9.5/raw/cold-debian-thp-interleaved` міститься в [public evidence archive](../artifacts/README.md). Статистика: [`cold-debian-thp-interleaved-statistics.json`](../analysis/universal-cross-os-4g/cold-debian-thp-interleaved-statistics.json), [`cold-debian-thp-interleaved-per-run.csv`](../analysis/universal-cross-os-4g/cold-debian-thp-interleaved-per-run.csv).

В Ubuntu run 20 зафіксовано один рядок `awk: fatal` від monitor harness після завершення daemon: PID уже зник, коли monitor читав `/proc/PID/io`. `systemd Result=success`, `ExecMainStatus=0`, graceful stop code 0, daemon-fatal відсутній. Run залишено валідним, raw evidence не редагувалося, а monitor після цього виправлено перевіркою PID start-time та безпечним завершенням при зникненні `/proc`. Класифікація: [`cold-pair20-monitor-race-classification.json`](../analysis/universal-cross-os-4g/cold-pair20-monitor-race-classification.json).

## Stop, restart і reboot

На кожній ОС виконано два reboot-цикли з тимчасово enabled benchmark service, включно з reboot при активному daemon та peers.

- після кожного reboot daemon автоматично стартував, відкривав RPC/P2P та мав 8 outgoing peers;
- blockchain height після відновлення: 4803 на обох VPS;
- фінальний graceful stop: code 0 на обох;
- crashes, SIGILL, daemon fatal patterns і systemd failures: 0;
- після тесту benchmark services вимкнені, daemon/monitor не працюють, тестові порти не слухають;
- Debian повернений до нативного `THP=always`, Ubuntu — до нативного `THP=madvise`;
- Debian bootstrap status і port audit пройшли; Ubuntu port audit пройшов, а Debian-only status helper на Ubuntu не застосовувався, тому його перевірено вручну.

Raw reboot evidence is preserved under `outputs/cross-os-v0.9.5/raw/reboot` in the [public evidence archive](../artifacts/README.md).

## Обмеження

- VPS показують однакову модель/flags vCPU, але провайдер не гарантує однакові фізичні ядра або однаковий scheduler noise.
- Live P2P network не можна повністю заморозити. Одночасний paired-запуск і однаковий стартовий state зменшують, але не усувають цей шум.
- Ядра різні (Ubuntu 6.8, Debian 6.1), бо тест порівнює реальні підтримувані ОС. Результат не розділяє kernel і userspace внесок усередині поняття «ОС».
- По шість валідних пар у базових серіях достатньо для повторюваних великих ефектів і direction consistency, але недостатньо для доведення малих wall-time відмінностей; відповідні довірчі інтервали широкі.
- Перевірено AMD EPYC Rome. Intel, інші покоління AMD і CPU без тих самих flags не входять у цей висновок.
- Reboot/lifecycle перевірено функціонально, але не тижнями безперервної роботи.

## Остаточна рекомендація

Universal v0.9.5 придатна для обох ОС і не має доведеної end-to-end performance-переваги на жодній з них. Для стандартного deployment path варто підтримувати один Universal artifact.

Для 4 GiB VPS немає підстав віддавати перевагу Ubuntu лише через нижчий RSS daemon. Якщо змушено вибирати ОС саме за виміряною ефективністю Universal, Debian 12 має невелику перевагу за CPU/block; називати його швидшим усе одно не можна, бо wall time цього не підтвердив. Подальший 1-GiB тест також показав, що Debian залишає більше системного `MemAvailable`, попри вищий RSS процесу зі штатним `THP=always`.

1-GiB follow-up: [`universal-ubuntu24-vs-debian12-1g.md`](universal-ubuntu24-vs-debian12-1g.md).

Пов'язаний Ubuntu-native vs Universal A/B: [`ubuntu-native-vs-universal-ubuntu24.md`](ubuntu-native-vs-universal-ubuntu24.md).
