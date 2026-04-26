from __future__ import annotations

import importlib.util
import tarfile
import tomllib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_scan_module():
    path = ROOT / "scripts" / "scan_dist_artifacts.py"
    spec = importlib.util.spec_from_file_location("scan_dist_artifacts", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sdist_build_policy_is_explicit_and_minimal():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    sdist = data["tool"]["hatch"]["build"]["targets"]["sdist"]

    assert set(sdist["include"]) == {
        "src/m365_owa_cli/**",
        "README.md",
        "pyproject.toml",
        "docs/schema.md",
        "docs/release.md",
    }
    assert set(sdist["exclude"]) >= {
        ".github/**",
        "AGENTS.md",
        "CLAUDE.md",
        "docs/research/**",
        "specs/**",
        "tests/**",
        "uv.lock",
    }


def test_artifact_scanner_rejects_disallowed_sdist_members(tmp_path):
    scanner = _load_scan_module()
    artifact = tmp_path / "m365_owa_cli-0.0.0.tar.gz"

    with tarfile.open(artifact, "w:gz") as archive:
        source = tmp_path / "AGENTS.md"
        source.write_text("agent guidance\n", encoding="utf-8")
        archive.add(source, arcname="m365_owa_cli-0.0.0/AGENTS.md")

    findings = scanner.scan_artifact(artifact)

    assert findings
    assert findings[0].kind == "disallowed-path"
    assert findings[0].member.endswith("AGENTS.md")


def test_artifact_scanner_rejects_token_like_content(tmp_path):
    scanner = _load_scan_module()
    artifact = tmp_path / "m365_owa_cli-0.0.0-py3-none-any.whl"

    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("m365_owa_cli/example.py", 'TOKEN = "Bearer eyJsecret.token.value"\n')

    findings = scanner.scan_artifact(artifact)

    assert findings
    assert findings[0].kind == "secret-pattern"
    assert findings[0].member == "m365_owa_cli/example.py"
