#!/usr/bin/env python3
"""Build a deterministic, privacy-sanitized Discrete benchmark evidence bundle."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import ipaddress
import json
import re
import tarfile
import uuid
from collections import Counter
from pathlib import Path, PurePosixPath


VERSION = 2
ARCHIVE_NAME = "discrete-v0.9.5-benchmark-evidence-public.tar.gz"
IP_PRESERVE = {"0.0.0.0", "1.1.1.1", "127.0.0.1", "255.255.255.255"}
DOCUMENTATION_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
)
HOSTNAME_MAP = {
    "Seattle-AMD-Ubuntu": "benchmark-ubuntu",
    "Seattle-AMD-Debian": "benchmark-debian",
}
UUID_NAMESPACE = uuid.UUID("85f477c1-f0db-58bb-ae1e-f3a92901cd75")

IPV4_RE = re.compile(
    r"(?<![0-9])(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})"
    r"(?:\.(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})){3}(?![0-9])"
)
UUID_RE = re.compile(
    r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}(?![0-9a-f])"
)
MAC_RE = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])")
EMAIL_RE = re.compile(r"(?i)(?<![a-z0-9._%+-])[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}(?![a-z0-9.-])")
PACKER_KEY_RE = re.compile(r"PACKER_SSHPUBKEY=[^\s]+")
SSH_KEY_RE = re.compile(r"ssh-(?:ed25519|rsa)\s+[A-Za-z0-9+/=]+(?:\s+[^\r\n]+)?")
WINDOWS_USER_PATH_RE = re.compile(r"(?i)[A-Z]:\\Users\\[^\\\r\n]+(?:\\[^\r\n\t\"']*)?")

FORBIDDEN_SOURCE_PATTERNS = {
    "private_key": re.compile(r"BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "authorization_header": re.compile(r"(?i)Authorization:\s*(?:Bearer|Basic)\s+\S+"),
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def selected_files(source: Path) -> list[Path]:
    paths: list[Path] = []
    outputs = source / "outputs"
    if not outputs.is_dir():
        raise RuntimeError(f"missing outputs directory: {outputs}")
    paths.extend(path for path in outputs.rglob("*") if path.is_file())

    for folder in (
        source / "work" / "analysis",
        source / "work" / "harness-v0.9.5",
        source / "work" / "cross-os-v0.9.5",
    ):
        if not folder.is_dir():
            raise RuntimeError(f"missing reproduction folder: {folder}")
        paths.extend(
            path for path in folder.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )

    for path in (
        source / "work" / "source-v0.9.5" / ".github" / "workflows" / "release.yml",
        source / "work" / "source-v0.9.5" / "CMakeLists.txt",
    ):
        if not path.is_file():
            raise RuntimeError(f"missing upstream provenance file: {path}")
        paths.append(path)

    unique = {path.resolve(): path for path in paths}
    return sorted(unique.values(), key=lambda path: path.relative_to(source).as_posix())


def read_text_files(source: Path, paths: list[Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in paths:
        relative = path.relative_to(source).as_posix()
        data = path.read_bytes()
        if b"\x00" in data:
            raise RuntimeError(f"binary/NUL-containing file rejected: {relative}")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise RuntimeError(f"non-UTF-8 file rejected: {relative}: {error}") from error
        for label, pattern in FORBIDDEN_SOURCE_PATTERNS.items():
            if pattern.search(text):
                raise RuntimeError(f"forbidden {label} pattern in {relative}")
        result[relative] = text
    return result


def apply_public_overrides(texts: dict[str, str]) -> dict[str, str]:
    """Replace private, one-off controllers with their parameterized public copies."""
    reproduce_root = Path(__file__).resolve().parent.parent
    benchmark_root = reproduce_root.parent
    result = dict(texts)
    overrides = {
        f"work/cross-os-v0.9.5/{name}": reproduce_root / "work" / "cross-os-v0.9.5" / name
        for name in ("run-cold-pair.ps1", "run-warm-pair.ps1", "run-reboot-validation.ps1")
    }
    overrides.update({
        "work/analysis/analyze_crossos_512m.py": (
            reproduce_root / "work" / "analysis" / "analyze_crossos_512m.py"
        ),
        "outputs/cross-os-v0.9.5/analysis/cold-per-run.csv": (
            benchmark_root / "analysis" / "universal-cross-os-4g" / "cold-per-run.csv"
        ),
        "outputs/cross-os-v0.9.5/analysis/cold-thp-madvise-per-run.csv": (
            benchmark_root / "analysis" / "universal-cross-os-4g" / "cold-thp-madvise-per-run.csv"
        ),
    })
    for relative, override in overrides.items():
        if relative not in result:
            raise RuntimeError(f"public override target is not selected: {relative}")
        if not override.is_file():
            raise RuntimeError(f"missing public override: {override}")
        result[relative] = override.read_bytes().decode("utf-8-sig")
    return result


def is_sensitive_ip(value: str) -> bool:
    if value in IP_PRESERVE:
        return False
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (address.is_loopback or address.is_multicast or address.is_unspecified)


def is_documentation_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(address in network for network in DOCUMENTATION_NETWORKS)


def documentation_ips() -> list[str]:
    result: list[str] = []
    for network in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"):
        result.extend(str(address) for address in ipaddress.ip_network(network).hosts())
    return result


def build_maps(texts: dict[str, str]) -> dict[str, dict[str, str]]:
    all_text = "\n".join(texts.values())
    sensitive_ips = sorted({value for value in IPV4_RE.findall(all_text) if is_sensitive_ip(value)})
    available = iter(documentation_ips())
    ip_map = {value: next(available) for value in sensitive_ips}

    uuids = sorted(set(UUID_RE.findall(all_text)), key=str.lower)
    uuid_map = {
        value: str(uuid.uuid5(UUID_NAMESPACE, f"discrete-benchmark:{value.lower()}"))
        for value in uuids
    }

    macs = sorted(set(MAC_RE.findall(all_text)), key=str.lower)
    mac_map = {
        value: f"02:00:00:{index >> 16 & 0xff:02x}:{index >> 8 & 0xff:02x}:{index & 0xff:02x}"
        for index, value in enumerate(macs, start=1)
    }

    emails = sorted(set(EMAIL_RE.findall(all_text)), key=str.lower)
    email_map = {value: f"contact-{index:03d}@example.invalid" for index, value in enumerate(emails, start=1)}
    return {"ip": ip_map, "uuid": uuid_map, "mac": mac_map, "email": email_map}


def replace_from_map(text: str, pattern: re.Pattern[str], mapping: dict[str, str], counter: Counter[str], label: str) -> str:
    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        replacement = mapping.get(value)
        if replacement is None:
            replacement = mapping.get(value.lower())
        if replacement is None:
            return value
        counter[label] += 1
        return replacement

    return pattern.sub(replace, text)


def sanitize_text(text: str, source: Path, maps: dict[str, dict[str, str]], counter: Counter[str]) -> str:
    source_windows = str(source)
    for value in (source_windows, source_windows.replace("\\", "/")):
        occurrences = text.lower().count(value.lower())
        if occurrences:
            counter["workspace_path"] += occurrences
            text = re.sub(re.escape(value), "<BENCHMARK_WORKSPACE>", text, flags=re.IGNORECASE)

    def replace_packer(match: re.Match[str]) -> str:
        counter["provisioning_ssh_parameter"] += 1
        return "PACKER_SSHPUBKEY=<REDACTED_PROVISIONING_PUBLIC_KEY>"

    def replace_ssh_key(match: re.Match[str]) -> str:
        counter["ssh_public_key"] += 1
        return "ssh-ed25519 <REDACTED_PUBLIC_KEY>"

    text = PACKER_KEY_RE.sub(replace_packer, text)
    text = SSH_KEY_RE.sub(replace_ssh_key, text)
    for original, replacement in HOSTNAME_MAP.items():
        occurrences = text.count(original)
        if occurrences:
            counter["hostname"] += occurrences
            text = text.replace(original, replacement)
    text = replace_from_map(text, UUID_RE, maps["uuid"], counter, "uuid")
    text = replace_from_map(text, MAC_RE, maps["mac"], counter, "mac")
    text = replace_from_map(text, EMAIL_RE, maps["email"], counter, "email")
    text = replace_from_map(text, IPV4_RE, maps["ip"], counter, "ip")

    def replace_windows_path(match: re.Match[str]) -> str:
        counter["windows_user_path"] += 1
        return "<REDACTED_WINDOWS_USER_PATH>"

    return WINDOWS_USER_PATH_RE.sub(replace_windows_path, text)


def manifest(entries: dict[str, bytes]) -> bytes:
    lines = [f"{sha256_bytes(data)}  {path}" for path, data in sorted(entries.items())]
    return ("\n".join(lines) + "\n").encode("utf-8")


def validate_public(entries: dict[str, bytes], source: Path) -> None:
    combined = b"\n".join(entries.values()).decode("utf-8")
    for label, pattern in FORBIDDEN_SOURCE_PATTERNS.items():
        if pattern.search(combined):
            raise RuntimeError(f"public bundle still contains forbidden {label} pattern")
    packer_placeholder = "PACKER_SSHPUBKEY=<REDACTED_PROVISIONING_PUBLIC_KEY>"
    if any(value != packer_placeholder for value in PACKER_KEY_RE.findall(combined)):
        raise RuntimeError("public bundle contains an unredacted provisioning SSH parameter")
    if SSH_KEY_RE.search(combined):
        raise RuntimeError("public bundle contains an unredacted SSH public key")
    if WINDOWS_USER_PATH_RE.search(combined):
        raise RuntimeError("public bundle contains a Windows user path")
    if str(source).lower() in combined.lower():
        raise RuntimeError("public bundle still contains the local workspace path")
    if any(original in combined for original in HOSTNAME_MAP):
        raise RuntimeError("public bundle still contains an original benchmark hostname")
    for value in IPV4_RE.findall(combined):
        if is_sensitive_ip(value) and not is_documentation_ip(value):
            raise RuntimeError(f"public bundle contains a non-documentation sensitive IP: {value}")


def tar_mode(path: str) -> int:
    return 0o755 if PurePosixPath(path).suffix in {".py", ".sh"} else 0o644


def write_deterministic_archive(path: Path, entries: dict[str, bytes]) -> None:
    with path.open("wb") as raw_handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, compresslevel=9, mtime=0) as gzip_handle:
            with tarfile.open(fileobj=gzip_handle, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, data in sorted(entries.items()):
                    info = tarfile.TarInfo(name=name)
                    info.size = len(data)
                    info.mode = tar_mode(name)
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    archive.addfile(info, io.BytesIO(data))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="Original benchmark workspace root")
    parser.add_argument("--output-dir", type=Path, required=True, help="Repository artifacts directory")
    arguments = parser.parse_args()

    source = arguments.source.resolve()
    output_dir = arguments.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = selected_files(source)
    texts = read_text_files(source, paths)
    maps = build_maps(texts)
    public_texts = apply_public_overrides(texts)
    counter: Counter[str] = Counter()
    public_entries = {
        relative: sanitize_text(text, source, maps, counter).encode("utf-8")
        for relative, text in public_texts.items()
    }
    raw_prefix = "outputs/cross-os-512m-v0.9.5/raw/"
    raw_manifest_path = "outputs/cross-os-512m-v0.9.5/analysis/raw-file-sha256.txt"
    raw_entries = {
        name.removeprefix(raw_prefix): data
        for name, data in public_entries.items()
        if name.startswith(raw_prefix)
    }
    if len(raw_entries) != 862:
        raise RuntimeError(f"expected 862 public 512-MiB raw files, found {len(raw_entries)}")
    public_entries[raw_manifest_path] = manifest(raw_entries)
    validate_public(public_entries, source)

    original_entries = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in paths
    }
    original_manifest = manifest(original_entries)
    public_manifest = manifest(public_entries)
    publication = {
        "schema": "discrete-benchmark-publication/v1",
        "sanitizer_version": VERSION,
        "source_release": "v.0.9.5",
        "selected_file_count": len(paths),
        "original_selected_bytes": sum(len(data) for data in original_entries.values()),
        "public_selected_bytes": sum(len(data) for data in public_entries.values()),
        "redaction_occurrences": dict(sorted(counter.items())),
        "unique_identifiers_redacted": {
            "email": len(maps["email"]),
            "ip": len(maps["ip"]),
            "mac": len(maps["mac"]),
            "uuid": len(maps["uuid"]),
        },
        "integrity_note": (
            "Original hashes describe the private source evidence. Public hashes describe the sanitized payload. "
            "Identifier redaction changes bytes but must not change numeric benchmark measurements."
        ),
    }
    publication_bytes = (json.dumps(publication, indent=2, sort_keys=True) + "\n").encode("utf-8")

    archive_entries = dict(public_entries)
    archive_entries["MANIFESTS/original-selected-files-sha256.txt"] = original_manifest
    archive_entries["MANIFESTS/public-selected-files-sha256.txt"] = public_manifest
    archive_entries["PUBLICATION.json"] = publication_bytes

    archive_path = output_dir / ARCHIVE_NAME
    write_deterministic_archive(archive_path, archive_entries)
    archive_hash = sha256_bytes(archive_path.read_bytes())

    (output_dir / "original-selected-files-sha256.txt").write_bytes(original_manifest)
    (output_dir / "public-selected-files-sha256.txt").write_bytes(public_manifest)
    (output_dir / "redaction-summary.json").write_bytes(publication_bytes)
    (output_dir / "archive-sha256.txt").write_text(f"{archive_hash}  {ARCHIVE_NAME}\n", encoding="utf-8")
    print(json.dumps({
        "archive": str(archive_path),
        "archive_bytes": archive_path.stat().st_size,
        "archive_sha256": archive_hash,
        **publication,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
