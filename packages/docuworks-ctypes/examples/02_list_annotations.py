from __future__ import annotations

import argparse
from pathlib import Path

from docuworks_ctypes.simple import open_xdw

from _common import add_runtime_arguments, annotation_type_name, runtime_arguments


def main() -> None:
    parser = argparse.ArgumentParser(description="List top-level annotations read-only.")
    parser.add_argument("input", type=Path)
    add_runtime_arguments(parser)
    args = parser.parse_args()

    with open_xdw(args.input, **runtime_arguments(args)) as document:
        for page_number in range(1, document.core.page_count + 1):
            for index, annotation in enumerate(document.page(page_number).annotations(), 1):
                print(
                    f"page={page_number} index={index} "
                    f"type={annotation_type_name(annotation.type)} "
                    f"position={annotation.position} size={annotation.size}"
                )


if __name__ == "__main__":
    main()
