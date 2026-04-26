#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import re
import sys
import tarfile
from pathlib import Path
from typing import Iterable, NamedTuple
import zipfile


DISALLOWED_PATH_PATTERNS = (
    ".github/**",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/research/**",
    "specs/**",
    "tests/**",
    "uv.lock",
    "*.token",
    "*.credential.json",
    ".env",
    ".env.*",
)

SECRET_PATTERNS = (
    re.compile(
        rb"(?i)\bBearer\s+(?:eyJ[A-Za-z0-9._~+/=-]{8,}|"
        rb"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9._-]{8,}\.[A-Za-z0-9._-]{8,})\b"
    ),
    re.compile(rb"(?i)\bM365_OWA_TOKEN(?:_[A-Z0-9]+)?\s*=\s*[^\s'\";]+"),
    re.compile(
        rb"(?i)\b(access_token|refresh_token|id_token)\s*[:=]\s*[\"']?"
        rb"(?:eyJ[A-Za-z0-9._~+/=-]{8,}|"
        rb"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9._-]{8,}\.[A-Za-z0-9._-]{8,})\b"
    ),
)


class Finding(NamedTuple):
    artifact: Path
    member: str
    kind: str
    detail: str


def _normalized_member_name(name: str) -> str:
    parts = Path(name).parts
    if len(parts) > 1 and parts[0].startswith("m365_owa_cli-"):
        return "/".join(parts[1:])
    return "/".join(parts)


def _is_disallowed_member(name: str) -> str | None:
    normalized = _normalized_member_name(name)
    for pattern in DISALLOWED_PATH_PATTERNS:
        if fnmatch.fnmatch(normalized, pattern):
            return pattern
    return None


def _secret_pattern_name(content: bytes) -> str | None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(content):
            return pattern.pattern.decode("ascii")
    return None


def _scan_members(artifact: Path, members: Iterable[tuple[str, bytes | None]]) -> list[Finding]:
    findings: list[Finding] = []
    for name, content in members:
        disallowed_pattern = _is_disallowed_member(name)
        if disallowed_pattern is not None:
            findings.append(
                Finding(
                    artifact=artifact,
                    member=name,
                    kind="disallowed-path",
                    detail=disallowed_pattern,
                )
            )
        if content is None:
            continue
        secret_pattern = _secret_pattern_name(content)
        if secret_pattern is not None:
            findings.append(
                Finding(
                    artifact=artifact,
                    member=name,
                    kind="secret-pattern",
                    detail=secret_pattern,
                )
            )
    return findings


def _scan_tar(artifact: Path) -> list[Finding]:
    with tarfile.open(artifact) as archive:
        members = []
        for member in archive.getmembers():
            if not member.isfile():
                members.append((member.name, None))
                continue
            extracted = archive.extractfile(member)
            members.append((member.name, None if extracted is None else extracted.read()))
    return _scan_members(artifact, members)


def _scan_zip(artifact: Path) -> list[Finding]:
    with zipfile.ZipFile(artifact) as archive:
        members = []
        for member in archive.infolist():
            if member.is_dir():
                members.append((member.filename, None))
                continue
            members.append((member.filename, archive.read(member)))
    return _scan_members(artifact, members)


def scan_artifact(artifact: str | Path) -> list[Finding]:
    path = Path(artifact)
    if path.suffix == ".whl" or zipfile.is_zipfile(path):
        return _scan_zip(path)
    if path.name.endswith(".tar.gz") or tarfile.is_tarfile(path):
        return _scan_tar(path)
    return [Finding(path, "", "unsupported-artifact", "expected .whl or .tar.gz")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan built wheel/sdist artifacts for release hygiene.")
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args(argv)

    findings: list[Finding] = []
    for artifact in args.artifacts:
        findings.extend(scan_artifact(artifact))

    for finding in findings:
        print(
            f"{finding.artifact}: {finding.kind}: {finding.member}: {finding.detail}",
            file=sys.stderr,
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
