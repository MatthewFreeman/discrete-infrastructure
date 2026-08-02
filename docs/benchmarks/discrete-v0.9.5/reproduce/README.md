# Reproduce and validate

The public archive preserves the original workspace layout so the included analyzers can run from
the extracted root.

## Verify the published archive

From `artifacts/`:

```bash
python ../reproduce/tools/verify_public_evidence.py \
  --archive discrete-v0.9.5-benchmark-evidence-public.tar.gz
```

The expected archive SHA256 is
`9719dcd03d80df7f4ed5c83e20fd601ff31350621b9c1540a0ebe0fd2e334518`.

## Rerun analysis

Extract the archive and change to its root. The Ubuntu asset A/B analysis uses explicit paths:

```bash
python work/analysis/analyze_cold_runs.py \
  outputs/raw/v0.9.5/v.0.9.5 outputs/analysis/v0.9.5
python work/analysis/analyze_warm_idle_runs.py \
  outputs/raw/v0.9.5/v.0.9.5 outputs/analysis/v0.9.5
python work/analysis/analyze_reboot_runs.py \
  outputs/raw/v0.9.5/v.0.9.5 outputs/analysis/v0.9.5
python work/analysis/comparison_statistics.py outputs/analysis/v0.9.5
```

The nine cross-OS analyzers are self-contained:

```bash
python work/analysis/analyze_crossos_1g.py
python work/analysis/analyze_crossos_512m.py
python work/analysis/analyze_crossos_cold.py
python work/analysis/analyze_crossos_cold_thp_madvise.py
python work/analysis/analyze_crossos_smaps.py
python work/analysis/analyze_crossos_thp_causality.py
python work/analysis/analyze_crossos_warm.py
python work/analysis/analyze_crossos_warm_thp_madvise.py
python work/analysis/analyze_debian_thp_interleaved.py
```

Publication validation ran all 13 analyzers successfully against the sanitized bundle. Derived
outputs matched the public payload manifest after rerun. The two 4-GiB cold CSV files were
regenerated with the current analyzer's monitor-race audit fields; numeric benchmark fields did not
change.

## Rebuild the public archive

Rebuilding requires the retained private benchmark workspace and the curated public controller
overrides in this repository:

```powershell
python .\docs\benchmarks\discrete-v0.9.5\reproduce\tools\package_public_evidence.py `
  --source C:\path\to\private-benchmark-workspace `
  --output-dir .\docs\benchmarks\discrete-v0.9.5\artifacts
```

Two independent rebuilds must produce the same archive SHA256. Run
`verify_public_evidence.py` after every rebuild.

## Harness warning

The harness is published to explain and reproduce the experiment, not as a production node
installer. The public PowerShell controllers require explicit Ubuntu/Debian SSH targets, key path,
known-hosts path, and optionally an SSH port. Never reuse benchmark data directories concurrently
or point two daemons at the same ports.
