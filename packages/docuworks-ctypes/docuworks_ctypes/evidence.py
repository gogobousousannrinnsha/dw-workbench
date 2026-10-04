from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


def verify_evidence_archive(
    archive: Path, *, allow_missing_required: bool = False
) -> dict[str, object]:
    archive = archive.expanduser().resolve()
    with zipfile.ZipFile(archive) as package:
        members = {
            name.replace("\\", "/"): name
            for name in package.namelist()
            if not name.endswith(("/", "\\"))
        }
        manifest_name = members.get("artifact-manifest.json")
        if manifest_name is None:
            raise ValueError("artifact-manifest.json is missing from the archive")
        manifest = json.loads(package.read(manifest_name).decode("utf-8-sig"))
        missing_required = manifest.get("missing_required_files", [])
        if missing_required and not allow_missing_required:
            raise ValueError(f"required evidence is missing: {missing_required}")

        errors = []
        for expected in manifest.get("files", []):
            normalized = expected["path"].replace("\\", "/")
            member = members.get(normalized)
            if member is None:
                errors.append(f"missing archive member: {normalized}")
                continue
            data = package.read(member)
            if len(data) != int(expected["size"]):
                errors.append(f"size mismatch: {normalized}")
            actual_hash = hashlib.sha256(data).hexdigest().upper()
            if actual_hash != str(expected["sha256"]).upper():
                errors.append(f"SHA-256 mismatch: {normalized}")
        if errors:
            raise ValueError("; ".join(errors))

    return {
        "archive": str(archive),
        "verified_files": len(manifest.get("files", [])),
        "missing_required_files": missing_required,
    }
