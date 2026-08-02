# Public evidence artifact

`discrete-v0.9.5-benchmark-evidence-public.tar.gz` is a deterministic, privacy-sanitized copy of
the retained benchmark workspace.

| Field | Value |
|---|---|
| Archive size | 6,141,447 bytes |
| Archive SHA256 | `9719dcd03d80df7f4ed5c83e20fd601ff31350621b9c1540a0ebe0fd2e334518` |
| Payload files | 6,067 |
| Uncompressed payload | 30,896,053 bytes |
| Sanitizer schema/version | `discrete-benchmark-publication/v1`, version 2 |

## Verify before extraction

From this directory:

```bash
sha256sum --check archive-sha256.txt
python ../reproduce/tools/verify_public_evidence.py \
  --archive discrete-v0.9.5-benchmark-evidence-public.tar.gz
```

The verifier checks the external archive hash, rejects unsafe or non-regular tar members, verifies
every payload file against the embedded public manifest, and repeats the privacy-pattern audit.

After successful verification:

```bash
mkdir discrete-v0.9.5-benchmark-evidence-public
tar -xzf discrete-v0.9.5-benchmark-evidence-public.tar.gz \
  -C discrete-v0.9.5-benchmark-evidence-public
```

PowerShell can run the same Python verifier and the Windows-provided `tar.exe`.

## Archive metadata

- `PUBLICATION.json` records the selection size and redaction counts.
- `MANIFESTS/public-selected-files-sha256.txt` verifies the public payload byte-for-byte.
- `MANIFESTS/original-selected-files-sha256.txt` fingerprints the retained private source files.
  It is provenance evidence, not a manifest that can be verified without the private corpus.

The copies of these records next to the archive make review possible without extraction.

## Privacy transformation

The sanitizer rejects private-key blocks, known token/key shapes, authorization headers, binary
files, NUL-containing files, and non-UTF-8 input. It deterministically replaces public IP addresses,
hostnames, UUIDs, MAC addresses, email-like identifiers, provisioning SSH parameters, SSH public
keys, and local Windows user paths.

IP replacements use the RFC 5737 documentation networks. No reverse mapping is published.
Release/artifact/binary hashes, block hashes, timestamps, numeric measurements, logs, and directory
relationships remain available for audit and rerun.

The archive includes only text evidence and reproduction code. It does not include upstream
Discrete binaries, source archives, private SSH material, or blockchain database files.

## Raw paths used by the reports

After extraction, the main raw roots are:

```text
outputs/raw/v0.9.5/
outputs/cross-os-v0.9.5/raw/
outputs/cross-os-1g-v0.9.5/raw/
outputs/cross-os-512m-v0.9.5/raw/
```
