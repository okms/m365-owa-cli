# Release Hygiene

`m365-owa-cli` ships only the Python package source, package metadata, `README.md`, and
`docs/schema.md` in the source distribution. Operational agent guidance, research notes,
tests, CI workflows, local locks, and generated artifacts are intentionally excluded.

Build artifacts from a clean output directory:

```bash
uv run python -m build --outdir /tmp/m365-owa-cli-dist
uv run python -m twine check /tmp/m365-owa-cli-dist/*
tar -tzf /tmp/m365-owa-cli-dist/m365_owa_cli-*.tar.gz
uv run python scripts/scan_dist_artifacts.py /tmp/m365-owa-cli-dist/*
```

The scanner fails on disallowed repository paths and obvious token-like strings. It is a
release guard, not a substitute for reviewing source changes before tagging.
