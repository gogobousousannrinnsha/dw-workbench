from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dll-path", type=Path)
    parser.add_argument("--codepage", type=int)


def runtime_arguments(args: argparse.Namespace) -> dict[str, object]:
    return {"dll_path": args.dll_path, "codepage": args.codepage}


def prepare_output(source_value: str | Path, output_value: str | Path) -> Path:
    source = Path(source_value).expanduser().resolve()
    output = Path(output_value).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"input XDW does not exist: {source}")
    if source.suffix.lower() != ".xdw" or output.suffix.lower() != ".xdw":
        raise ValueError("input and output paths must have the .xdw suffix")
    if source == output:
        raise ValueError("output must be different from the input XDW")
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    return output


def annotation_type_name(value: object) -> str:
    return getattr(value, "name", str(value))
