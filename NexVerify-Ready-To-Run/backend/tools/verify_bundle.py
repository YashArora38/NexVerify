"""Offline verifier for a NexVerify provenance ZIP.

Usage: python backend/tools/verify_bundle.py path/to/bundle.zip
The command reads the ZIP in memory, never extracts it, and exits non-zero on
any integrity or safety failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Permit direct invocation from the repository root or from backend/tools.
try:
    from app.provenance import verify_bundle
except ModuleNotFoundError:  # pragma: no cover - exercised by direct CLI use
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.provenance import verify_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a NexVerify offline provenance bundle")
    parser.add_argument("bundle", type=Path, help="ZIP bundle to verify")
    args = parser.parse_args(argv)
    result = verify_bundle(args.bundle)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
