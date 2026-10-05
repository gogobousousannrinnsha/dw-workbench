from __future__ import annotations

import argparse
import json
from pathlib import Path

from docuworks_ctypes.evidence import verify_evidence_archive


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify every file recorded in an integration evidence manifest."
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument("--allow-missing-required", action="store_true")
    args = parser.parse_args()

    summary = verify_evidence_archive(
        args.archive, allow_missing_required=args.allow_missing_required
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
