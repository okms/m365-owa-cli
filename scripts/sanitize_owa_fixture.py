#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from m365_owa_cli.owa.fixture_sanitize import extract_har_action_entries, sanitize_owa_fixture


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sanitize raw OWA JSON/HAR captures before committing them as fixtures."
    )
    parser.add_argument("input", type=Path, help="Raw JSON or HAR capture path.")
    parser.add_argument("output", type=Path, help="Sanitized fixture output path.")
    parser.add_argument(
        "--har-action",
        help="When input is a HAR, keep only entries whose request URL contains this OWA action.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if args.har_action:
        payload = extract_har_action_entries(payload, args.har_action)

    sanitized = sanitize_owa_fixture(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(sanitized, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Wrote sanitized fixture to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
