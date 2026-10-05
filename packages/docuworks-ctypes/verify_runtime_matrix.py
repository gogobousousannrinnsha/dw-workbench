from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


NOT_INSTALLED = 0x80040001


def _candidate(report: dict, path: Path) -> dict:
    expected = str(path.resolve()).casefold()
    for candidate in report["resolution"]["candidates"]:
        if candidate["bundle"]["xdwapi"].casefold() == expected:
            return candidate
    raise AssertionError(f"runtime candidate not found: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the 0.9.0 XDWAPI runtime matrix.")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--sdk10-dll", required=True, type=Path)
    parser.add_argument("--sdk917-dll", required=True, type=Path)
    parser.add_argument("--sdk10-smoke", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8-sig"))
    smoke = json.loads(args.sdk10_smoke.read_text(encoding="utf-8-sig"))
    installed = next(
        item for item in report["resolution"]["candidates"]
        if item["bundle"]["source"] == "installed" and item["selected"]
    )
    sdk10 = _candidate(report, args.sdk10_dll)
    sdk917 = _candidate(report, args.sdk917_dll)
    checks = {
        "installed_10_1_document_open": installed["probe"]["document_open_ok"] is True,
        "sdk10_static_valid": sdk10["static"]["valid"] is True,
        "sdk10_document_open": sdk10["probe"]["document_open_ok"] is True,
        "sdk10_simple_persistence_smoke": smoke["verified"] is True,
        "sdk917_static_valid": sdk917["static"]["valid"] is True,
        "sdk917_expected_not_installed": (
            sdk917["probe"]["document_open_ok"] is False
            and sdk917["probe"]["xdw_error_code"] == NOT_INSTALLED
        ),
        "sdk917_not_selected": sdk917["selected"] is False,
    }
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "status": {
            "installed_10_1_1": "FULL_VERIFIED_BASELINE",
            "sdk_10_0": "SMOKE_VERIFIED",
            "sdk_9_1_7": "ABI_VERIFIED_RUNTIME_CONDITIONALLY_INCOMPATIBLE",
        },
        "verified": all(checks.values()),
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0 if payload["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
