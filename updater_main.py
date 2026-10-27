#!/usr/bin/env python3
"""Standalone GUI updater entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from updater_app.ui import run_updater


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--request", required=False)
    args, _unknown = parser.parse_known_args()
    request_path = Path(args.request) if args.request else Path("update_request.json")
    if not request_path.exists():
        return 2
    return run_updater(request_path.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
