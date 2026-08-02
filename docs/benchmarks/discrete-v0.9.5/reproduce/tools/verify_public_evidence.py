#!/usr/bin/env python3
"""Verify integrity, archive safety, and privacy properties of the public bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath

from package_public_evidence import validate_public


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
METADATA_PATHS = {
    "MANIFESTS/original-selected-files-sha256.txt",
    "MANIFESTS/public-selected-files-sha256.txt",
    "PUBLICATION.json",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_manifest(data: bytes, label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
        digest, separator, name = line.partition("  ")
        if not separator or not SHA256_RE.fullmatch(digest) or not name:
            raise RuntimeError(f"invalid {label} manifest line {number}")
        if name in result:
            raise RuntimeError(f"duplicate {label} manifest path: {name}")
        result[name] = digest
    return result


def safe_member_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and path.as_posix() == name


def read_archive(archive_path: Path) -> dict[str, bytes]:
    entries: dict[str, bytes] = {}
    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                raise RuntimeError(f"non-regular archive member rejected: {member.name}")
            if not safe_member_name(member.name):
                raise RuntimeError(f"unsafe archive member rejected: {member.name}")
            if member.name in entries:
                raise RuntimeError(f"duplicate archive member rejected: {member.name}")
            handle = archive.extractfile(member)
            if handle is None:
                raise RuntimeError(f"cannot read archive member: {member.name}")
            entries[member.name] = handle.read()
    return entries


def verify_external_archive_hash(archive_path: Path, hash_path: Path) -> str:
    line = hash_path.read_text(encoding="utf-8").strip()
    digest, separator, name = line.partition("  ")
    if not separator or not SHA256_RE.fullmatch(digest) or name != archive_path.name:
        raise RuntimeError(f"invalid archive hash file: {hash_path}")
    actual = sha256_bytes(archive_path.read_bytes())
    if actual != digest:
        raise RuntimeError(f"archive SHA256 mismatch: expected {digest}, got {actual}")
    return actual


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", type=Path)
    arguments = parser.parse_args()

    archive_path = arguments.archive.resolve()
    hash_path = (
        arguments.archive_sha256.resolve()
        if arguments.archive_sha256
        else archive_path.with_name("archive-sha256.txt")
    )
    archive_hash = verify_external_archive_hash(archive_path, hash_path)
    entries = read_archive(archive_path)

    missing_metadata = METADATA_PATHS - entries.keys()
    if missing_metadata:
        raise RuntimeError(f"archive metadata missing: {sorted(missing_metadata)}")

    public_manifest = parse_manifest(
        entries["MANIFESTS/public-selected-files-sha256.txt"], "public"
    )
    original_manifest = parse_manifest(
        entries["MANIFESTS/original-selected-files-sha256.txt"], "original"
    )
    payload = {name: data for name, data in entries.items() if name not in METADATA_PATHS}
    if set(public_manifest) != set(payload):
        raise RuntimeError("public manifest paths do not exactly match archive payload")
    if set(original_manifest) != set(payload):
        raise RuntimeError("original manifest paths do not exactly match archive payload")
    for name, data in payload.items():
        actual = sha256_bytes(data)
        if actual != public_manifest[name]:
            raise RuntimeError(f"public payload SHA256 mismatch: {name}")

    publication = json.loads(entries["PUBLICATION.json"])
    if publication.get("selected_file_count") != len(payload):
        raise RuntimeError("PUBLICATION.json selected_file_count mismatch")
    validate_public(payload, Path("<private-source-not-required-for-verification>"))

    sidecars = {
        "public-selected-files-sha256.txt": entries["MANIFESTS/public-selected-files-sha256.txt"],
        "original-selected-files-sha256.txt": entries["MANIFESTS/original-selected-files-sha256.txt"],
        "redaction-summary.json": entries["PUBLICATION.json"],
    }
    for name, expected in sidecars.items():
        path = archive_path.with_name(name)
        if path.exists() and path.read_bytes() != expected:
            raise RuntimeError(f"external sidecar does not match embedded metadata: {path}")

    print(json.dumps({
        "archive": str(archive_path),
        "archive_sha256": archive_hash,
        "payload_bytes": sum(len(data) for data in payload.values()),
        "payload_files": len(payload),
        "privacy_validation": "passed",
        "safe_regular_members_only": True,
        "sidecars_checked": sum(
            archive_path.with_name(name).exists() for name in sidecars
        ),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
