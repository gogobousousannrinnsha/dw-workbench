from __future__ import annotations

import argparse
from pathlib import Path

from docuworks_ctypes import AnnotationType
from docuworks_ctypes.simple import open_xdw

from _common import add_runtime_arguments, prepare_output, runtime_arguments


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete the first annotation of a type.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--type", choices=tuple(AnnotationType.__members__), default="RECTANGLE")
    add_runtime_arguments(parser)
    args = parser.parse_args()
    output = prepare_output(args.input, args.output)
    wanted = AnnotationType[args.type]

    with open_xdw(output, writable=True, **runtime_arguments(args)) as document:
        page = document.page(1)
        annotation = next((item for item in page.annotations() if item.type is wanted), None)
        if annotation is None:
            raise RuntimeError(f"page 1 has no {wanted.name} annotation")
        annotation.delete()
        remaining = page.annotations()
        document.save()
    print(f"Saved: {output} ({len(remaining)} top-level annotations remain)")


if __name__ == "__main__":
    main()
