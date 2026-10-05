from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from docuworks_ctypes import XdwApi


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect XDWAPI candidates in isolated subprocesses and write JSON evidence."
    )
    parser.add_argument("--verification-document", type=Path)
    parser.add_argument("--search-path", action="append", type=Path, default=[])
    parser.add_argument("--dll-path", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("runtime-resolution.json")
    )
    args = parser.parse_args()

    report = XdwApi.inspect_runtimes(
        dll_path=args.dll_path,
        search_paths=args.search_path,
        verification_document=args.verification_document,
    )
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_dll": str(args.dll_path.resolve()) if args.dll_path else None,
        "requested_search_paths": [str(path.resolve()) for path in args.search_path],
        "verification_document": (
            str(args.verification_document.resolve())
            if args.verification_document
            else None
        ),
        "resolution": report.to_dict(),
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
