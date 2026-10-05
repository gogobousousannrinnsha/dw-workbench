from __future__ import annotations

import argparse
from pathlib import Path

from docuworks_ctypes import AnnotationType
from docuworks_ctypes.simple import open_xdw

from _common import add_runtime_arguments, prepare_output, runtime_arguments


def main() -> None:
    parser = argparse.ArgumentParser(description="Move and resize the first rectangle.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--x", type=float, default=25.0)
    parser.add_argument("--y", type=float, default=45.0)
    parser.add_argument("--width", type=float, default=40.0)
    parser.add_argument("--height", type=float, default=25.0)
    add_runtime_arguments(parser)
    args = parser.parse_args()
    output = prepare_output(args.input, args.output)

    with open_xdw(output, writable=True, **runtime_arguments(args)) as document:
        rectangle = next(
            (item for item in document.page(1).annotations()
             if item.type is AnnotationType.RECTANGLE),
            None,
        )
        if rectangle is None:
            raise RuntimeError("page 1 has no rectangle annotation")
        rectangle.move_to(x=args.x, y=args.y)
        rectangle.resize(width=args.width, height=args.height)
        document.save()
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
