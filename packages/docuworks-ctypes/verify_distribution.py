from __future__ import annotations

import argparse
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path


FORBIDDEN_SUFFIXES = (".dll", ".xdw", ".pdf", ".h", ".pyc")
FORBIDDEN_PARTS = ("__pycache__", "integration-runs", "integration-artifacts")
FORBIDDEN_CONTENT = (re.compile(rb"[a-z]:[\\/]+users[\\/]+[^\\/\s]+", re.I),)


def _package_python_files(archive: zipfile.ZipFile) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for name in archive.namelist():
        normalized = name.replace("\\", "/")
        marker = "docuworks_ctypes/"
        position = normalized.find(marker)
        if position >= 0 and normalized.endswith(".py"):
            key = normalized[position:]
            result[key] = archive.read(name)
    return result


def _audit(archive: zipfile.ZipFile) -> list[str]:
    errors: list[str] = []
    for name in archive.namelist():
        normalized = name.replace("\\", "/")
        lower = normalized.lower()
        if lower.endswith(FORBIDDEN_SUFFIXES):
            errors.append(f"forbidden suffix: {normalized}")
        if any(part in lower.split("/") for part in FORBIDDEN_PARTS):
            errors.append(f"forbidden path: {normalized}")
        if name.endswith("/"):
            continue
        data = archive.read(name)
        lowered = data.lower()
        for pattern in FORBIDDEN_CONTENT:
            if pattern.search(lowered):
                errors.append(f"local absolute path content: {normalized}")
                break
    return errors


def verify(wheel_path: Path, source_path: Path) -> dict[str, object]:
    with zipfile.ZipFile(wheel_path) as wheel, zipfile.ZipFile(source_path) as source:
        wheel_errors = _audit(wheel)
        source_errors = _audit(source)
        wheel_python = _package_python_files(wheel)
        source_python = _package_python_files(source)
    missing = sorted(set(source_python) - set(wheel_python))
    wheel_only = sorted(set(wheel_python) - set(source_python))
    different = sorted(
        name for name in set(wheel_python) & set(source_python)
        if wheel_python[name] != source_python[name]
    )
    verified = not (wheel_errors or source_errors or missing or wheel_only or different)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "wheel": str(wheel_path.resolve()),
        "source_zip": str(source_path.resolve()),
        "wheel_python_count": len(wheel_python),
        "source_python_count": len(source_python),
        "wheel_errors": wheel_errors,
        "source_errors": source_errors,
        "missing_from_wheel": missing,
        "wheel_only": wheel_only,
        "different": different,
        "verified": verified,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit release archives and compare package Python files.")
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--source-zip", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.wheel.resolve(), args.source_zip.resolve())
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
