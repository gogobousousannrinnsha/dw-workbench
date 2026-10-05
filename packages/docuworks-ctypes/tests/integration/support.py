from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def safe_case_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return normalized or "case"


def json_value(value: Any) -> Any:
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value, Enum):
        return {"name": value.name, "value": value.value}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"hex": value.hex(), "length": len(value)}
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    return value


class EvidenceWriter:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.evidence_path = self.root / "evidence.jsonl"

    def record(self, case: str, stage: str, **details: Any) -> dict[str, Any]:
        item = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "case": case,
            "stage": stage,
            **{key: json_value(value) for key, value in details.items()},
        }
        with self.evidence_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
        return item

    def write_json(self, name: str, value: Any) -> Path:
        path = self.root / name
        path.write_text(
            json.dumps(json_value(value), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return path

    def copy_fixture(self, source: Path, case: str) -> Path:
        destination_dir = self.root / "xdw"
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{safe_case_name(case)}{source.suffix.lower()}"
        shutil.copy2(source, destination)
        self.record(
            case,
            "fixture_copy",
            source=source,
            destination=destination,
            source_sha256=sha256_file(source),
            destination_sha256=sha256_file(destination),
        )
        return destination
