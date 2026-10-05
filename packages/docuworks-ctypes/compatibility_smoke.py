from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

from docuworks_ctypes import AnnotationType, Color, OpenMode, XdwApi
from docuworks_ctypes.simple import SimpleDocument


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def prepare_copy(source_value: str | Path, output_value: str | Path) -> tuple[Path, Path, str]:
    source = Path(source_value).expanduser().resolve()
    output = Path(output_value).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"fixture does not exist: {source}")
    if source.suffix.lower() != ".xdw" or output.suffix.lower() != ".xdw":
        raise ValueError("fixture and output must use the .xdw suffix")
    if source == output:
        raise ValueError("output must differ from the fixture")
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    before = sha256_file(source)
    shutil.copy2(source, output)
    return source, output, before


def main() -> int:
    parser = argparse.ArgumentParser(description="Fresh-install Simple API persistence smoke.")
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output-xdw", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--dll-path", type=Path)
    parser.add_argument("--codepage", type=int, default=932)
    args = parser.parse_args()

    source, output, source_before = prepare_copy(args.fixture, args.output_xdw)
    api = XdwApi.load(
        dll_path=args.dll_path,
        multibyte_codepage=args.codepage,
        verification_document=output,
    )
    with SimpleDocument(api.open_document(output, mode=OpenMode.UPDATE)) as document:
        page = document.page(1)
        page.text("RC smoke", x=20, y=20, font_size=12, fore_color=Color.BLUE)
        page.rectangle(x=20, y=40, width=40, height=25, fill_color=Color.YELLOW)
        document.save()
    with SimpleDocument(api.open_document(output, mode=OpenMode.READONLY)) as document:
        types = [annotation.type for annotation in document.page(1).annotations()]
        if types != [AnnotationType.TEXT, AnnotationType.RECTANGLE]:
            raise AssertionError(f"unexpected persisted annotation types: {types!r}")

    source_after = sha256_file(source)
    if source_after != source_before:
        raise AssertionError("fixture SHA-256 changed")
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "python_executable": sys.executable,
        "python_bits": struct.calcsize("P") * 8,
        "fixture": str(source),
        "fixture_sha256_before": source_before,
        "fixture_sha256_after": source_after,
        "output_xdw": str(output),
        "output_sha256": sha256_file(output),
        "dll_path": str(args.dll_path.resolve()) if args.dll_path else None,
        "persisted_types": [item.name for item in types],
        "verified": True,
    }
    result = args.result.expanduser().resolve()
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
