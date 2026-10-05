from __future__ import annotations

import argparse
import json
from pathlib import Path

from docuworks_ctypes import STANDARD_ATTRIBUTE_REGISTRY
from docuworks_ctypes.enums import AnnotationType


def generate(evidence_path: Path) -> dict[str, object]:
    observations: dict[tuple[int, str], dict[str, object]] = {}
    for line in evidence_path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item.get("stage") not in {"coverage_immediate", "coverage_persistence"}:
            continue
        key = (int(item["annotation_type"]), str(item["attribute"]))
        observations.setdefault(key, {})[str(item["stage"])] = item

    rows = []
    complete = 0
    for key, spec in sorted(STANDARD_ATTRIBUTE_REGISTRY.items()):
        stages = observations.get(key, {})
        immediate = "VERIFIED" if "coverage_immediate" in stages else "MISSING"
        persistence = "VERIFIED" if "coverage_persistence" in stages else "MISSING"
        if immediate == persistence == "VERIFIED":
            complete += 1
        rows.append(
            {
                "annotation_type": AnnotationType(key[0]).name,
                "annotation_type_value": key[0],
                "attribute": key[1],
                "contract": "VERIFIED",
                "immediate": immediate,
                "persistence": persistence,
                "viewer": "REPRESENTATIVE_TYPE_PENDING",
                "writable": spec.writable,
                "evidence_case": (
                    stages.get("coverage_persistence", {}).get("case")
                    or stages.get("coverage_immediate", {}).get("case")
                ),
                "runtime_observation": None,
            }
        )
    return {
        "schema_version": 1,
        "runtime_scope": "Windows x64 / Python 3.11 / XDWAPI 10.1.1",
        "registry_count": len(STANDARD_ATTRIBUTE_REGISTRY),
        "complete_count": complete,
        "full_persistence_verified": complete == len(STANDARD_ATTRIBUTE_REGISTRY),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = generate(args.evidence)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0 if report["full_persistence_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
